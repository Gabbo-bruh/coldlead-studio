from __future__ import annotations

import json
from urllib.parse import unquote_plus

import httpx
import pytest

from coldlead.providers.demo import demo_leads
from coldlead.providers.google_places import GooglePlacesProvider, place_to_lead
from coldlead.providers.osm import (
    LocationNotFound,
    OSMProvider,
    ProviderError,
    SearchScope,
    build_query,
    element_to_lead,
    geocode,
    pick_place,
    tag_filters,
)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("coldlead.providers.osm.time.sleep", lambda s: None)


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
    q = build_query(['["amenity"="dentist"]'], SearchScope("area", area_id=3600044915), 30)
    assert "area(id:3600044915)->.a;" in q
    assert 'nwr["amenity"="dentist"]["name"](area.a);' in q
    assert q.endswith("out tags 30;")
    bbox = build_query(['["shop"="boat"]'], SearchScope("bbox", bbox=(44.3, 44.4, 9.1, 9.3)), 10)
    assert "(44.3,9.1,44.4,9.3)" in bbox
    around = build_query(
        ['["shop"="boat"]'], SearchScope("around", point=(44.3, 9.2), radius_m=11_132), 10
    )
    assert "(44.20000,9.06028,44.40000,9.33972)" in around  # indexed bbox, not (around:…)


def test_overpass_error_remark_is_not_an_empty_result():
    def handler(request: httpx.Request) -> httpx.Response:
        if "nominatim" in request.url.host:
            return httpx.Response(200, json=[TIGULLIO[2]])
        if request.url.host == "overpass-api.de":
            return httpx.Response(
                200, json={"elements": [], "remark": "runtime error: Query timed out"}
            )
        return httpx.Response(
            200, json={"elements": [{"type": "node", "id": 7, "tags": {"name": "Marina"}}]}
        )

    provider = OSMProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert [ld.company.name for ld in provider.search("nautico", "Tigullio", 5)] == ["Marina"]


# Real Nominatim answers for "Tigullio": a nightclub in Malta ranks first.
TIGULLIO = [
    {
        "category": "amenity",
        "type": "nightclub",
        "osm_type": "way",
        "osm_id": 1,
        "importance": 0.0001,
        "address": {"country_code": "mt"},
        "name": "Tigullio",
        "boundingbox": ["35.9", "35.91", "14.4", "14.5"],
    },
    {
        "category": "tourism",
        "type": "hotel",
        "osm_type": "node",
        "osm_id": 2,
        "importance": 0.0,
        "address": {"country_code": "it"},
        "name": "Tigullio",
        "boundingbox": ["44.3", "44.31", "9.3", "9.31"],
    },
    {
        "category": "place",
        "type": "locality",
        "osm_type": "node",
        "osm_id": 3,
        "importance": 0.0667,
        "address": {"country_code": "it"},
        "name": "Golfo del Tigullio",
        "lat": "44.325",
        "lon": "9.238",
        "display_name": "Golfo del Tigullio, Santa Margherita Ligure",
        "boundingbox": ["44.31", "44.33", "9.22", "9.24"],
    },
]


def test_pick_place_ignores_venues_named_like_places():
    assert pick_place(TIGULLIO, "IT")["name"] == "Golfo del Tigullio"
    assert pick_place(TIGULLIO[:2], "IT") is None


def test_pick_place_prefers_home_country_but_not_blindly():
    paris_fr = {
        "category": "boundary",
        "type": "administrative",
        "importance": 0.9,
        "address": {"country_code": "fr"},
        "name": "Paris",
    }
    paris_it = {
        "category": "place",
        "type": "hamlet",
        "importance": 0.1,
        "address": {"country_code": "it"},
        "name": "Parisi",
    }
    assert pick_place([paris_it, paris_fr], "IT")["name"] == "Paris"
    como_it = {**paris_it, "name": "Como", "category": "boundary", "importance": 0.5}
    como_us = {**paris_fr, "name": "Como", "importance": 0.55, "address": {"country_code": "us"}}
    assert pick_place([como_us, como_it], "IT")["name"] == "Como"


