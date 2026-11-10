# AGENTS.md — Standing instructions for coding agents

Project: **Macro Intelligence Agent** — a private, personal macroeconomic intelligence website.
Read `docs/PRODUCT_SPEC.md` (what/why), `docs/ARCHITECTURE.md` (how), `docs/IMPLEMENTATION_PLAN.md` (milestones/checkpoints) and `docs/PROGRESS.md` (current state) before starting work.

## Repository rules

- **Two repositories** (owner decision 2026-11-10): the **public** `macro-intelligence-agent` holds code, docs and the
  synthetic sample/demo only; the **private** `macro-intelligence-private` runs the daily update, holds the `data`
  branch and deploys the owner's private site. Never commit collected data (news items, FRED/market values,
  calendar forecasts, digests) to the public repo; `update.yml` refuses to run in public repositories.
- Never change either repository's visibility without explicit owner approval.
- Do not open PRs/issues against, push to, or sync with `yukipanpan/marketbrief`. The remote `marketbrief-upstream-readonly` has pushes disabled; leave it that way.
- Preserve the MIT `LICENSE` and original copyright notice for inherited code.
- Work happens on `dev` (or feature branches); `main` changes through owner-merged pull requests. No history rewrites, no force-pushes.
- Never commit secrets (`.env`, API keys, tokens). Configuration is via environment variables; see `.env.example`.
- Do not deploy a publicly accessible site with real data, create paid resources, or enable billing without explicit owner approval.
  (The public demo site shows only the labeled synthetic sample.)
- Stop at the checkpoints defined in `docs/IMPLEMENTATION_PLAN.md` and report to the owner.

## Analytical rules (non-negotiable)

- Keep five kinds of content separate and labeled: **facts**, **published consensus**, **model interpretation**, **model potential impact**, **observed market moves**.
- Never invent consensus values, prices, dates, news or historical data. If consensus is unavailable, say so.
- Never label a previous observation as consensus, or show an actual before it is published.
- No false precision: no point forecasts of market moves (e.g. "+8bp") and no confidence percentages from the LLM. Use direction / relative strength / low-medium-high confidence / horizon + mechanism.
- Numbers displayed as data must come from the data layer, not from LLM text.
- Avoid look-ahead bias: keep vintage/first-seen information; don't present revised data as the real-time print.
- Macro first: equities only as broad, cross-asset confirmation. No stock picks or trade recommendations.
- Store links, titles and short attributed summaries only — never full copyrighted articles.

## Engineering conventions

- Python ≥ 3.11, package `src/macro_intel`, pydantic v2 models, type hints, `logging` (logger name `macro_intel`).
- Every external call: timeout, retry with backoff, failure isolated to its source/stage.
- LLM calls: schema-validated output, budget caps, never re-analyze unchanged events.
- Tests in `tests/` must run **offline** (fixtures, fake LLM provider). Run `pytest -q` before committing.
- Frontend in `web/` (React + TS + Vite + Tailwind); `npm run build` must pass type-checking.
- Small, reviewable commits with descriptive messages. Update `docs/PROGRESS.md` at the end of each milestone.

## Common commands

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/macro-intel run --no-llm        # full cycle, data-only
cd web && npm install && npm run dev      # local website
```
