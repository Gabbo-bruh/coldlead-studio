from __future__ import annotations

import re
import socket

import httpx
import pytest
from bs4 import BeautifulSoup

from coldlead.enrich import tech_audit
from coldlead.enrich.tech_audit import (
    MAX_RESPONSE_BYTES,
    BlockedURLError,
    analyze_html,
    audit_client,
    audit_website,
    detect_cms,
    detect_multilingual,
    ensure_public_url,
    fetch_page,
    normalize_url,
)
from coldlead.pipeline import merge_audit
from tests.conftest import PUBLIC_IP, make_lead

LEGACY_HTML = """<!doctype html><html><head>
<meta name="generator" content="WordPress 4.9.8">
<link rel="stylesheet" href="/wp-content/plugins/elementor/assets/css/frontend.css">
<script>!function(f,b,e,v,n,t,s){}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');fbq('init','123');</script>
<script async src="https://www.googletagmanager.com/gtag/js?id=AW-123456789"></script>
</head><body>
<a href="/menu-estate-2026.pdf">Scarica il nostro menù</a>
<a href="mailto:info@trattoria.example">Scrivici</a>
<a href="tel:+390185000003">Chiama</a>
<a href="https://wa.me/393331234567">WhatsApp</a>
<a href="https://www.instagram.com/trattoria">IG</a>
<form><input type="email" name="email"><textarea></textarea><button>Invia</button></form>
<footer>© 2026 Trattoria da Mario — P.IVA 01234567890 · Sito realizzato da Pixel Web Agency</footer>
</body></html>"""

MODERN_HTML = """<!doctype html><html lang="it"><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="alternate" hreflang="it" href="https://x.example/it/">
<link rel="alternate" hreflang="en" href="https://x.example/en/">
<script src="/_next/static/chunks/main.js"></script>
<script src="https://code.tidio.co/abc.js"></script>
</head><body><iframe src="https://widget.thefork.com/xyz"></iframe>
<footer>© 2026 Ristorante Moderno</footer></body></html>"""


def test_analyze_legacy_site():
    result = analyze_html(LEGACY_HTML, "http://trattoria.example", elapsed_ms=2400)
    s = result.signals
    assert s["cms_stack"] == "WordPress 4.9.8 (Elementor)"
    assert s["has_ssl"] is False
    assert s["mobile_friendly"] is False
    assert s["has_multilingual"] is False
    assert s["has_booking_system"] is False
    assert s["has_ai_chat"] is False
    assert s["has_pdf_menu"] is True
    assert s["has_contact_form"] is True
    assert s["footer_agency_credit"] == "Pixel Web Agency"
    assert s["is_running_ads"] is True
    assert set(s["ads_evidence"]) == {"Meta Pixel installed", "Google Ads conversion tag"}
    assert s["performance_source"] == "estimated"
    assert s["lighthouse_performance"] < 50
    assert result.emails == ["info@trattoria.example"]
    assert result.phones == ["+390185000003"]
    assert {"WhatsApp", "Instagram"} <= set(result.channels)


def test_analyze_modern_site():
    s = analyze_html(MODERN_HTML, "https://x.example", elapsed_ms=300).signals
    assert s["cms_stack"] == "Next.js"
    assert s["has_ssl"] and s["mobile_friendly"] and s["has_multilingual"]
    assert s["has_booking_system"] is True
    assert s["has_ai_chat"] is True
    assert s["footer_agency_credit"] is None
    assert s["is_running_ads"] is None
    assert s["lighthouse_performance"] > 80


def _multilingual(html: str) -> bool:
    return analyze_html(html, "https://x.example").signals["has_multilingual"]


def test_hreflang_alternates_are_authoritative():
    # Two declared languages: multilingual, whatever language the server happened to send.
    assert _multilingual(MODERN_HTML)
    # The self-referencing alternate is often missing: the page's own lang counts too.
    assert _multilingual(
        '<html lang="it"><head><link rel="alternate" hreflang="en-GB" href="/en/"></head></html>'
    )
    # A single declared language wins over a stray /de/ link.
    single = (
        '<html lang="en"><head><link rel="alternate" hreflang="en" href="/">'
        '<link rel="alternate" hreflang="x-default" href="/"></head>'
        '<body><a href="/de/brochure.pdf">Brochure</a></body></html>'
    )
    assert not _multilingual(single)
    soup = BeautifulSoup(single, "html.parser")
    assert detect_multilingual(soup, single.lower()) == (
        False,
        "hreflang declares a single language (en)",
    )
    # hreflang on a non-alternate link (e.g. a stylesheet) is not a declaration.
    assert not _multilingual('<html><head><link rel="stylesheet" hreflang="fr"></head></html>')


