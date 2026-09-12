from __future__ import annotations

import json

import httpx
import pytest

from coldlead.providers.demo import demo_leads
from coldlead.providers.google_places import GooglePlacesProvider, place_to_lead
from coldlead.providers.osm import (
    OSMProvider,
    ProviderError,
    build_query,
    element_to_lead,
    tag_filters,
)


def test_demo_is_deterministic_and_marked():
    a = demo_leads("Ristorante", "Firenze", 10)
    b = demo_leads("Ristorante", "Firenze", 10)
    assert [x.model_dump(exclude={"collected_at"}) for x in a] == [
        x.model_dump(exclude={"collected_at"}) for x in b
    ]
    assert [x.id for x in demo_leads("ristorante", "firenze", 10)] == [
        x.id for x in a
    ]  # case-insensitive
    assert all(lead.source == "demo" for lead in a)
    assert all(".example" in (lead.raw_signals.website_url or ".example") for lead in a)
    assert len({lead.company.name for lead in a}) == 10
    assert len({lead.id for lead in a}) == 10


def test_demo_covers_the_spectrum():
    leads = demo_leads("Dentista", "Milano", 12)
    assert any(not ld.raw_signals.has_website for ld in leads)
    assert any(ld.raw_signals.is_toxic_owner for ld in leads)
    assert any(ld.raw_signals.footer_agency_credit for ld in leads)
    assert any(ld.raw_signals.business_status == "IN_LIQUIDATION" for ld in leads)
    assert any(ld.raw_signals.is_chain for ld in leads)


@pytest.mark.parametrize("limit", [0, 1, 7, 60])
def test_demo_limit(limit):
    assert len(demo_leads("Palestra", "Torino", limit)) == limit


def test_osm_tag_filters():
    assert tag_filters("Studio dentistico") == ['["amenity"="dentist"]', '["healthcare"="dentist"]']
    assert tag_filters("Ristorante di pesce") == ['["amenity"="restaurant"]']
    assert tag_filters("Noleggio barche")[0].startswith('["shop"~"boat')
    assert tag_filters('Weird "niche"') == ['["name"~"Weird niche",i]']


def test_osm_build_query():
    q = build_query(['["amenity"="dentist"]'], 3600044915, (0, 0, 0, 0), 30)
    assert "area(id:3600044915)->.a;" in q
    assert 'nwr["amenity"="dentist"]["name"](area.a);' in q
    assert q.endswith("out tags 30;")
    bbox = build_query(['["shop"="boat"]'], None, (44.3, 44.4, 9.1, 9.3), 10)
    assert "(44.3,9.1,44.4,9.3)" in bbox


def test_osm_element_to_lead():
    lead = element_to_lead(
        {
            "type": "node",
            "id": 1,
            "tags": {
                "name": "Dental Clinic Rossi S.r.l.",
                "website": "dentalrossi.example",
                "phone": "+39 010 123;+39 010 456",
                "addr:street": "Via Roma",
                "addr:housenumber": "1",
                "addr:city": "Genova",
                "brand": "DentalPro",
            },
        },
        "Dentista",
        "Genova",
    )
    assert lead.raw_signals.website_url == "https://dentalrossi.example"
    assert lead.company.phone == "+39 010 123"
    assert lead.company.legal_form.value == "S.r.l."
    assert lead.raw_signals.is_chain is True
    assert lead.company.address == "Via Roma 1, Genova"
    assert element_to_lead({"type": "node", "id": 2, "tags": {}}, "x", "y") is None


def test_osm_search_with_mock_network():
    def handler(request: httpx.Request) -> httpx.Response:
        if "nominatim" in request.url.host:
            return httpx.Response(
                200,
                json=[
                    {
                        "osm_type": "relation",
                        "osm_id": 44915,
                        "name": "Genova",
                        "boundingbox": ["44.3", "44.5", "8.6", "9.1"],
                    }
                ],
            )
        body = request.content.decode()
        assert "area" in body
        return httpx.Response(
            200,
            json={
                "elements": [
                    {"type": "node", "id": 1, "tags": {"name": "B Dentist", "phone": "1"}},
                    {
                        "type": "node",
                        "id": 2,
                        "tags": {"name": "A Dentist", "website": "https://a.example"},
                    },
                    {"type": "node", "id": 3, "tags": {"name": "A Dentist"}},  # duplicate name
                ]
            },
        )

    provider = OSMProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    leads = provider.search("Dentista", "Genova", 5)
    assert [ld.company.name for ld in leads] == [
        "A Dentist",
        "B Dentist",
    ]  # website first, deduplicated
    assert leads[0].source == "osm"


def test_osm_retries_rate_limit_and_falls_back(monkeypatch):
    monkeypatch.setattr("coldlead.providers.osm.time.sleep", lambda s: None)
    hits = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "nominatim" in request.url.host:
            return httpx.Response(
                200,
                json=[
                    {
                        "osm_type": "node",
                        "osm_id": 1,
                        "name": "X",
                        "boundingbox": ["1", "2", "3", "4"],
                    }
                ],
            )
        hits.append(request.url.host)
        if request.url.host == "overpass-api.de":
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(
            200, json={"elements": [{"type": "node", "id": 9, "tags": {"name": "Ok"}}]}
        )

    leads = OSMProvider(client=httpx.Client(transport=httpx.MockTransport(handler))).search(
        "Bar", "X", 3
    )
    assert [ld.company.name for ld in leads] == ["Ok"]
    assert hits == ["overpass-api.de", "overpass-api.de", "overpass.private.coffee"]


def test_osm_unknown_location():
    provider = OSMProvider(
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])))
    )
    with pytest.raises(ProviderError, match="not found"):
        provider.search("Bar", "Atlantide", 3)


def test_google_places_pagination():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        assert request.headers["X-Goog-Api-Key"] == "k"
        assert "places.websiteUri" in request.headers["X-Goog-FieldMask"]
        page = [
            {
                "id": f"p{len(calls)}{i}",
                "displayName": {"text": f"Hotel {len(calls)}{i}"},
                "websiteUri": "https://h.example",
                "rating": 4.5,
                "userRatingCount": 10,
                "businessStatus": "OPERATIONAL",
            }
            for i in range(body["pageSize"])
        ]
        return httpx.Response(
            200, json={"places": page, "nextPageToken": "t" if len(calls) == 1 else None}
        )

    provider = GooglePlacesProvider(
        "k", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    leads = provider.search("Hotel", "Como", 25)
    assert len(leads) == 25
    assert calls[1]["pageToken"] == "t"
    assert leads[0].raw_signals.average_rating == 4.5


def test_google_error_and_missing_key():
    with pytest.raises(ProviderError):
        GooglePlacesProvider("")
    handler = lambda r: httpx.Response(403, json={"error": {"message": "API key not valid"}})  # noqa: E731
    provider = GooglePlacesProvider(
        "bad", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(ProviderError, match="API key not valid"):
        provider.search("Hotel", "Como", 3)


def test_place_to_lead_closed():
    lead = place_to_lead(
        {"id": "x", "displayName": {"text": "Old Bar"}, "businessStatus": "CLOSED_PERMANENTLY"},
        "Bar",
        "Asti",
    )
    assert lead.raw_signals.business_status == "CLOSED_PERMANENTLY"
    assert not lead.raw_signals.has_website
