"""Settings: environment variables + JSON registries in ``config/``.

Priority: code defaults < config/*.json < environment variables < CLI flags.
Secrets come only from the environment (or a local, gitignored ``.env``).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from macro_intel.models import IndicatorSpec, MarketSpec, NewsSource

log = logging.getLogger("macro_intel")

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        log.warning("Invalid float for %s; using %s", name, default)
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        log.warning("Invalid int for %s; using %s", name, default)
        return default


@dataclass
class Settings:
    root: Path
    config_dir: Path
    data_dir: Path

    fred_api_key: str = ""

    # LLM — disabled by default; nothing is called unless a provider is explicitly enabled.
    llm_provider: str = "none"  # none | anthropic | openai_compat
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "high"
    anthropic_api_key: str = ""
    openai_compat_base_url: str = ""
    openai_compat_api_key: str = ""
    llm_max_event_analyses_per_run: int = 6
    llm_max_calls_per_day: int = 20
    llm_daily_budget_usd: float = 1.00
    llm_min_importance: float = 60.0
    llm_reanalysis_cooldown_hours: float = 12.0

    timezone: str = "America/New_York"
    user_agent: str = "MacroIntelligenceAgent/0.2 (personal research; contact via repository owner)"
    http_timeout: float = 20.0

    sources: list[NewsSource] = field(default_factory=list)
    indicators: list[IndicatorSpec] = field(default_factory=list)
    markets: list[MarketSpec] = field(default_factory=list)

    @property
    def llm_enabled(self) -> bool:
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "openai_compat":
            return bool(self.openai_compat_base_url and self.openai_compat_api_key)
        return False

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    @property
    def site_dir(self) -> Path:
        return self.data_dir / "site"


def _load_list(path: Path, key: str, model):
    if not path.exists():
        example = path.with_name(f"{path.stem}.example{path.suffix}")
        if not example.exists():
            log.warning("Config file missing: %s", path)
            return []
        path = example  # e.g. the public edition ships config/sources.example.json only
    data = json.loads(path.read_text(encoding="utf-8"))
    return [model(**row) for row in data.get(key, []) if not str(row.get("id", "")).startswith("_")]


def load_settings(
    root: str | Path | None = None,
    data_dir: str | Path | None = None,
    load_env_file: bool = True,
) -> Settings:
    root_path = Path(root).resolve() if root else PROJECT_ROOT
    if load_env_file:
        env_file = root_path / ".env"
        if env_file.exists():
            # override=False: real environment variables (e.g. CI secrets) win over .env
            load_dotenv(env_file, override=False)

    config_dir = root_path / "config"
    resolved_data = Path(data_dir or os.environ.get("MACRO_DATA_DIR") or root_path / "data").resolve()

    s = Settings(root=root_path, config_dir=config_dir, data_dir=resolved_data)
    s.fred_api_key = os.environ.get("FRED_API_KEY", "").strip().strip('"').strip("'")
    if s.fred_api_key and not re.fullmatch(r"[a-z0-9]{32}", s.fred_api_key):
        log.warning("FRED_API_KEY is set but does not look like a FRED key (32 lowercase letters/digits); "
                    "ignoring it and using the public CSV instead")
        s.fred_api_key = ""
    s.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    s.llm_provider = os.environ.get("LLM_PROVIDER", s.llm_provider).strip().lower() or "none"
    s.llm_model = os.environ.get("LLM_MODEL", s.llm_model).strip() or s.llm_model
    s.llm_effort = os.environ.get("LLM_EFFORT", s.llm_effort).strip() or s.llm_effort
    s.openai_compat_base_url = os.environ.get("OPENAI_COMPAT_BASE_URL", "").strip()
    s.openai_compat_api_key = os.environ.get("OPENAI_COMPAT_API_KEY", "").strip()
    s.llm_max_event_analyses_per_run = _env_int("LLM_MAX_EVENT_ANALYSES_PER_RUN", s.llm_max_event_analyses_per_run)
    s.llm_max_calls_per_day = _env_int("LLM_MAX_CALLS_PER_DAY", s.llm_max_calls_per_day)
    s.llm_daily_budget_usd = _env_float("LLM_DAILY_BUDGET_USD", s.llm_daily_budget_usd)
    s.llm_min_importance = _env_float("LLM_MIN_IMPORTANCE", s.llm_min_importance)

    s.sources = _load_list(config_dir / "sources.json", "sources", NewsSource)
    s.indicators = _load_list(config_dir / "indicators.json", "indicators", IndicatorSpec)
    s.markets = _load_list(config_dir / "markets.json", "markets", MarketSpec)
    return s
