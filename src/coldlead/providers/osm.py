"""OpenStreetMap provider: free, key-less live discovery via Nominatim + Overpass.

Follows the OSMF usage policies: identifying User-Agent, one geocoding request per search,
modest result sizes. Data © OpenStreetMap contributors (ODbL).
"""

from __future__ import annotations

import time

import httpx

from coldlead import knowledge
from coldlead.models import Company, Lead, RawSignals, make_lead_id
from coldlead.settings import USER_AGENT

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

# Specific keywords first (more precise tags), then category-wide fallbacks.
KEYWORD_TAGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dent", ('["amenity"="dentist"]', '["healthcare"="dentist"]')),
    ("veterinar", ('["amenity"="veterinary"]',)),
    ("pizzeria", ('["amenity"="restaurant"]["cuisine"~"pizza"]',)),
    ("sushi", ('["amenity"="restaurant"]["cuisine"~"sushi|japanese"]',)),
    ("gelat", ('["amenity"="ice_cream"]', '["shop"="ice_cream"]')),
    ("gioiell", ('["shop"="jewelry"]',)),
    ("jewel", ('["shop"="jewelry"]',)),
    ("ottic", ('["shop"="optician"]',)),
    ("fiorist", ('["shop"="florist"]',)),
    ("parrucch", ('["shop"="hairdresser"]',)),
    ("barber", ('["shop"="hairdresser"]',)),
    ("avvocat", ('["office"="lawyer"]',)),
    ("lawyer", ('["office"="lawyer"]',)),
    ("commercialist", ('["office"~"accountant|tax_advisor"]',)),
    ("notai", ('["office"="notary"]',)),
    ("architett", ('["office"="architect"]',)),
    ("assicuraz", ('["office"="insurance"]',)),
    ("agenzia viaggi", ('["shop"="travel_agency"]', '["office"="travel_agent"]')),
    ("camping", ('["tourism"="camp_site"]',)),
    ("b&b", ('["tourism"="guest_house"]',)),
    ("ncc", ('["amenity"="taxi"]', '["office"="taxi"]')),
    ("taxi", ('["amenity"="taxi"]',)),
    ("stabilimento balneare", ('["leisure"="beach_resort"]',)),
)

CATEGORY_TAGS: dict[str, tuple[str, ...]] = {
    "nautical": (
        '["shop"~"boat|boat_rental"]',
        '["amenity"="boat_rental"]',
        '["leisure"="marina"]',
        '["craft"="boatbuilder"]',
    ),
    "real_estate": ('["office"="estate_agent"]', '["shop"="estate_agent"]'),
    "hospitality": ('["tourism"~"^(hotel|guest_house|motel|apartment|chalet|hostel)$"]',),
    "restaurant": ('["amenity"="restaurant"]',),
    "cafe_bar": ('["amenity"~"^(bar|cafe|pub)$"]', '["shop"~"pastry|bakery"]'),
    "clinic": ('["amenity"~"^(clinic|doctors|dentist)$"]', '["healthcare"]'),
    "beauty": ('["shop"~"^(beauty|hairdresser|massage|cosmetics)$"]', '["leisure"="spa"]'),
    "professional": ('["office"~"^(lawyer|accountant|notary|architect|consulting|tax_advisor)$"]',),
    "fitness": ('["leisure"~"^(fitness_centre|sports_centre)$"]',),
    "automotive": ('["shop"~"^(car|car_repair|motorcycle)$"]', '["amenity"~"^(car_rental|taxi)$"]'),
    "retail": ('["shop"~"^(clothes|boutique|jewelry|optician|shoes|gift|florist)$"]',),
    "events": ('["amenity"="events_venue"]', '["craft"="photographer"]', '["shop"="photo"]'),
}


class ProviderError(RuntimeError):
    pass


def tag_filters(niche: str) -> list[str]:
    for keyword, tags in KEYWORD_TAGS:
        if knowledge.keyword_in(keyword, niche):
            return list(tags)
    category = knowledge.detect_category(niche)
    if category in CATEGORY_TAGS:
        return list(CATEGORY_TAGS[category])
    safe = niche.replace('"', "").replace("\\", "").strip()
    return [f'["name"~"{safe}",i]']