def test_multilingual_fallbacks_without_hreflang():
    assert _multilingual('<html lang="it"><body><a href="/en/rooms">English</a></body></html>')
    # A link to the page's own language is not another version.
    assert not _multilingual('<html lang="it"><body><a href="/it/camere">Camere</a></body></html>')
    assert _multilingual('<html><body><div class="gtranslate_wrapper"></div></body></html>')
    notes = analyze_html(MODERN_HTML, "https://x.example").notes
    assert "Multilingual: hreflang alternates (en, it)" in notes


def test_detect_cms_variants():
    for html, expected in [
        ('<meta name="generator" content="Joomla! - Open Source Content Management">', "Joomla"),
        ('<script src="https://static.wixstatic.com/x.js"></script>', "Wix"),
        ('<link href="https://cdn.shopify.com/s.css">', "Shopify"),
        ("<p>hello</p>", "Custom / Static"),
    ]:
        assert detect_cms(html, BeautifulSoup(html, "html.parser")) == expected


def test_normalize_url():
    assert normalize_url("example.com") == "https://example.com"
    assert normalize_url(" http://a.example ") == "http://a.example"
    assert normalize_url("file:///etc/passwd") == "file:///etc/passwd"  # kept, then refused


def _client(handler) -> httpx.Client:
    # follow_redirects=True on purpose: audits must follow redirects hop by hop regardless.
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_audit_website_with_mock_network():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=MODERN_HTML)

    result = audit_website("x.example", _client(handler))
    assert result.reachable
    assert result.signals["cms_stack"] == "Next.js"
    assert result.signals["website_url"].startswith("https://x.example")


def test_audit_respects_robots():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /")
        raise AssertionError("homepage must not be fetched")

    result = audit_website("https://blocked.example", _client(handler))
    assert "robots.txt" in result.notes[0]
    assert "cms_stack" not in result.signals


def test_audit_https_fallback_to_http():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.scheme == "https":
            raise httpx.ConnectError("ssl handshake failed")
        return httpx.Response(200, text=LEGACY_HTML)

    result = audit_website("old.example", _client(handler), respect_robots=False)
    assert result.signals["has_ssl"] is False
    assert result.url.startswith("http://")


def test_audit_unreachable_and_http_errors():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    result = audit_website("http://down.example", _client(down), respect_robots=False)
    assert not result.reachable and "unreachable" in result.notes[0]

    def error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    result = audit_website("https://err.example", _client(error), respect_robots=False)
    assert not result.reachable and "HTTP 500" in result.notes[0]


def test_pagespeed_overrides_estimate():
    def handler(request: httpx.Request) -> httpx.Response:
        if "pagespeedonline" in str(request.url):
            return httpx.Response(
                200, json={"lighthouseResult": {"categories": {"performance": {"score": 0.37}}}}
            )
        return httpx.Response(200, text=MODERN_HTML)

    result = audit_website(
        "https://x.example", _client(handler), pagespeed=True, respect_robots=False
    )
    assert result.signals["lighthouse_performance"] == 37
    assert result.signals["performance_source"] == "lighthouse"


def test_merge_audit_keeps_provider_data():
    lead = make_lead(cms_stack="Provided CMS", ads_evidence=["manual"])
    audit = analyze_html(LEGACY_HTML, "http://trattoria.example")
    merged = merge_audit(lead, audit)
    assert merged.raw_signals.cms_stack == "Provided CMS"  # not overwritten
    assert merged.raw_signals.has_pdf_menu is True  # filled in
    assert "manual" in merged.raw_signals.ads_evidence
    assert "Instagram" in merged.company.contact_channels


# ------------------------------------------------------------------------------------ SSRF guard

REAL_RESOLVE = tech_audit.resolve_host  # captured before the autouse offline_dns fixture runs

NON_PUBLIC_URLS = [
    "http://127.0.0.1/",
    "http://127.0.0.1:8080/admin",
    "http://10.0.0.8/",
    "http://172.16.5.4/",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/iam/security-credentials/",  # cloud metadata
    "http://0.0.0.0/",
    "http://100.64.0.1/",  # carrier-grade NAT (shared)
    "http://224.0.0.1/",  # multicast
    "http://240.0.0.1/",  # reserved
    "http://[::1]/",
    "http://[fe80::1]/",
    "http://[fd00::1]/",
    "http://[::ffff:127.0.0.1]/",  # IPv4-mapped loopback
    "http://[::ffff:169.254.169.254]/",
    "http://[2002:a00:1::]/",  # 6to4 wrapping 10.0.0.1
]


