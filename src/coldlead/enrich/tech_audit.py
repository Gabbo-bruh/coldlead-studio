"""Website technical auditor: one polite GET per site, then pure HTML analysis.

``analyze_html`` is a pure function (easy to test with fixtures); ``audit_website`` adds the
network part: robots.txt, HTTPS fallback, timing and optional PageSpeed Insights.

The URLs audited here come from third parties (map data, imported lists, an AI agent that may
have read a hostile page), so every request is SSRF-guarded: only ``http``/``https``, only public
IP addresses — checked before each request, at every redirect hop and again at connection time —
and never more than :data:`MAX_RESPONSE_BYTES` read into memory.
"""

from __future__ import annotations

import contextlib
import ipaddress
import re
import socket
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpcore
import httpx
from bs4 import BeautifulSoup

from coldlead.settings import HTTP_HEADERS, USER_AGENT

PAGESPEED_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
ALLOWED_SCHEMES = ("http", "https")
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # a bigger homepage is truncated, never fully buffered
MAX_ROBOTS_BYTES = 512 * 1024  # Google also stops reading robots.txt after 500 KiB
MAX_REDIRECTS = 5

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
    """Add ``https://`` to bare hosts. Other explicit schemes are kept, so the guard rejects them."""
    url = url.strip()
    if not re.match(r"^[a-z][a-z0-9+.\-]*://", url, re.I):
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


def _primary_language(code: str | None) -> str:
    """``"en-GB"`` → ``"en"``; ``"x-default"`` and empty values → ``""``."""
    primary = (code or "").strip().lower().replace("_", "-").split("-")[0]
    return "" if primary in ("", "x") else primary


def detect_multilingual(soup: BeautifulSoup, low: str) -> tuple[bool, str]:
    """Whether a page is multilingual, with the evidence.

    Declared ``<link rel="alternate" hreflang="…">`` alternates are authoritative: they describe
    every language version whatever the server chose to send us. Language links and switcher
    plugins are only a fallback for sites that declare no alternates at all.
    """
    html_tag = soup.find("html")
    own = _primary_language(html_tag.get("lang") if html_tag else None)
    declared = {
        _primary_language(tag.get("hreflang"))
        for tag in soup.find_all("link", attrs={"hreflang": True})
        if "alternate" in [rel.lower() for rel in tag.get("rel") or []]
    } - {""}
    if declared:
        # Pages often omit the self-referencing alternate: count the page's own language too.
        languages = sorted(declared | ({own} if own else set()))
        if len(languages) >= 2:
            return True, f"hreflang alternates ({', '.join(languages)})"
        return False, f"hreflang declares a single language ({languages[0]})"
    # A link to /en/ only proves another version exists if the page itself is not English.
    lang_links = sorted(
        {
            m.group(1)
            for a in soup.find_all("a", href=True)
            if (
                m := re.search(
                    r"(?:^|/)(en|de|fr|es|it|ru|nl|pt|zh)(?:/|$|-)",
                    urlparse(a["href"]).path.lower(),
                )
            )
        }
        - {own}
    )
    if lang_links:
        return True, "links to language versions (" + ", ".join(f"/{c}/" for c in lang_links) + ")"
    switcher = next((w for w in LANG_SWITCHERS if w in low), None)
    if switcher:
        return True, f"language switcher ({switcher})"
    return False, "no alternate language versions found"


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

    s["has_multilingual"], languages_evidence = detect_multilingual(soup, low)
    if s["has_multilingual"]:
        result.notes.append(f"Multilingual: {languages_evidence}")

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


# ------------------------------------------------------------------------------------------
# SSRF guard
# ------------------------------------------------------------------------------------------


class BlockedURLError(ValueError):
    """The URL is not a public ``http(s)`` address: fetching it could reach private services."""


IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def resolve_host(host: str, port: int) -> list[str]:
    """Every IP address ``host`` resolves to, in resolver order (tests replace this)."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def is_public_ip(ip: IPAddress) -> bool:
    """False for loopback, private, link-local (cloud metadata), multicast, reserved,
    unspecified and shared addresses — also when wrapped in IPv4-mapped or 6to4 IPv6."""
    embedded = (ip.ipv4_mapped or ip.sixtofour) if isinstance(ip, ipaddress.IPv6Address) else None
    if embedded is not None and not is_public_ip(embedded):
        return False
    return ip.is_global and not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def public_addresses(host: str, port: int) -> list[str]:
    """The addresses of ``host`` if *all* of them are public; :class:`BlockedURLError` otherwise.

    Raises ``OSError`` when the name does not resolve.
    """
    try:
        candidates, literal = [str(ipaddress.ip_address(host.strip("[]")))], True
    except ValueError:
        candidates, literal = resolve_host(host, port), False
    addresses = [ipaddress.ip_address(a.split("%")[0]) for a in candidates]
    blocked = next((ip for ip in addresses if not is_public_ip(ip)), None)
    if blocked is not None or not addresses:
        where = f"{blocked} is" if literal else f"{host} resolves to"
        raise BlockedURLError(
            f"{where} a non-public address{'' if literal else f' ({blocked})'}: "
            "refusing to fetch it"
        )
    return [str(ip) for ip in addresses]


def ensure_public_url(url: str) -> None:
    """Refuse anything but an ``http(s)`` URL whose host resolves only to public addresses."""
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as exc:
        raise BlockedURLError(f"invalid URL {url!r}") from exc
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise BlockedURLError(
            f"only http and https URLs can be audited, not '{parsed.scheme or '?'}:'"
        )
    if not parsed.host:
        raise BlockedURLError(f"URL without a host: {url!r}")
    try:
        public_addresses(parsed.host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as exc:
        raise httpx.ConnectError(f"cannot resolve {parsed.host}: {exc}") from exc


class _PublicOnlyBackend(httpcore.SyncBackend):
    """Resolve, vet and connect in a single step.

    Checking a hostname and then letting the HTTP stack resolve it again leaves a window for DNS
    rebinding (first answer public, second one 169.254.169.254). Here the socket only ever
    connects to an address that was just verified; TLS still validates the certificate against
    the hostname, because httpcore passes the origin host as SNI.
    """

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable | None = None,
    ) -> httpcore.NetworkStream:
        try:
            addresses = public_addresses(host, port)
        except OSError as exc:
            raise httpcore.ConnectError(f"cannot resolve {host}: {exc}") from exc
        error: Exception | None = None
        for address in addresses:
            try:
                return super().connect_tcp(address, port, timeout, local_address, socket_options)
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                error = exc
        raise error or httpcore.ConnectError(f"cannot connect to {host}")


@contextlib.contextmanager
def _httpx_errors(request: httpx.Request) -> Iterator[None]:
    """Re-raise httpcore exceptions as their httpx namesakes (ConnectError, ReadTimeout…)."""
    try:
        yield
    except Exception as exc:
        if type(exc).__module__.startswith("httpcore"):
            mapped = getattr(httpx, type(exc).__name__, httpx.TransportError)
            if isinstance(mapped, type) and issubclass(mapped, httpx.TransportError):
                raise mapped(str(exc), request=request) from exc
        raise


class _ResponseStream(httpx.SyncByteStream):
    def __init__(self, stream: Iterable[bytes], request: httpx.Request) -> None:
        self._stream, self._request = stream, request

    def __iter__(self) -> Iterator[bytes]:
        with _httpx_errors(self._request):
            yield from self._stream

    def close(self) -> None:
        close = getattr(self._stream, "close", None)
        if close is not None:
            close()


class PublicOnlyTransport(httpx.BaseTransport):
    """An httpx transport that can only open connections to public IP addresses."""

    def __init__(self) -> None:
        self._pool = httpcore.ConnectionPool(
            ssl_context=httpx.create_ssl_context(),
            network_backend=_PublicOnlyBackend(),
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=5.0,
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        with _httpx_errors(request):
            response = self._pool.handle_request(core_request)
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_ResponseStream(response.stream, request),
            extensions=response.extensions,
        )

    def close(self) -> None:
        self._pool.close()


def audit_client(timeout: float = 10.0) -> httpx.Client:
    """The HTTP client for audits: neutral headers, SSRF-safe transport, manual redirects."""
    return httpx.Client(headers=HTTP_HEADERS, timeout=timeout, transport=PublicOnlyTransport())


@dataclass
class Page:
    url: str
    status_code: int
    text: str
    truncated: bool = False


def fetch_page(
    client: httpx.Client,
    url: str,
    *,
    max_bytes: int = MAX_RESPONSE_BYTES,
    timeout: float | None = None,
) -> Page:
    """GET ``url`` safely: every hop (redirects are followed by hand) must pass
    :func:`ensure_public_url`, and at most ``max_bytes`` of decoded body are ever read."""
    options = {} if timeout is None else {"timeout": timeout}
    for _ in range(MAX_REDIRECTS + 1):
        ensure_public_url(url)
        with client.stream("GET", url, follow_redirects=False, **options) as resp:
            if resp.is_redirect:
                request = resp.request
                url = urljoin(str(resp.url), resp.headers["location"])
                continue
            body, truncated = bytearray(), False
            for chunk in resp.iter_bytes():
                body += chunk
                if len(body) > max_bytes:
                    del body[max_bytes:]
                    truncated = True
                    break
            text = bytes(body).decode(resp.encoding or "utf-8", errors="replace")
            return Page(str(resp.url), resp.status_code, text, truncated)
    raise httpx.TooManyRedirects(f"more than {MAX_REDIRECTS} redirects", request=request)


def robots_allows(client: httpx.Client, url: str) -> bool:
    parsed = urlparse(url)
    try:
        page = fetch_page(
            client,
            f"{parsed.scheme}://{parsed.netloc}/robots.txt",
            max_bytes=MAX_ROBOTS_BYTES,
            timeout=5,
        )
    except (httpx.HTTPError, BlockedURLError):
        return True  # no readable robots.txt: nothing forbids the audit
    if page.status_code >= 400:
        return True
    parser = RobotFileParser()
    parser.parse(page.text.splitlines())
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
    client = client or audit_client()
    target = normalize_url(url)
    try:
        ensure_public_url(target)  # fail fast, before even asking for robots.txt
        if respect_robots and not robots_allows(client, target):
            result = AuditResult(url=target, signals={"has_website": True, "website_url": target})
            result.notes.append("robots.txt disallows automated audits: signals left unknown")
            return result
        started = time.perf_counter()
        try:
            page = fetch_page(client, target)
        except httpx.ConnectError:
            if not target.startswith("https://"):
                raise
            target = "http://" + target[len("https://") :]
            page = fetch_page(client, target)
        elapsed = int((time.perf_counter() - started) * 1000)
        final_url = page.url
        if page.status_code >= 400:
            result = AuditResult(url=final_url, reachable=False)
            result.signals = {
                "has_website": True,
                "website_url": final_url,
                "has_ssl": final_url.startswith("https"),
            }
            result.notes.append(f"Website answered HTTP {page.status_code}")
            return result
        result = analyze_html(page.text, final_url, elapsed)
        if page.truncated:
            result.notes.append(
                f"Homepage larger than {MAX_RESPONSE_BYTES // (1024 * 1024)} MB: "
                "only the beginning was analysed"
            )
        if pagespeed or pagespeed_key:
            score = pagespeed_score(client, final_url, pagespeed_key)
            if score is not None:
                result.signals["lighthouse_performance"] = score
                result.signals["performance_source"] = "lighthouse"
        return result
    except BlockedURLError as exc:
        result = AuditResult(url=target, reachable=False)
        result.signals = {"has_website": True, "website_url": target}
        result.notes.append(f"Audit refused: {exc}")
        return result
    except httpx.HTTPError as exc:
        result = AuditResult(url=target, reachable=False)
        result.signals = {"has_website": True, "website_url": target}
        result.notes.append(f"Website unreachable: {type(exc).__name__}")
        return result
    finally:
        if owns_client:
            client.close()
