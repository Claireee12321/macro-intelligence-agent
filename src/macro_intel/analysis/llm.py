"""LLM provider abstraction, cost accounting and budget guard.

Replaces MarketBrief's core/analysis.py (free-form JSON + fence stripping) with
schema-validated structured outputs. Providers:

* ``anthropic``      — Claude via the official SDK, ``messages.parse`` with a pydantic schema.
* ``openai_compat``  — any OpenAI-compatible /chat/completions endpoint with JSON-schema output.
* ``none`` (default) — no calls are made; the pipeline runs in data-only mode.

The provider interface is deliberately tiny (``generate(system, user, schema) -> (parsed, usage)``)
so another backend (e.g. a subscription-based CLI) can be added without touching callers.
Every call goes through ``Budget`` (per-day call cap + USD cap) and is logged in state.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from macro_intel.config import Settings
from macro_intel.models import LLMCall, LLMUsage
from macro_intel.store import State
from macro_intel.timeutil import ET, utc_now

log = logging.getLogger("macro_intel")
T = TypeVar("T", bound=BaseModel)

# USD per 1M tokens (input, output) — Anthropic list prices (claude-api reference, cached 2026-10-06).
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-1": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
}
UNKNOWN_MODEL_PRICE = (10.00, 50.00)  # conservative default so caps still bind
# Models that accept the server-side refusal fallback ("default" routing).
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
EXPECTED_OUTPUT_TOKENS = 5000  # for pre-call budget estimates (includes thinking)


class LLMError(RuntimeError):
    pass


class LLMRefusal(LLMError):
    pass


def price_for(model: str) -> tuple[float, float]:
    return PRICING.get(model, UNKNOWN_MODEL_PRICE)


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = price_for(model)
    return round(input_tokens / 1e6 * pin + output_tokens / 1e6 * pout, 6)


class Provider(Protocol):
    name: str
    model: str

    def generate(self, system: str, user: str, schema: type[T], max_tokens: int) -> tuple[T, LLMUsage]: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, effort: str = "high"):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=240.0)
        self.model = model
        self.effort = effort

    def generate(self, system: str, user: str, schema: type[T], max_tokens: int = 16000) -> tuple[T, LLMUsage]:
        kwargs: dict = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            output_config={"effort": self.effort},
        )
        if self.model in _FALLBACK_MODELS:
            kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        try:
            resp = self.client.beta.messages.parse(**kwargs)
        except self._anthropic.RateLimitError as exc:
            raise LLMError(f"rate limited: {exc}") from exc
        except self._anthropic.APIStatusError as exc:
            raise LLMError(f"API error {exc.status_code}: {exc.message}") from exc
        except self._anthropic.APIConnectionError as exc:
            raise LLMError(f"connection error: {exc}") from exc
        if resp.stop_reason == "refusal":
            raise LLMRefusal("model declined the request")
        if resp.stop_reason == "max_tokens":
            raise LLMError("output truncated at max_tokens")
        parsed = resp.parsed_output
        if parsed is None:
            raise LLMError("no structured output returned")
        served_by = getattr(resp, "model", self.model) or self.model
        u = resp.usage
        in_tok = (u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0) + (getattr(u, "cache_read_input_tokens", 0) or 0)
        usage = LLMUsage(input_tokens=in_tok, output_tokens=u.output_tokens or 0,
                         cost_usd=cost_usd(served_by, in_tok, u.output_tokens or 0))
        return parsed, usage


class OpenAICompatProvider:
    """Minimal OpenAI-compatible chat-completions client with JSON-schema output (optional)."""

    name = "openai_compat"

    def __init__(self, base_url: str, api_key: str, model: str, price: tuple[float, float] = UNKNOWN_MODEL_PRICE):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.price = price

    def generate(self, system: str, user: str, schema: type[T], max_tokens: int = 16000) -> tuple[T, LLMUsage]:
        import requests

        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()}},
        }
        resp = requests.post(f"{self.base_url}/chat/completions", json=body, timeout=240,
                             headers={"Authorization": f"Bearer {self.api_key}"})
        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
            parsed = schema.model_validate_json(content)
        except (KeyError, IndexError, ValidationError, json.JSONDecodeError) as exc:
            raise LLMError(f"invalid structured output: {exc}") from exc
        u = data.get("usage", {})
        in_tok, out_tok = int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))
        cost = round(in_tok / 1e6 * self.price[0] + out_tok / 1e6 * self.price[1], 6)
        return parsed, LLMUsage(input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost)


def make_provider(settings: Settings) -> Provider | None:
    if not settings.llm_enabled:
        return None
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings.anthropic_api_key, settings.llm_model, settings.llm_effort)
    if settings.llm_provider == "openai_compat":
        return OpenAICompatProvider(settings.openai_compat_base_url, settings.openai_compat_api_key, settings.llm_model)
    return None


class Budget:
    """Per-day (US/Eastern) call and USD caps, enforced before every call."""

    def __init__(self, state: State, settings: Settings):
        self.state = state
        self.max_calls = settings.llm_max_calls_per_day
        self.max_usd = settings.llm_daily_budget_usd

    def _today(self) -> list[LLMCall]:
        today = utc_now().astimezone(ET).date()
        return [c for c in self.state.llm_calls if c.at.astimezone(ET).date() == today]

    def spent_today(self) -> tuple[int, float]:
        calls = self._today()
        return len(calls), round(sum(c.cost_usd for c in calls), 6)

    def check(self, model: str, prompt_chars: int) -> tuple[bool, str]:
        n, spent = self.spent_today()
        if n >= self.max_calls:
            return False, f"daily call cap reached ({n}/{self.max_calls})"
        est = cost_usd(model, int(prompt_chars / 3.5), EXPECTED_OUTPUT_TOKENS)
        if spent + est > self.max_usd:
            return False, f"daily budget would be exceeded (${spent:.3f} spent + ~${est:.3f} est > ${self.max_usd:.2f})"
        return True, ""

    def record(self, purpose: str, provider: Provider, usage: LLMUsage | None, ok: bool, error: str = "") -> None:
        self.state.llm_calls.append(LLMCall(
            at=utc_now(), purpose=purpose, provider=provider.name, model=provider.model,
            input_tokens=usage.input_tokens if usage else 0, output_tokens=usage.output_tokens if usage else 0,
            cost_usd=usage.cost_usd if usage else 0.0, ok=ok, error=error[:300],
        ))


def call_structured(provider: Provider, budget: Budget, purpose: str, system: str, user: str,
                    schema: type[T], max_tokens: int = 16000) -> tuple[T | None, LLMUsage | None, str]:
    """Budget-checked structured call. Returns (parsed, usage, error). Never raises."""
    ok, reason = budget.check(provider.model, len(system) + len(user))
    if not ok:
        log.warning("LLM %s skipped: %s", purpose, reason)
        return None, None, f"budget: {reason}"
    try:
        parsed, usage = provider.generate(system, user, schema, max_tokens)
        budget.record(purpose, provider, usage, ok=True)
        log.info("LLM %s ok — %d in / %d out tokens, $%.4f", purpose, usage.input_tokens, usage.output_tokens, usage.cost_usd)
        return parsed, usage, ""
    except Exception as exc:  # provider failures must not break the pipeline
        budget.record(purpose, provider, None, ok=False, error=str(exc))
        log.warning("LLM %s failed: %s", purpose, exc)
        return None, None, str(exc)