def _never_called(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"{request.url} must never be requested")


@pytest.mark.parametrize("url", NON_PUBLIC_URLS)
def test_private_and_local_addresses_are_refused(url):
    with pytest.raises(BlockedURLError, match="non-public"):
        ensure_public_url(url)
    result = audit_website(url, _client(_never_called))
    assert not result.reachable
    assert result.notes[0].startswith("Audit refused:")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "gopher://127.0.0.1:70/_stats",
        "dict://127.0.0.1:11211/stats",
        "javascript:alert(1)",
    ],
)
def test_only_http_and_https_are_allowed(url):
    result = audit_website(url, _client(_never_called), respect_robots=False)
    assert not result.reachable
    assert result.notes[0].startswith("Audit refused:")


def test_hostnames_resolving_to_private_addresses_are_refused(monkeypatch):
    answers = {"intranet.example": ["10.1.2.3"], "mixed.example": [PUBLIC_IP, "192.168.0.10"]}
    monkeypatch.setattr(tech_audit, "resolve_host", lambda host, port: answers[host])
    for host in answers:  # every address must be public, not just the first one
        with pytest.raises(BlockedURLError, match="non-public"):
            ensure_public_url(f"https://{host}/")
        assert not audit_website(host, _client(_never_called)).reachable


def test_localhost_is_refused_with_the_real_resolver(monkeypatch):
    monkeypatch.setattr(tech_audit, "resolve_host", REAL_RESOLVE)  # "localhost" resolves offline
    with pytest.raises(BlockedURLError):
        ensure_public_url("http://localhost:8080/admin")


def test_every_redirect_hop_is_checked():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "shop.example":
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/"})
        raise AssertionError("the redirect target must never be requested")

    result = audit_website("https://shop.example/", _client(handler), respect_robots=False)
    assert seen == ["https://shop.example/"]
    assert not result.reachable and "169.254.169.254" in result.notes[0]

    def relative(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"Location": "//127.0.0.1:2375/containers/json"})

    assert "Audit refused" in audit_website("https://a.example", _client(relative)).notes[0]


def test_public_redirects_are_followed_and_capped():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "old.example":
            return httpx.Response(301, headers={"Location": "https://new.example/home"})
        return httpx.Response(200, text=MODERN_HTML)

    result = audit_website("http://old.example", _client(handler), respect_robots=False)
    assert result.reachable and result.url == "https://new.example/home"

    def loop(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": f"/hop{len(request.url.path)}"})

    result = audit_website("https://loop.example", _client(loop), respect_robots=False)
    assert not result.reachable and "TooManyRedirects" in result.notes[0]


def test_response_size_is_capped():
    chunks_sent = 0

    def endless_page():
        nonlocal chunks_sent
        yield b"<html><head><meta name='viewport' content='width=device-width'></head><body>"
        while True:  # a hostile server that never stops sending
            chunks_sent += 1
            yield b"x" * (1024 * 1024)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=endless_page())

    result = audit_website("https://huge.example", _client(handler), respect_robots=False)
    assert result.reachable and result.signals["mobile_friendly"] is True
    assert any("larger than 5 MB" in note for note in result.notes)
    assert chunks_sent <= MAX_RESPONSE_BYTES // (1024 * 1024) + 1

    page = fetch_page(_client(handler), "https://huge.example/", max_bytes=1000)
    assert page.truncated and len(page.text) == 1000


def test_transport_blocks_dns_rebinding_at_connect_time(monkeypatch):
    """The name looked public when checked, but the connection-time answer is the metadata IP."""
    answers = iter([[PUBLIC_IP], ["169.254.169.254"]])
    monkeypatch.setattr(tech_audit, "resolve_host", lambda host, port: next(answers))
    ensure_public_url("http://rebind.example/")  # first answer: public, the pre-check passes
    with (
        audit_client() as client,
        pytest.raises(BlockedURLError, match=re.escape("169.254.169.254")),
    ):
        client.get("http://rebind.example/latest/meta-data/")  # second answer: refused

    with audit_client() as client, pytest.raises(BlockedURLError):
        client.get("http://127.0.0.1:9/")  # literal addresses never reach a socket either


def test_transport_maps_network_errors_to_httpx(monkeypatch):
    def unresolvable(host, port):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(tech_audit, "resolve_host", unresolvable)
    with audit_client() as client, pytest.raises(httpx.ConnectError):
        client.get("https://does-not-exist.example/")
    result = audit_website("https://does-not-exist.example/")
    assert not result.reachable and "ConnectError" in result.notes[0]
