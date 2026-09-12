from __future__ import annotations

import httpx

from coldlead.enrich.tech_audit import analyze_html, audit_website, detect_cms, normalize_url
from coldlead.pipeline import merge_audit
from tests.conftest import make_lead

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


def test_detect_cms_variants():
    from bs4 import BeautifulSoup

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


def _client(handler) -> httpx.Client:
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
