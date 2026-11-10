"""Calendar helpers shared by processing, export and collectors (no data fetching here)."""

from __future__ import annotations

from macro_intel.store import State
from macro_intel.timeutil import et_datetime, utc_now

FAMILY_NAMES = {
    "cpi": "CPI", "pce": "Personal income & outlays (PCE)", "ppi": "PPI", "us_payrolls": "Employment report",
    "jobless_claims": "Jobless claims", "jolts": "JOLTS", "gdp": "GDP", "retail_sales": "Retail sales",
    "industrial_production": "Industrial production", "fed": "FOMC decision", "consumer_sentiment": "UMich sentiment",
    "pmi": "ISM PMI", "trade": "Trade balance", "boe": "Bank of England decision", "ecb": "ECB decision",
    "boj": "Bank of Japan decision", "ea_cpi": "Euro area CPI", "boc": "Bank of Canada decision",
    "rba": "RBA decision", "rbnz": "RBNZ decision", "snb": "SNB decision",
}


def refresh_status(state: State) -> None:
    now = utc_now()
    for ev in state.calendar.values():
        if ev.status == "released":
            continue
        when = ev.scheduled_at or et_datetime(ev.date, 23, 59)
        ev.status = "upcoming" if when > now else "past"