def build_query(
    filters: list[str], area_id: int | None, bbox: tuple[float, ...], limit: int
) -> str:
    if area_id is not None:
        scope, selector = f"area(id:{area_id})->.a;", "(area.a)"
    else:
        south, north, west, east = bbox
        scope, selector = "", f"({south},{west},{north},{east})"
    body = "".join(f'nwr{f}["name"]{selector};' for f in filters)
    return f"[out:json][timeout:25];{scope}({body});out tags {limit};"


def geocode(client: httpx.Client, location: str) -> tuple[int | None, tuple[float, ...], str]:
    resp = client.get(NOMINATIM_URL, params={"q": location, "format": "jsonv2", "limit": 1})
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ProviderError(f"Location '{location}' not found on OpenStreetMap")
    place = results[0]
    south, north, west, east = (float(x) for x in place["boundingbox"])
    osm_id = int(place["osm_id"])
    area_id = {"relation": 3_600_000_000 + osm_id, "way": 2_400_000_000 + osm_id}.get(
        place["osm_type"]
    )
    city = place.get("name") or location
    return area_id, (south, north, west, east), city


def _first(tags: dict[str, str], *keys: str) -> str:
    for key in keys:
        if tags.get(key):
            return tags[key].split(";")[0].strip()
    return ""


def element_to_lead(element: dict, niche: str, city: str) -> Lead | None:
    tags = element.get("tags", {})
    name = tags.get("name")
    if not name:
        return None
    website = _first(tags, "website", "contact:website", "url")
    if website and not website.startswith(("http://", "https://")):
        website = f"https://{website}"
    street = " ".join(x for x in (tags.get("addr:street"), tags.get("addr:housenumber")) if x)
    address = ", ".join(x for x in (street, tags.get("addr:postcode"), tags.get("addr:city")) if x)
    phone = _first(tags, "phone", "contact:phone", "contact:mobile")
    email = _first(tags, "email", "contact:email")
    channels = [
        label
        for label, key in (
            ("Phone", phone),
            ("Email", email),
            ("WhatsApp", _first(tags, "contact:whatsapp")),
            ("Facebook", _first(tags, "contact:facebook")),
            ("Instagram", _first(tags, "contact:instagram")),
        )
        if key
    ]
    status = None
    if tags.get("disused:shop") or tags.get("disused:amenity") or tags.get("abandoned"):
        status = "CLOSED_PERMANENTLY"
    return Lead(
        id=make_lead_id("osm", str(element.get("type")), str(element.get("id"))),
        company=Company(
            name=name,
            niche=niche,
            city=tags.get("addr:city") or city,
            address=address,
            phone=phone,
            email=email,
            legal_form=knowledge.parse_legal_form(tags.get("operator", "") + " " + name),
            contact_channels=channels,
        ),
        raw_signals=RawSignals(
            has_website=bool(website),
            website_url=website or None,
            is_chain=bool(tags.get("brand") or tags.get("brand:wikidata")),
            business_status=status or "OPERATIONAL",
        ),
        source="osm",
    )


class OSMProvider:
    name = "osm"

    def __init__(self, client: httpx.Client | None = None, timeout: float = 30.0) -> None:
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "it,en"}, timeout=timeout
        )

    def _overpass(self, query: str) -> list[dict]:
        """Try each public Overpass instance; retry once on 429/504 honouring Retry-After."""
        last_error: Exception | None = None
        for url in OVERPASS_URLS:
            for attempt in range(2):
                try:
                    resp = self.client.post(url, data={"data": query})
                    if resp.status_code in (429, 504) and attempt == 0:
                        time.sleep(min(float(resp.headers.get("Retry-After") or 2), 5.0))
                        continue
                    resp.raise_for_status()
                    return resp.json().get("elements", [])
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
                    break
        raise ProviderError(
            f"Overpass API unavailable ({last_error}). Try again later or use --source demo."
        )

    def search(self, niche: str, location: str, limit: int = 10) -> list[Lead]:
        area_id, bbox, city = geocode(self.client, location)
        elements = self._overpass(
            build_query(tag_filters(niche), area_id, bbox, max(limit * 3, 30))
        )

        leads, seen = [], set()
        for element in elements:
            lead = element_to_lead(element, niche, city)
            if lead and lead.company.name.lower() not in seen:
                seen.add(lead.company.name.lower())
                leads.append(lead)
        # Most contactable first: website and phone make a lead actionable.
        leads.sort(
            key=lambda ld: (not ld.raw_signals.has_website, not ld.company.phone, ld.company.name)
        )
        return leads[:limit]
