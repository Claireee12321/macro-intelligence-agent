from macro_intel.process.classify import classify
from macro_intel.process.scoring import score_item
from macro_intel.process.text import canonical_url, clean_summary, jaccard, stable_id, title_tokens

from .conftest import SRC, make_item


def test_canonical_url_strips_tracking_and_normalises():
    a = canonical_url("http://www.Example.com/a/b/?utm_source=x&id=3&mod=rss#frag")
    b = canonical_url("https://example.com/a/b?id=3")
    assert a == b
    assert stable_id(a) == stable_id(b)


def test_title_tokens_fold_synonyms_and_stem():
    t = title_tokens("Federal Reserve raises rates as payrolls surge")
    assert {"fed", "hike", "rate", "payroll"} <= t
    assert jaccard(title_tokens("Fed holds rates steady"), title_tokens("FOMC keeps interest rates unchanged")) > 0.2


def test_clean_summary_strips_html_and_truncates():
    s = clean_summary("<p>Hello <b>world</b> " + "word " * 200 + "</p>", max_chars=60)
    assert "<" not in s and len(s) <= 61 and s.endswith("…")


def _score(source, title, summary=""):
    item = make_item(source, title, summary=summary)
    cls = classify(title, summary, SRC[source])
    return score_item(item, cls)[0], cls


def test_macro_items_outrank_noise():
    cpi, _ = _score("wire", "US consumer prices rise more than expected as core CPI firms")
    crypto, _ = _score("wire", "Bitcoin hits record as crypto ETF inflows surge")
    company, _ = _score("wire", "Retailer quarterly results beat estimates; shares jump")
    assert cpi >= 70
    assert crypto < 20 and company < 40


def test_routine_official_publications_are_penalised():
    routine, _ = _score("off", "Federal Reserve Board announces termination of enforcement action")
    decision, _ = _score("off", "Federal Reserve issues FOMC statement")
    assert decision > 70 and routine < 40


def test_us_region_beats_secondary_regions_for_same_kind_of_story():
    us, _ = _score("wire", "Fed raises rates by a quarter point")
    ecb, c = _score("wire", "ECB raises rates by a quarter point")
    assert c.region == "EA"
    assert us > ecb


def test_region_detection_edge_cases():
    # Lower-case pronoun "us" must not mark a story as US; "South American" is not America.
    c = classify("Paraguay names new central banker", "The South American nation told us it will act.", SRC["wire"])
    assert c.region == "Other"
    c2 = classify("Euro zone inflation hits 4% as ECB hike looms", "", SRC["daily"])
    assert c2.region == "EA"


def test_central_bank_speech_is_lower_weight_than_decision():
    speech, _ = _score("ecb", "Philip R. Lane: AI adoption in Europe")
    decision, _ = _score("ecb", "Monetary policy decisions")
    assert decision - speech > 20
