"""Rule-based macro classification: concepts → topics, region, noise flags.

Deterministic and explainable by design; the LLM never decides what is macro-relevant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from macro_intel.models import NewsSource


@dataclass(frozen=True)
class Concept:
    id: str
    pattern: re.Pattern
    topic: str
    strength: str  # high | medium | low
    region: str | None = None  # region implied by the concept itself
    specific: bool = False  # an "event type" (one release/decision) → strong clustering signal
    family: str = ""  # clustering family (defaults to id); e.g. ecb_policy and ecb share "ecb"


def _c(id_, regex, topic, strength, region=None, specific=False, family="", flags=re.I) -> Concept:
    return Concept(id_, re.compile(regex, flags), topic, strength, region, specific, family or id_)


CONCEPTS: list[Concept] = [
    # Inflation
    _c("cpi", r"\b(cpi|consumer[- ]price(s| index)?)\b", "inflation", "high", specific=True),
    _c("pce", r"\b(pce|personal consumption expenditures?|personal income and (outlays|spending))\b", "inflation", "high", "US", True),
    _c("ppi", r"\b(ppi|producer[- ]price(s| index)?|wholesale (prices|inflation))\b", "inflation", "medium", specific=True),
    _c("inflation_print", r"inflation (hits|rises|rose|falls|fell|accelerates|accelerated|slows|slowed|eases|eased|jumps|jumped|climbs|climbed|cools|cooled|picks up|unexpectedly|quickens|holds)|\b(january|february|march|april|may|june|july|august|september|october|november|december) inflation\b|inflation (rate|data|figures|reading)|flash (estimate|inflation)", "inflation", "high", specific=True, family="cpi"),
    _c("inflation_expectations", r"inflation expectations|breakevens?|inflation outlook", "inflation", "medium"),
    _c("inflation_general", r"\binflation\b|disinflation|deflation|price pressures?|sticky prices|cost of living", "inflation", "low"),
    # Labor
    _c("us_payrolls", r"\bpayrolls?\b|non-?farm|jobs report|employment (situation|report)|job (growth|gains)|hiring (slows|picks)", "labor", "high", "US", True),
    _c("unemployment", r"unemployment rate|jobless rate", "labor", "high"),
    _c("jobless_claims", r"jobless claims|unemployment (benefit )?claims|initial claims|continuing claims", "labor", "medium", "US", True),
    _c("jolts", r"\bJOLTS\b|(?i:job openings)", "labor", "medium", "US", True, flags=0),
    _c("wages", r"wage (growth|pressures?|gains|tracker)|average hourly earnings|labou?r costs|employment cost index|\beci\b|pay growth", "labor", "medium"),
    _c("adp", r"\badp\b|private (payrolls|employers added|companies added)|challenger job cuts", "labor", "medium", "US"),
    _c("labor_general", r"labou?r market|layoffs?|job cuts|workforce|employers|turnover figures", "labor", "low"),
    # Growth
    _c("gdp", r"\bgdp\b|gross domestic product|economy (grew|shrank|contracted|expanded|grows|shrinks)|\brecession\b|soft landing|hard landing", "growth", "high", specific=True),
    _c("retail_sales", r"retail sales|consumer spending|household spending", "growth", "medium", specific=True),
    _c("pmi", r"\bpmis?\b|\bism\b|purchasing managers|factory activity|manufacturing (activity|sector)|services (activity|sector)", "growth", "medium", specific=True),
    _c("industrial_production", r"industrial (production|output)|factory (output|orders)|durable goods|capital goods orders", "growth", "medium", specific=True),
    _c("consumer_sentiment", r"consumer (sentiment|confidence)|university of michigan|conference board", "growth", "low", specific=True),
    _c("growth_general", r"economic (growth|outlook|slowdown|activity|data)|growth (forecast|outlook)", "growth", "low"),
    _c("housing", r"housing (starts|market)|home (sales|prices|builders)|building permits|mortgage rates?|house prices|existing-home|new-home", "housing", "low"),
    # Monetary policy — decisions (high, specific) vs. general mentions (medium)
    _c("fed_policy", r"\bfomc\b|federal open market|fed (holds|raises|cuts|hikes|decision|keeps|leaves|pauses|delivers)|fed('s)? (rate|policy) (decision|move|path)|dot plot|beige book|fed minutes|minutes of the fed|summary of economic projections", "monetary_policy", "high", "US", True, "fed"),
    _c("fed_general", r"\bthe fed\b|\bfed\b|federal reserve|fed officials?|fed chair|fed governor", "monetary_policy", "medium", "US", False, "fed"),
    _c("ecb_policy", r"\becb (raises|cuts|holds|keeps|hikes|lifts|lowers|leaves|decision)|\becb('s)? (rate|policy) (decision|meeting|path)|monetary policy decisions|governing council (decision|meeting)", "monetary_policy", "high", "EA", True, "ecb"),
    _c("ecb", r"\becb\b|european central bank|lagarde", "monetary_policy", "medium", "EA", False, "ecb"),
    _c("boe_policy", r"(bank of england|\bboe) (raises|cuts|holds|keeps|hikes|lifts|lowers|leaves|decision)|(\bboe|bank of england)('s)? (rate|policy) decision|monetary policy (summary|report)|official bank rate|\bmpc\b (vote|decision)", "monetary_policy", "high", "UK", True, "boe"),
    _c("boe", r"bank of england|\bboe\b|\bmpc\b", "monetary_policy", "medium", "UK", False, "boe"),
    _c("boj_policy", r"(bank of japan|\bboj) (raises|cuts|holds|keeps|hikes|lifts|lowers|leaves|decision)|statement on monetary policy|outlook for economic activity and prices|\bboj('s)? (rate|policy) (decision|meeting)|minutes of the monetary policy meeting|summary of opinions", "monetary_policy", "high", "JP", True, "boj"),
    _c("boj", r"bank of japan|\bboj\b|\bueda\b", "monetary_policy", "medium", "JP", False, "boj"),
    _c("pboc_policy", r"loan prime rate|\blpr\b|reserve requirement|rrr cut|pboc (cuts|raises|holds|keeps|lowers|rate)", "monetary_policy", "high", "CN", True, "pboc"),
    _c("pboc", r"\bpboc\b|people'?s bank of china", "monetary_policy", "medium", "CN", False, "pboc"),
    _c("rate_decision", r"rate decisions?|interest rates? (decision|unchanged|steady)|\b(cut|cuts|raise|raises|hike|hikes|hold|holds|lift|lifts|lower|lowers|keep|keeps|leave|leaves) (key |interest |benchmark |policy )?(rates\b|rate (at|steady|unchanged|on hold|to)\b)", "monetary_policy", "medium"),
    _c("rate_outlook", r"rate (cut|hike|rise|increase|reduction)s? (ahead|expected|likely|bets?|door|path|odds|pricing)|policy rate|interest rates? (are |is )?(expected to|set to|likely to|poised to)", "monetary_policy", "medium"),
    # Other G10 central banks
    _c("boc_policy", r"(bank of canada|\bboc\b) (raises|cuts|holds|keeps|hikes|lifts|lowers|leaves|decision|rate decision)", "monetary_policy", "high", "CA", True, "boc"),
    _c("boc", r"bank of canada|\bboc\b|macklem", "monetary_policy", "medium", "CA", False, "boc"),
    _c("rba_policy", r"(\brba\b|reserve bank of australia) (raises|cuts|holds|keeps|hikes|lifts|lowers|leaves|decision|rate decision)", "monetary_policy", "high", "AU", True, "rba"),
    _c("rba", r"\brba\b|reserve bank of australia", "monetary_policy", "medium", "AU", False, "rba"),
    _c("rbnz_policy", r"(\brbnz\b|reserve bank of new zealand) (raises|cuts|holds|keeps|hikes|lifts|lowers|leaves|decision|rate decision)", "monetary_policy", "high", "NZ", True, "rbnz"),
    _c("rbnz", r"\brbnz\b|reserve bank of new zealand", "monetary_policy", "medium", "NZ", False, "rbnz"),
    _c("snb_policy", r"(\bsnb\b|swiss national bank) (raises|cuts|holds|keeps|hikes|lifts|lowers|leaves|decision|rate decision)", "monetary_policy", "high", "CH", True, "snb"),
    _c("snb", r"\bsnb\b|swiss national bank", "monetary_policy", "medium", "CH", False, "snb"),
    _c("riksbank_policy", r"(riksbank) (raises|cuts|holds|keeps|hikes|lifts|lowers|leaves|decision|rate decision)", "monetary_policy", "high", "SE", True, "riksbank"),
    _c("riksbank", r"riksbank", "monetary_policy", "medium", "SE", False, "riksbank"),
    _c("norges_policy", r"(norges bank) (raises|cuts|holds|keeps|hikes|lifts|lowers|leaves|decision|rate decision)", "monetary_policy", "high", "NO", True, "norges"),
    _c("norges", r"norges bank", "monetary_policy", "medium", "NO", False, "norges"),
    _c("other_cb", r"central bank", "monetary_policy", "low"),
    _c("cb_speak", r"(?!x)x", "monetary_policy", "low"),  # assigned from OFFICIALS (speeches/remarks)
    # Fiscal & Treasury
    _c("treasury_issuance", r"treasury (auction|refunding|issuance|bill|supply)|quarterly refunding|bond auction|debt (issuance|sale)|t-bills?|coupon (auction|sizes)", "fiscal_policy", "medium", "US", True),
    _c("fiscal", r"budget deficit|\bfiscal\b|\bdeficits?\b|government spending|debt (ceiling|limit)|shutdown|appropriations|tax (bill|cuts?|plan|package)|spending (bill|package|cuts)|\bcbo\b|national debt|stimulus|\bbudget\b", "fiscal_policy", "medium"),
    # Rates, FX, credit, liquidity
    _c("bond_market", r"treasury yields?|bond yields?|\b(2|5|10|30)-year\b|yield curve|bond market|\bgilts?\b|\bbunds?\b|\bjgbs?\b|\btreasuries\b|term premium|bond (selloff|rally|investors|traders)", "rates", "medium"),
    _c("fx", r"\bdollar\b|\byen\b|\bsterling\b|\byuan\b|renminbi|currenc(y|ies)|\bforex\b|\bfx\b|\bdxy\b|euro (falls|rises|slips|gains|weakens|strengthens)|exchange rate|\bpound\b", "fx", "low"),
    _c("credit", r"credit spreads?|high[- ]yield|junk bonds?|corporate (bonds?|debt)|private credit|defaults?|credit market|leveraged loans?|bank lending|lending standards|loan growth", "financial_conditions", "medium"),
    _c("liquidity", r"financial conditions|\bliquidity\b|\brepo\b|money markets?|bank reserves|balance sheet|quantitative (tightening|easing)|\bqt\b|\bqe\b|bank stress|banking (crisis|turmoil)|funding (markets|stress|costs)|\bsofr\b|reverse repo|standing repo|treasury general account", "financial_conditions", "medium"),
    # Energy, commodities, trade, geopolitics
    _c("oil", r"\boil\b|\bcrude\b|\bopec\+?|\bbrent\b|\bwti\b|gasoline|natural gas|\blng\b|energy (prices|crisis|supply)", "energy_commodities", "medium"),
    _c("metals", r"\bgold\b|precious metals|\bcopper\b|\bsilver\b|commodit(y|ies)|iron ore", "energy_commodities", "low"),
    _c("tariffs_trade", r"\btariffs?\b|trade (war|deal|talks|deficit|balance|policy|tensions|truce)|export controls?|import (duties|curbs)|\bwto\b|customs duties", "trade_geopolitics", "medium"),
    _c("sanctions_geo", r"sanctions|ceasefire|missile|invasion|strait of hormuz|red sea|shipping disruption|blockade", "trade_geopolitics", "low"),
    _c("china_econ", r"china'?s (economy|exports|imports|gdp|growth|inflation|factory|retail|property|stimulus)|chinese (economy|exports|growth)|property (sector|crisis|developers?)", "growth", "medium", "CN"),
    # Big-story markers (make non-US items eligible for display)
    _c("market_shock", r"\b(stocks?|equities|markets?|dow|s&p|nasdaq|nikkei|topix|ftse|dax|stoxx|cac|hang seng|csi 300|shanghai composite|kospi|asx|tsx|bonds?|yields?|treasur(y|ies)|gilts?|yen|dollar|sterling|franc|euro)\b.{0,60}\b(plunges?|plummets?|tumbles?|crash(es)?|routs?|meltdown|sell-?offs?|slumps?|worst (day|week|month)|best (day|week)|biggest (one-day )?(drop|fall|decline|gain|jump)|record (high|low)|soars?|collapses?|freefall)\b|\b(plunges?|plummets?|tumbles?|crash(es)?|rout|meltdown|sell-?off)\b.{0,40}\b(stocks?|shares|equities|markets?|bonds?)\b|fear gauge|circuit breaker|flash crash", "financial_conditions", "high", specific=True),
    _c("cb_leadership", r"\b(step(s|ping)? down|resign\w*|successor|succeed|nominat\w*|appoint\w*|fire[sd]?|ousts?)\b.{0,50}\b(ecb|fed|federal reserve|boe|bank of england|boj|bank of japan|pboc|central bank|chair|president|governor)\b|\b(ecb|fed|boe|boj) (president|chair|governor)\b.{0,40}\b(step(s|ping)? down|resign\w*|nominat\w*|successor)", "monetary_policy", "high", specific=True),
    # Equities (secondary)
    _c("equity_market", r"\bstocks?\b|s&p 500|\bnasdaq\b|dow jones|\bequities\b|wall street|stock market|\bshares\b", "equities", "low"),
]

# Fed/central-bank officials (case-sensitive to avoid common-word collisions).
FED_OFFICIALS = re.compile(
    r"\b(Powell|Waller|Jefferson|Bowman|Goolsbee|Hammack|Musalem|Kashkari|Bostic|Barkin|Miran|Warsh|Hassett|"
    r"Logan|Schmid|Daly|Paulson|Collins|Williams)\b"
)
OTHER_OFFICIALS = re.compile(r"\b(Lagarde|Schnabel|Lane|Nagel|Villeroy|Ueda|Himino|Uchida|Bailey|Pan Gongsheng|Macklem|Bullock|Schlegel|Thedeen|Thedéen)\b")
SPEECH_WORDS = re.compile(r"\b(says|said|speaks|speech|remarks|testimony|signals|warns|sees|expects|interview|comments)\b|:", re.I)

NOISE = re.compile(
    r"stocks? to (buy|watch)|best (stocks|etfs|credit cards|savings|cd rates)|how to |personal finance|"
    r"mortgage rates today|retirement (savings|account)|\bquiz\b|\bpodcast\b|newsletter|"
    r"\bcrypto|bitcoin|ethereum|\bnft\b|memecoin|stablecoin|binance|celebrity|\bsports?\b|recipe|horoscope|"
    r"black friday|deal of the day|stocks making the biggest moves|premarket movers|reference rate at|price forecast:|"
    r"ceo (steps down|resigns)|earnings (call|preview|beat|miss)|quarterly (profit|results|earnings)|\bipo\b",
    re.I,
)
# Single-company stories must not count as market-wide shocks.
SINGLE_NAME = re.compile(r"\b[A-Z][\w&.'’-]+(?:'s|’s)? [Ss]hares\b|(?i:\bshares (in|of)\b)|\bstock (jumps|falls|plunges|soars)\b")
# Titles not in English (some aggregator feeds mix languages).
NON_ENGLISH = re.compile(r"\b(tras|del|las|los|para|con|por|sobre|según|una|são|não|uma|und|der|die|das|pour|avec)\b", re.I)
# Routine official publications that are not macro developments.
ROUTINE_OFFICIAL = re.compile(
    r"enforcement action|termination of (an )?enforcement|approv\w* (of )?.{0,30}applications?|applications? (by|of|from)|"
    r"consent order|civil money penalt|prohibition order|bank of japan accounts|\baccounts \(|outright purchases|"
    r"market operations|operations? results|results of (the )?(auction|operation)|time[- ]series|statistics on|"
    r"payment and settlement|tokeni[sz]ed|\bcbdc\b|digital euro|banknotes?|\bcoins?\b|vacanc(y|ies)|recruitment|"
    r"held by the bank of japan|collateral accepted|in addition to decisions setting interest rates|annual report|financial statements|consultation|working paper|data release calendar|publication schedule|"
    r"call for (papers|applications)|conference on|webinar|board meeting|meeting notice|request for (comment|information)",
    re.I,
)

_REGION_PATTERNS: dict[str, re.Pattern] = {
    "EA": re.compile(r"\becb\b|euro ?zone|euro area|\beu\b|european union|germany|german|france|french|italy|italian|spain|spanish|\bbunds?\b|lagarde|brussels", re.I),
    "UK": re.compile(r"\buk\b|britain|british|bank of england|\bboe\b|sterling|\bgilts?\b|\bengland\b|reeves|\bmpc\b", re.I),
    "JP": re.compile(r"japan|japanese|\bboj\b|bank of japan|\byen\b|\bjgbs?\b|tokyo|nikkei", re.I),
    "CN": re.compile(r"\bchina\b|chinese|beijing|\bpboc\b|\byuan\b|renminbi|hong kong|shanghai", re.I),
    "US": re.compile(r"(?-i:\bU\.?S\.?(?=\W|$))|united states|(?<!south )(?<!latin )(?<!central )(?<!north )\bamerican?s?\b|\bfed\b|federal reserve|\bfomc\b|\btreasur(y|ies)\b|wall street|washington|white house|congress|\bbls\b|\bbea\b|non-?farm|payrolls|s&p 500|trump", re.I),
    "CA": re.compile(r"\bcanad\w*|bank of canada|\bboc\b|\bloonie\b|ottawa|macklem", re.I),
    "AU": re.compile(r"\baustralia\w*|\brba\b|reserve bank of australia|aussie|\bbullock\b", re.I),
    "NZ": re.compile(r"new zealand|\brbnz\b|\bkiwi\b", re.I),
    "CH": re.compile(r"switzerland|\bswiss\b|\bsnb\b|\bfranc\b", re.I),
    "SE": re.compile(r"\bswed\w*|riksbank", re.I),
    "NO": re.compile(r"\bnorw\w*|norges bank", re.I),
    "Other": re.compile(
        r"\b(india|indonesia|brazil|mexic|poland|polish|czech|hungar|turk|chile|colombia|peru|argentin|south africa|"
        r"nigeria|egypt|saudi|uae|emirat|israel|russia|ukrain|korea|taiwan|vietnam|thai|malaysia|philippin|singapore|"
        r"denmark|danish|paraguay|uruguay|kenya|pakistan|bangladesh|sri lanka|qatar|kazakh|romania|serbia|iceland|"
        r"ghana|zambia|latin america|emerging[- ]market|rupiah|rupee|ringgit|baht|peso|lira|zloty|forint|koruna|"
        r"lula|mantega|haddad|milei|caputo|sheinbaum|petro|boric|modi|erdogan|prabowo|bukele|orban)\w*",
        re.I,
    ),
}

TOPIC_WEIGHTS = {
    "inflation": 1.0, "labor": 1.0, "monetary_policy": 1.0, "growth": 0.9,
    "financial_conditions": 0.85, "rates": 0.85, "fiscal_policy": 0.8,
    "fx": 0.6, "energy_commodities": 0.6, "trade_geopolitics": 0.6,
    "housing": 0.5, "equities": 0.3, "other": 0.1,
}
REGION_WEIGHTS = {"US": 1.0, "Global": 0.75, "EA": 0.5, "CN": 0.5, "JP": 0.45, "UK": 0.4,
                  "CA": 0.4, "AU": 0.35, "CH": 0.3, "NZ": 0.25, "SE": 0.25, "NO": 0.25, "Other": 0.0}
OUT_OF_COVERAGE_CAP = 15.0  # coverage is G10 + China; other countries are kept but never surface
STRENGTH_FACTOR = {"high": 1.0, "medium": 0.8, "low": 0.5}

_CONCEPTS_BY_ID = {c.id: c for c in CONCEPTS}


def concept(cid: str) -> Concept | None:
    return _CONCEPTS_BY_ID.get(cid)


def families(concepts: list[str]) -> set[str]:
    return {c.family for cid in concepts if (c := _CONCEPTS_BY_ID.get(cid))}


def specific_families(concepts: list[str]) -> set[str]:
    return {c.family for cid in concepts if (c := _CONCEPTS_BY_ID.get(cid)) and c.specific}


@dataclass
class Classification:
    concepts: list[str] = field(default_factory=list)  # from title (strong)
    summary_concepts: list[str] = field(default_factory=list)  # from summary only (weak)
    topics: list[str] = field(default_factory=list)
    region: str = "Other"
    noise: bool = False
    routine_official: bool = False


def _match_concepts(text: str) -> list[str]:
    return [c.id for c in CONCEPTS if c.pattern.search(text)]


def _region_signal(text: str, matched: list[str]) -> str | None:
    implied = {c.region for cid in matched if (c := _CONCEPTS_BY_ID.get(cid)) and c.region}
    hits = {r for r, pat in _REGION_PATTERNS.items() if pat.search(text)}
    major_non_us = (hits | implied) - {"US", "Other"}  # EA, UK, JP, CN and other G10
    us_text = "US" in hits
    us = us_text or "US" in implied
    if len(major_non_us) >= 2:
        return "Global"
    if len(major_non_us) == 1:
        r = next(iter(major_non_us))
        if not us_text:
            return r  # an explicitly named country beats a region merely implied by a concept
        # A non-US central bank / data concept dominates incidental US mentions.
        return r if r in implied else "Global"
    if "Other" in hits and not ("US" in implied):
        return "Other" if not us else "Global"
    if us:
        return "US"
    return None


def detect_region(title: str, summary: str, matched: list[str], default: str) -> str:
    """Title signals win; the summary is consulted only when the title is silent."""
    return _region_signal(title, matched) or _region_signal(f"{title} {summary[:300]}", matched) or default


def classify(title: str, summary: str, source: NewsSource) -> Classification:
    title_hits = _match_concepts(title)
    summary_hits = [c for c in _match_concepts(summary[:400]) if c not in title_hits] if summary else []
    out = Classification(concepts=title_hits, summary_concepts=summary_hits)

    fed_person = FED_OFFICIALS.search(title)
    other_person = OTHER_OFFICIALS.search(title)
    if (fed_person or other_person) and SPEECH_WORDS.search(title):
        out.concepts.append("cb_speak")
        if fed_person and "fed_general" not in out.concepts:
            out.concepts.append("fed_general")

    region = detect_region(title, summary, out.concepts, source.region)
    # Generic "interest rates expected to rise" stories: anchor to the region's central bank.
    cb_general = {"US": "fed_general", "EA": "ecb", "UK": "boe", "JP": "boj", "CN": "pboc", "CA": "boc",
                  "AU": "rba", "NZ": "rbnz", "CH": "snb", "SE": "riksbank", "NO": "norges"}
    if ("rate_decision" in out.concepts or "rate_outlook" in out.concepts) and region in cb_general and not any(
            c in out.concepts for c in set(cb_general.values()) | {f"{v}_policy" for v in cb_general.values()} | {"fed_policy", "other_cb"}):
        out.concepts.append(cb_general[region])
    if "market_shock" in out.concepts and SINGLE_NAME.search(title):
        out.concepts.remove("market_shock")
    # A central-bank mention plus rate-decision language is a policy-decision story — unless it is a speech.
    if "rate_decision" in out.concepts and "cb_speak" not in out.concepts:
        for general, policy in (("fed_general", "fed_policy"), ("ecb", "ecb_policy"), ("boe", "boe_policy"),
                                ("boj", "boj_policy"), ("pboc", "pboc_policy"), ("boc", "boc_policy"), ("rba", "rba_policy"),
                                ("rbnz", "rbnz_policy"), ("snb", "snb_policy"), ("riksbank", "riksbank_policy"),
                                ("norges", "norges_policy")):
            if general in out.concepts and policy not in out.concepts:
                out.concepts.append(policy)

    topics: list[str] = []
    for cid in out.concepts + out.summary_concepts:
        t = _CONCEPTS_BY_ID[cid].topic
        if t not in topics:
            topics.append(t)
    if not topics:
        topics = [t for t in source.topics if t] or ["other"]
    out.topics = topics

    out.region = region
    accents = len(re.findall(r"[áéíóúñãõçà]", title.lower()))
    fn_words = len(NON_ENGLISH.findall(title))
    out.noise = bool(NOISE.search(title)) or fn_words >= 2 or (fn_words >= 1 and accents >= 2)
    out.routine_official = source.kind == "official" and bool(ROUTINE_OFFICIAL.search(title))
    return out
