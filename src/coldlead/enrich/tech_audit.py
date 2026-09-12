"""Website technical auditor: one polite GET per site, then pure HTML analysis.

``analyze_html`` is a pure function (easy to test with fixtures); ``audit_website`` adds the
network part: robots.txt, HTTPS fallback, timing and optional PageSpeed Insights.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from coldlead.settings import USER_AGENT

PAGESPEED_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

BOOKING_WIDGETS = (
    "thefork",
    "lafourchette",
    "quandoo",
    "opentable",
    "resdiary",
    "sevenrooms",
    "zenchef",
    "octorate",
    "simplebooking",
    "vertical-booking",
    "verticalbooking",
    "bookingexpert",
    "synxis",
    "cloudbeds",
    "beddy",
    "ericsoft",
    "passepartout",
    "calendly",
    "fresha",
    "treatwell",
    "booksy",
    "uala",
    "planity",
    "miodottore",
    "doctolib",
    "setmore",
    "acuityscheduling",
    "simplybook",
    "bokun",
    "fareharbor",
    "checkfront",
    "rezdy",
    "clickandboat",
    "samboat",
    "nautal",
    "prenota-online",
)
BOOKING_WORDS = r"prenota|book now|book online|reserve|riserva|preventivo|get a quote|check availability|disponibilit"
CHAT_WIDGETS = (
    "tidio",
    "crisp.chat",
    "intercom",
    "drift.com",
    "tawk.to",
    "livechatinc",
    "zopim",
    "zendesk",
    "hs-scripts",
    "chatbase",
    "voiceflow",
    "botpress",
    "landbot",
    "manychat",
    "chatra",
    "smartsupp",
    "userlike",
    "freshchat",
    "olark",
    "jivosite",
    "gorgias",
)
LANG_SWITCHERS = (
    "wpml",
    "polylang",
    "gtranslate",
    "weglot",
    "translatepress",
    "lang-switch",
    "language-switcher",
)
AGENCY_PATTERNS = (
    r"(?:realizzat[oa]|sviluppat[oa]|progettat[oa]|creat[oa]|design(?:ed)?|made|developed|built|powered|web design)"
    r"\s+(?:da|by|con)\s+([A-Z][\w&.\- ]{2,40})",
    r"(?:web agency|digital agency|agenzia web)\s*[:\-]?\s*([A-Z][\w&.\- ]{2,40})",
)
NOT_AGENCIES = (
    "wordpress",
    "wix",
    "squarespace",
    "shopify",
    "joomla",
    "jimdo",
    "webflow",
    "google",
    "elementor",
)
PDF_MENU_WORDS = r"men[uù]|listino|carta|price|prezzi|tariff|brochure|catalog"


@dataclass
class AuditResult:
    url: str
    signals: dict = field(default_factory=dict)
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    reachable: bool = True


def normalize_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = f"https://{url}"
    return url


def detect_cms(html: str, soup: BeautifulSoup) -> str:
    generator = soup.find("meta", attrs={"name": re.compile("^generator$", re.I)})
    gen = (generator.get("content") or "").strip() if generator else ""
    low = html.lower()
    builder = next((b for b in ("Elementor", "Divi", "WPBakery") if b.lower() in low), None)
    if gen.lower().startswith("wordpress") or "wp-content" in low or "wp-includes" in low:
        version = re.search(r"wordpress\s*([\d.]+)", gen, re.I)
        base = f"WordPress {version.group(1)}" if version else "WordPress"
        return f"{base} ({builder})" if builder else base
    if "joomla" in gen.lower() or "/media/jui/" in low or "joomla" in low:
        return gen.replace("! - Open Source Content Management", "").strip() or "Joomla"
    if gen.lower().startswith("drupal") or "drupal-settings-json" in low:
        return gen or "Drupal"
    for marker, label in (
        ("wix.com", "Wix"),
        ("static.wixstatic", "Wix"),
        ("squarespace", "Squarespace"),
        ("cdn.shopify", "Shopify"),
        ("webflow", "Webflow"),
        ("jimdo", "Jimdo"),
        ("weebly", "Weebly"),
        ("prestashop", "PrestaShop"),
        ("magento", "Magento"),
        ("/_next/", "Next.js"),
        ("__nuxt", "Nuxt"),
        ("gatsby", "Gatsby"),
        ("astro-island", "Astro"),
        ("ghost-", "Ghost"),
        ("framerusercontent", "Framer"),
    ):
        if marker in low:
            return label
    return gen or "Custom / Static"


def _find_agency(soup: BeautifulSoup) -> str | None:
    footer = (
        soup.find("footer")
        or soup.find(attrs={"id": re.compile("footer", re.I)})
        or soup.find(attrs={"class": re.compile("footer", re.I)})
    )
    text = " ".join((footer or soup).get_text(" ", strip=True).split())[-1500:]
    for pattern in AGENCY_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            credit = match.group(1).strip(" .-|")
            credit = re.split(r"\s{2,}| \| | - |©|P\.? ?IVA", credit)[0].strip()
            if credit and not any(credit.lower().startswith(n) for n in NOT_AGENCIES):
                return credit
    return None


def estimate_performance(
    html: str, soup: BeautifulSoup, cms: str, mobile: bool, elapsed_ms: int | None
) -> int:
    """Heuristic Lighthouse-like score when PageSpeed is unavailable. Transparent by design."""
    score = 92.0
    size_kb = len(html.encode("utf-8", errors="ignore")) / 1024
    score -= min(25, max(0, (size_kb - 150) / 25))
    scripts = len(soup.find_all("script"))
    score -= min(15, max(0, scripts - 15) * 0.6)
    styles = len(soup.find_all("link", rel=lambda v: v and "stylesheet" in v))
    score -= min(8, max(0, styles - 6) * 0.8)
    if elapsed_ms is not None:
        score -= min(20, max(0, (elapsed_ms - 500) / 100))
    low = cms.lower()
    if any(b in low for b in ("elementor", "divi", "wpbakery")):
        score -= 15
    elif "wix" in low or "joomla" in low:
        score -= 12
    if not mobile:
        score -= 12
    return int(max(10, min(98, round(score))))


def analyze_html(html: str, base_url: str, elapsed_ms: int | None = None) -> AuditResult:
    """Pure analysis of a homepage. No network access."""
    soup = BeautifulSoup(html, "html.parser")
    low = html.lower()
    result = AuditResult(url=base_url)
    s = result.signals

    s["has_website"] = True
    s["website_url"] = base_url
    s["has_ssl"] = base_url.lower().startswith("https://")
    s["mobile_friendly"] = (
        soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)}) is not None
    )
    s["cms_stack"] = detect_cms(html, soup)

    hreflangs = {
        (tag.get("hreflang") or "").lower()[:2]
        for tag in soup.find_all("link", attrs={"hreflang": True})
    } - {"", "x-"}
    lang_links = {
        m.group(1)
        for a in soup.find_all("a", href=True)
        if (
            m := re.search(
                r"(?:^|/)(en|de|fr|es|ru|nl|zh)(?:/|$|-)", urlparse(a["href"]).path.lower()
            )
        )
    }
    s["has_multilingual"] = (
        len(hreflangs) >= 2 or bool(lang_links) or any(w in low for w in LANG_SWITCHERS)
    )

    widget = next((w for w in BOOKING_WIDGETS if w in low), None)
    booking_form = any(
        form.find("input", attrs={"type": re.compile("date|datetime-local", re.I)})
        or re.search(BOOKING_WORDS, form.get_text(" ").lower())
        for form in soup.find_all("form")
    )
    s["has_booking_system"] = bool(widget or booking_form)
    if widget:
        result.notes.append(f"Booking widget detected: {widget}")

    chat = next((w for w in CHAT_WIDGETS if w in low), None)
    s["has_ai_chat"] = bool(chat)
    if chat:
        result.notes.append(f"Chat widget detected: {chat}")

    s["has_pdf_menu"] = any(
        a["href"].lower().split("?")[0].endswith(".pdf")
        and re.search(PDF_MENU_WORDS, (a["href"] + " " + a.get_text(" ")).lower())
        for a in soup.find_all("a", href=True)
    )
    s["has_contact_form"] = any(
        form.find("textarea") or form.find("input", attrs={"type": "email"})
        for form in soup.find_all("form")
    )
    s["footer_agency_credit"] = _find_agency(soup)
    s["page_weight_kb"] = round(len(html.encode("utf-8", errors="ignore")) / 1024)

    evidence = []
    if "fbevents.js" in low or re.search(r"fbq\(\s*['\"]init", low):
        evidence.append("Meta Pixel installed")
    if re.search(r"\baw-\d{6,}", low) or "googleadservices.com" in low:
        evidence.append("Google Ads conversion tag")
    s["ads_evidence"] = evidence
    s["is_running_ads"] = True if evidence else None

    links = [a["href"] for a in soup.find_all("a", href=True)]
    result.emails = sorted({h[7:].split("?")[0] for h in links if h.lower().startswith("mailto:")})[
        :3
    ]
    result.phones = sorted({h[4:].strip() for h in links if h.lower().startswith("tel:")})[:3]
    for label, pattern in (
        ("WhatsApp", r"wa\.me/|api\.whatsapp\.com|whatsapp://"),
        ("LinkedIn", r"linkedin\.com/"),
        ("Instagram", r"instagram\.com/"),
        ("Facebook", r"facebook\.com/"),
    ):
        if any(re.search(pattern, h, re.I) for h in links):
            result.channels.append(label)

    s["lighthouse_performance"] = estimate_performance(
        html, soup, s["cms_stack"], s["mobile_friendly"], elapsed_ms
    )
    s["performance_source"] = "estimated"
    if elapsed_ms is not None:
        s["response_time_ms"] = elapsed_ms
    return result


def robots_allows(client: httpx.Client, url: str) -> bool:
    parsed = urlparse(url)
    try:
        resp = client.get(f"{parsed.scheme}://{parsed.netloc}/robots.txt", timeout=5)
    except httpx.HTTPError:
        return True
    if resp.status_code >= 400:
        return True
    parser = RobotFileParser()
    parser.parse(resp.text.splitlines())
    return parser.can_fetch(USER_AGENT, url)


def pagespeed_score(client: httpx.Client, url: str, api_key: str | None) -> int | None:
    params = {"url": url, "strategy": "mobile", "category": "performance"}
    if api_key:
        params["key"] = api_key
    try:
        resp = client.get(PAGESPEED_URL, params=params, timeout=60)
        resp.raise_for_status()
        score = resp.json()["lighthouseResult"]["categories"]["performance"]["score"]
        return round(float(score) * 100)
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return None


def audit_website(
    url: str,
    client: httpx.Client | None = None,
    *,
    pagespeed: bool = False,
    pagespeed_key: str | None = None,
    respect_robots: bool = True,
) -> AuditResult:
    owns_client = client is None
    client = client or httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "it,en;q=0.8"},
        timeout=10.0,
        follow_redirects=True,
    )
    target = normalize_url(url)
    try:
        if respect_robots and not robots_allows(client, target):
            result = AuditResult(url=target, signals={"has_website": True, "website_url": target})
            result.notes.append("robots.txt disallows automated audits: signals left unknown")
            return result
        started = time.perf_counter()
        try:
            resp = client.get(target)
        except httpx.ConnectError:
            if not target.startswith("https://"):
                raise
            target = "http://" + target[len("https://") :]
            resp = client.get(target)
        elapsed = int((time.perf_counter() - started) * 1000)
        final_url = str(resp.url)
        if resp.status_code >= 400:
            result = AuditResult(url=final_url, reachable=False)
            result.signals = {
                "has_website": True,
                "website_url": final_url,
                "has_ssl": final_url.startswith("https"),
            }
            result.notes.append(f"Website answered HTTP {resp.status_code}")
            return result
        result = analyze_html(resp.text, final_url, elapsed)
        if pagespeed or pagespeed_key:
            score = pagespeed_score(client, final_url, pagespeed_key)
            if score is not None:
                result.signals["lighthouse_performance"] = score
                result.signals["performance_source"] = "lighthouse"
        return result
    except httpx.HTTPError as exc:
        result = AuditResult(url=target, reachable=False)
        result.signals = {"has_website": True, "website_url": target}
        result.notes.append(f"Website unreachable: {type(exc).__name__}")
        return result
    finally:
        if owns_client:
            client.close()
