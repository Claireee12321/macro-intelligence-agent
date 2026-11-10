"""Text utilities: canonical URLs, stable IDs, title tokens, summary cleaning.

Title normalisation and Jaccard overlap originate from MarketBrief's news.py (MIT),
extended with light stemming and macro synonym folding for cross-outlet clustering.
"""

from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "mod", "ref", "src", "cmpid", "cid", "partner", "siteid", "yptr", "fbclid", "gclid",
    "mc_cid", "mc_eid", "taid", "smid", "ftag", "rss", "feed", "dfid", "s_cid", "linkid",
    "__source", "sref", "ns_mchannel", "ns_source", "ns_campaign", "at_medium", "at_campaign",
}

STOPWORDS = frozenset(
    """a an the in on at to for of is are was were be been as by with from into over after before
    and or but not no its it this that these those their his her they them we you our your
    says said say report reports reported says amid via vs versus new latest update updates live
    what why how who when where will would could should may might can just more most than then
    up down out about also still yet ahead today week year years month months day days
    """.split()
)

# Fold common synonyms so different outlets' headlines overlap.
_SYNONYMS = {
    "federal": "fed", "reserve": "fed", "fomc": "fed",
    "nonfarm": "payroll", "nfp": "payroll", "payrolls": "payroll", "jobs": "job", "employment": "job",
    "inflation": "inflation", "cpi": "cpi", "consumer": "consumer",
    "treasuries": "treasury", "yields": "yield", "bonds": "bond",
    "euro": "euro", "eurozone": "eurozone", "ecb": "ecb",
    "tariffs": "tariff", "rates": "rate", "hikes": "hike", "cuts": "cut", "cutting": "cut",
    "raises": "hike", "raising": "hike", "hiking": "hike", "lowers": "cut", "slashes": "cut",
    "holds": "hold", "unchanged": "hold", "pauses": "hold", "steady": "hold",
    "gdp": "gdp", "economy": "economy", "economic": "economy",
    "boe": "boe", "boj": "boj", "pboc": "pboc",
}

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def canonical_url(url: str) -> str:
    """Strip tracking params/fragments, normalise scheme/host, drop trailing slash."""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False) if k.lower() not in _TRACKING_PARAMS]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def stable_id(*parts: str, length: int = 16) -> str:
    h = hashlib.sha1("|".join(p or "" for p in parts).encode("utf-8")).hexdigest()
    return h[:length]


def clean_summary(raw: str, max_chars: int = 320) -> str:
    """Feed summary → plain text, truncated on a word boundary (short attributed excerpt only)."""
    if not raw:
        return ""
    text = BeautifulSoup(raw, "lxml").get_text(" ", strip=True) if "<" in raw else raw
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0].rstrip(",;:-")
    return cut + "…"


def clean_title(raw: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", raw or "")).strip()


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def title_tokens(title: str) -> frozenset[str]:
    """Content tokens for similarity: lowercased, punctuation-stripped, stemmed, synonym-folded."""
    t = title.lower().replace("’", "'")
    t = re.sub(r"'s\b", "", t)
    t = re.sub(r"[^a-z0-9%.\s-]", " ", t)
    t = t.replace("-", " ")
    out = set()
    for w in t.split():
        w = w.strip(".")
        if not w or w in STOPWORDS or _YEAR_RE.match(w):
            continue
        if len(w) <= 2 and not any(c.isdigit() for c in w):
            continue
        w = _SYNONYMS.get(w, w)
        out.add(_SYNONYMS.get(_stem(w), _stem(w)))
    return frozenset(out)


def jaccard(a: frozenset[str] | set[str], b: frozenset[str] | set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def normalized_title_key(title: str) -> str:
    """Key for exact-duplicate detection (same story re-posted with trivial differences)."""
    return " ".join(sorted(title_tokens(title)))