def test_geocode_scopes():
    def client_for(results):
        return httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=results))
        )

    scope = geocode(client_for(TIGULLIO), "Tigullio", "IT")
    assert scope.kind == "around" and scope.radius_m == 10_000 and scope.point == (44.325, 9.238)
    assert "Golfo del Tigullio" in scope.label
    boundary = [
        {
            "category": "boundary",
            "type": "administrative",
            "osm_type": "relation",
            "osm_id": 43040,
            "importance": 0.4,
            "address": {"country_code": "it"},
            "name": "Chiavari",
            "boundingbox": ["44.30", "44.34", "9.28", "9.35"],
        }
    ]
    assert geocode(client_for(boundary), "Chiavari").area_id == 3_600_043_040
    bay = [{**boundary[0], "category": "natural", "type": "bay", "osm_type": "way", "name": "Baia"}]
    assert geocode(client_for(bay), "Baia").kind == "bbox"
    with pytest.raises(LocationNotFound):
        geocode(client_for(TIGULLIO[:2]), "Tigullio")


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
                        "category": "boundary",
                        "type": "administrative",
                        "osm_type": "relation",
                        "osm_id": 44915,
                        "importance": 0.6,
                        "address": {"country_code": "it"},
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
    leads = provider.search("Dentista", "Genova", 5, expand=False)
    assert [ld.company.name for ld in leads] == [
        "A Dentist",
        "B Dentist",
    ]  # website first, deduplicated
    assert leads[0].source == "osm"


def test_osm_retries_rate_limit_and_falls_back(monkeypatch):
    hits = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "nominatim" in request.url.host:
            return httpx.Response(
                200,
                json=[
                    {
                        "category": "place",
                        "type": "town",
                        "osm_type": "node",
                        "osm_id": 1,
                        "lat": "44.3",
                        "lon": "9.2",
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
        "Bar", "X", 3, expand=False
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


def _osm_client(elements_by_call):
    """Nominatim answers with a municipality; each Overpass call returns the next batch."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "reverse" in request.url.path:
            return httpx.Response(200, json={"address": {"town": "Camogli"}})
        if "nominatim" in request.url.host:
            return httpx.Response(
                200,
                json=[
                    {
                        "category": "boundary",
                        "type": "administrative",
                        "osm_type": "relation",
                        "osm_id": 5,
                        "importance": 0.4,
                        "address": {"country_code": "it"},
                        "name": "Camogli",
                        "lat": "44.35",
                        "lon": "9.15",
                        "boundingbox": ["44.34", "44.36", "9.13", "9.17"],
                    }
                ],
            )
        calls.append(unquote_plus(request.content.decode()))
        batch = elements_by_call[min(len(calls), len(elements_by_call)) - 1]
        return httpx.Response(
            200,
            json={
                "elements": [{"type": "node", "id": i, "tags": {"name": name}} for i, name in batch]
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_osm_widens_search_when_too_few_results():
    client, calls = _osm_client([[(1, "A")], [(1, "A"), (2, "B"), (3, "C")], [(4, "D"), (5, "E")]])
    provider = OSMProvider(client=client)
    leads = provider.search("Ristorante", "Camogli", 4)
    assert len(calls) == 3  # municipality, then 5 km, then 10 km
    assert "area(id:" in calls[0] and "area(id:" not in calls[1]
    assert {ld.company.name for ld in leads} == {"A", "B", "C", "D"}
    assert "widened the search to 5 km" in provider.notes[0]
    assert provider.last_scope.radius_m == 10_000


def test_osm_no_widening_when_enough_or_disabled():
    client, calls = _osm_client([[(1, "A"), (2, "B")]])
    OSMProvider(client=client).search("Ristorante", "Camogli", 2)
    assert len(calls) == 1
    client, calls = _osm_client([[(1, "A")]])
    OSMProvider(client=client).search("Ristorante", "Camogli", 9, expand=False)
    assert len(calls) == 1


def test_osm_pin_search():
    client, calls = _osm_client([[(1, "A"), (2, "B")]])
    provider = OSMProvider(client=client)
    leads = provider.search("Ristorante", "", 2, near=(44.35, 9.15), radius_m=3000)
    assert len(leads) == 2 and len(calls) == 1
    assert provider.last_scope.name == "Camogli"
    assert "pin 44.3500, 9.1500 near Camogli (3 km radius)" in provider.last_scope.label
    with pytest.raises(LocationNotFound):
        provider.search("Bar", "", 2, near=(123.0, 9.0))


def test_osm_widening_failure_keeps_results():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "nominatim" in request.url.host:
            return httpx.Response(200, json=[TIGULLIO[2]])
        calls.append(request.url.host)
        if len(calls) == 1:
            return httpx.Response(
                200, json={"elements": [{"type": "node", "id": 1, "tags": {"name": "A"}}]}
            )
        return httpx.Response(503)

    provider = OSMProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    leads = provider.search("nautico", "Tigullio", 5)
    assert [ld.company.name for ld in leads] == ["A"]
    assert "Could not widen the search" in provider.notes[-1]
