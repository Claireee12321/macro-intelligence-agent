"""CLI: ``macro-intel <command>`` (or ``python -m macro_intel``)."""

from __future__ import annotations

import argparse
import json
import logging
import sys


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    for noisy in ("urllib3", "yfinance", "peewee", "httpx", "httpx2", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _status_markdown(state, last) -> str:
    from macro_intel.timeutil import fmt_et

    if last is None:
        return "## Macro update\n\nNo run recorded."
    lines = [f"## Macro update — {'✅ ok' if last.ok else '⚠️ partial failure'}",
             f"Run `{last.id}` ({last.trigger}, {last.mode}) · started {fmt_et(last.started_at)} · LLM cost ${last.llm_cost_usd:.2f}", "",
             "| Stage | Status | Time (s) | Detail |", "|---|---|---|---|"]
    for s in last.stages:
        counts = ", ".join(f"{k}={v}" for k, v in s.counts.items())
        detail = (counts + (" · " if counts and s.detail else "") + s.detail).replace("|", "/")[:160]
        lines.append(f"| {s.name} | {s.status} | {s.duration_s} | {detail} |")
    failing = {k: v.get("error", "") for k, v in state.meta.get("source_health", {}).items() if not v.get("ok", True)}
    lines += ["", f"Items {len(state.items)} · events {len(state.events)} · releases {len(state.releases)} · "
              f"calendar {len(state.calendar)} · series {len(state.series)}"]
    if failing:
        lines += ["", "**Failing sources:** " + "; ".join(f"{k} ({str(v)[:80]})" for k, v in failing.items())]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="macro-intel", description="Macro Intelligence Agent pipeline")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--data-dir", help="State/site directory (default: ./data or $MACRO_DATA_DIR)")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Run one full update cycle")
    run.add_argument("--no-llm", action="store_true", help="Data-only mode even if an LLM is configured")
    run.add_argument("--force-briefing", action="store_true", help="Regenerate today's briefing")
    run.add_argument("--trigger", default="manual", help="Label recorded in the run log (e.g. schedule)")

    sub.add_parser("export", help="Re-export the site bundle from stored state")
    st = sub.add_parser("status", help="Show the latest run, source health and LLM usage")
    st.add_argument("--markdown", action="store_true", help="Markdown summary (for the GitHub job summary)")
    gt = sub.add_parser("gate", help="Decide whether a scheduled run should proceed (writes run=true|false to $GITHUB_OUTPUT)")
    gt.add_argument("--event", default="", help="GitHub event name (schedule | workflow_dispatch | ...)")
    sub.add_parser("sample", help="Write a clearly labeled SAMPLE dataset (offline; for UI development)")
    dg = sub.add_parser("digest", help="Write a readable Markdown digest of the exported site data")
    dg.add_argument("--out", help="Output path (default: <data-dir>/digest.md)")

    args = p.parse_args(argv)
    _setup_logging(args.verbose)

    from macro_intel.config import load_settings

    settings = load_settings(data_dir=args.data_dir)

    if args.cmd == "run":
        from macro_intel.pipeline import NoCollectorsError, run_cycle

        try:
            rec = run_cycle(settings, trigger=args.trigger, no_llm=args.no_llm, force_briefing=args.force_briefing)
        except NoCollectorsError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps({"run": rec.id, "ok": rec.ok, "mode": rec.mode,
                          "stages": {s.name: s.status for s in rec.stages}, "llm_cost_usd": rec.llm_cost_usd}, indent=1))
        # Partial failures are reported but do not fail the scheduled job; only a total failure does.
        return 0 if any(s.name == "export" and s.status == "ok" for s in rec.stages) else 1
    if args.cmd == "export":
        from macro_intel.pipeline import export_only

        export_only(settings)
        return 0
    if args.cmd == "gate":
        import os

        from macro_intel.schedule import load_runs, should_run
        from macro_intel.timeutil import utc_now

        ok, reason = should_run(load_runs(settings.state_dir / "runs.json"), utc_now(), args.event)
        print(f"run={'true' if ok else 'false'} — {reason}")
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as fh:
                fh.write(f"run={'true' if ok else 'false'}\nreason={reason}\n")
        return 0
    if args.cmd == "status":
        from macro_intel.store import Store

        state = Store(settings.state_dir).load()
        last = state.runs[-1] if state.runs else None
        if args.markdown:
            print(_status_markdown(state, last))
            return 0
        print(json.dumps({
            "last_run": last.model_dump(mode="json") if last else None,
            "items": len(state.items), "events": len(state.events), "releases": len(state.releases),
            "calendar": len(state.calendar), "series": len(state.series), "briefings": sorted(state.briefings)[-5:],
            "failing_sources": {k: v.get("error") for k, v in state.meta.get("source_health", {}).items() if not v.get("ok", True)},
            "llm_calls_logged": len(state.llm_calls),
        }, indent=1, default=str))
        return 0
    if args.cmd == "digest":
        from pathlib import Path

        from macro_intel.publish.digest import write_digest

        out = write_digest(settings.site_dir, Path(args.out) if args.out else settings.data_dir / "digest.md")
        print(f"Digest written to {out}")
        return 0
    if args.cmd == "sample":
        from macro_intel.sample import write_sample

        path = write_sample(settings)
        print(f"Sample (fixture) dataset written to {path} — clearly labeled as SAMPLE in the UI.")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
