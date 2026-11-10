from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from macro_intel import timeutil
from macro_intel.config import load_settings
from macro_intel.models import NewsItem, NewsSource
from macro_intel.process.text import canonical_url, stable_id

NOW = datetime(2026, 11, 5, 15, 0, tzinfo=timezone.utc)  # 10:00 ET


@pytest.fixture(autouse=True)
def frozen_now():
    timeutil.set_now(NOW)
    yield NOW
    timeutil.set_now(None)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    for var in ("FRED_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER", "OPENAI_COMPAT_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return load_settings(data_dir=tmp_path / "data", load_env_file=False)


SRC = {
    "off": NewsSource(id="off", name="Official Stats", url="https://x/off", kind="official", tier=1, region="US"),
    "wire": NewsSource(id="wire", name="Wire", url="https://x/wire", kind="media", tier=2, region="US"),
    "daily": NewsSource(id="daily", name="Daily", url="https://x/daily", kind="media", tier=2, region="Global"),
    "ecb": NewsSource(id="ecb", name="ECB", url="https://x/ecb", kind="official", tier=1, region="EA"),
}


def make_item(source: str, title: str, hours: float = 0.0, url: str | None = None, summary: str = "") -> NewsItem:
    src = SRC[source]
    u = url or f"https://news.example/{source}/{stable_id(title)}"
    return NewsItem(id=stable_id(canonical_url(u)), source_id=src.id, source_name=src.name, source_kind=src.kind,
                    source_tier=src.tier, url=u, title=title, summary=summary,
                    published_at=NOW + timedelta(hours=hours), collected_at=NOW, region=src.region)
