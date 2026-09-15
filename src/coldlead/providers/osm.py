"""OpenStreetMap provider: free, key-less live discovery via Nominatim + Overpass.

Follows the OSMF usage policies: identifying User-Agent, one geocoding request per search,
modest result sizes. Data © OpenStreetMap contributors (ODbL).
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import httpx

from coldlead import knowledge
from coldlead.models import Company, Lead, RawSignals, make_lead_id
from coldlead.settings import HTTP_HEADERS

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
MAX_RADIUS_M = 25_000
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

# Specific keywords first (more precise tags), then category-wide fallbacks.
KEYWORD_TAGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dent", ('["amenity"="dentist"]', '["healthcare"="dentist"]')),
    ("veterinar", ('["amenity"="veterinary"]',)),
    ("vet ", ('["amenity"="veterinary"]',)),
    ("animal hospital", ('["amenity"="veterinary"]',)),
    ("pizzeria", ('["amenity"="restaurant"]["cuisine"~"pizza"]',)),
    ("sushi", ('["amenity"="restaurant"]["cuisine"~"sushi|japanese"]',)),
    ("gelat", ('["amenity"="ice_cream"]', '["shop"="ice_cream"]')),
    ("ice cream", ('["amenity"="ice_cream"]', '["shop"="ice_cream"]')),
    ("gioiell", ('["shop"="jewelry"]',)),
    ("jewel", ('["shop"="jewelry"]',)),
    ("ottic", ('["shop"="optician"]',)),
    ("optician", ('["shop"="optician"]',)),
    ("eyewear", ('["shop"="optician"]',)),
    ("fiorist", ('["shop"="florist"]',)),
    ("florist", ('["shop"="florist"]',)),
    ("flower", ('["shop"="florist"]',)),
    ("parrucch", ('["shop"="hairdresser"]',)),
    ("hairdress", ('["shop"="hairdresser"]',)),
    ("hair salon", ('["shop"="hairdresser"]',)),
    ("barber", ('["shop"="hairdresser"]',)),
    ("avvocat", ('["office"="lawyer"]',)),
    ("lawyer", ('["office"="lawyer"]',)),
    ("attorney", ('["office"="lawyer"]',)),
    ("law firm", ('["office"="lawyer"]',)),
    ("commercialist", ('["office"~"accountant|tax_advisor"]',)),
    ("accountant", ('["office"~"accountant|tax_advisor"]',)),
    ("cpa ", ('["office"~"accountant|tax_advisor"]',)),
    ("notai", ('["office"="notary"]',)),
    ("notary", ('["office"="notary"]',)),
    ("architett", ('["office"="architect"]',)),
    ("architect", ('["office"="architect"]',)),
    ("assicuraz", ('["office"="insurance"]',)),
    ("insurance", ('["office"="insurance"]',)),
    ("agenzia viaggi", ('["shop"="travel_agency"]', '["office"="travel_agent"]')),
    ("travel agen", ('["shop"="travel_agency"]', '["office"="travel_agent"]')),
    ("camping", ('["tourism"="camp_site"]',)),
    ("campground", ('["tourism"="camp_site"]',)),
    ("campsite", ('["tourism"="camp_site"]',)),
    ("b&b", ('["tourism"="guest_house"]',)),
    ("ncc", ('["amenity"="taxi"]', '["office"="taxi"]')),
    ("chauffeur", ('["amenity"="taxi"]', '["office"="taxi"]')),
    ("limousine", ('["amenity"="taxi"]', '["office"="taxi"]')),
    ("taxi", ('["amenity"="taxi"]',)),
    ("stabilimento balneare", ('["leisure"="beach_resort"]',)),
    ("beach club", ('["leisure"="beach_resort"]',)),
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


class LocationNotFound(ProviderError):
    """The location text does not match any real place."""


def tag_filters(niche: str) -> list[str]:
    for keyword, tags in KEYWORD_TAGS:
        if knowledge.keyword_in(keyword, niche):
            return list(tags)
    category = knowledge.detect_category(niche)
    if category in CATEGORY_TAGS:
        return list(CATEGORY_TAGS[category])
    safe = niche.replace('"', "").replace("\\", "").strip()
    return [f'["name"~"{safe}",i]']


@dataclass(frozen=True)
class SearchScope:
    """Where to look: an administrative area, a bounding box or a radius around a point."""

    kind: Literal["area", "bbox", "around"]
    area_id: int | None = None
    bbox: tuple[float, float, float, float] | None = None  # south, north, west, east
    point: tuple[float, float] | None = None  # lat, lon
    radius_m: int | None = None
    name: str = ""
    label: str = ""
    center: tuple[float, float] | None = None  # used to widen the search around the place

    def selector(self) -> tuple[str, str]:
        if self.kind == "area":
            return f"area(id:{self.area_id})->.a;", "(area.a)"
        if self.kind == "around" and self.point:
            # A square box around the point: bbox filters use Overpass' spatial index and are far
            # faster than (around:…), which times out on public instances for large radii.
            lat, lon = self.point
            dlat = (self.radius_m or 5000) / 111_320
            dlon = dlat / max(0.1, math.cos(math.radians(lat)))
            return "", f"({lat - dlat:.5f},{lon - dlon:.5f},{lat + dlat:.5f},{lon + dlon:.5f})"
        south, north, west, east = self.bbox or (0, 0, 0, 0)
        return "", f"({south},{west},{north},{east})"


def build_query(filters: list[str], scope: SearchScope, limit: int) -> str:
    prefix, selector = scope.selector()
    body = "".join(f'nwr{f}["name"]{selector};' for f in filters)
    return f"[out:json][timeout:25];{prefix}({body});out tags {limit};"


# Only real places are acceptable search scopes — never a restaurant or hotel that happens to be
# called "Tigullio" or "Costa Smeralda". Lower value = preferred.
GEO_CATEGORIES = {"boundary": 0, "place": 1, "natural": 2}
# Search radius for places mapped as a single point.
PLACE_RADIUS_M = {
    "city": 10_000,
    "town": 6_000,
    "village": 3_000,
    "hamlet": 1_500,
    "suburb": 2_500,
    "quarter": 1_500,
    "neighbourhood": 1_000,
    "locality": 10_000,
    "island": 12_000,
    "archipelago": 25_000,
    "region": 25_000,
    "county": 25_000,
    "state": 40_000,
    "bay": 12_000,
    "peninsula": 12_000,
    "cape": 8_000,
    "coastline": 12_000,
}


def _nominatim(client: httpx.Client, location: str, country: str | None) -> list[dict]:
    params = {"q": location, "format": "jsonv2", "limit": 10, "addressdetails": 1}
    if country:
        params["countrycodes"] = country.lower()
    resp = client.get(NOMINATIM_URL, params=params)
    resp.raise_for_status()
    return resp.json()


def pick_place(candidates: list[dict], country: str | None) -> dict | None:
    """Best geographic candidate: real places only, own country first, then importance."""
    places = [c for c in candidates if c.get("category") in GEO_CATEGORIES]
    if not places:
        return None

    def rank(c: dict) -> float:
        same_country = (c.get("address") or {}).get("country_code", "").upper() == (
            country or ""
        ).upper()
        return (
            float(c.get("importance") or 0)
            + (0.25 if same_country else 0)
            - 0.05 * GEO_CATEGORIES[c["category"]]
        )

    return max(places, key=rank)


def geocode(client: httpx.Client, location: str, country: str | None = None) -> SearchScope:
    """Resolve a place name. With ``country`` (ISO code) places in that country are preferred."""
    candidates = _nominatim(client, location, country) if country else []
    if country:
        time.sleep(1.0)  # Nominatim policy: at most one request per second
    candidates += _nominatim(client, location, None)
    place = pick_place(candidates, country)
    if place is None:
        raise LocationNotFound(
            f"'{location}' was not found as a place on OpenStreetMap (only shops or venues with "
            "that name). Try a city or municipality, e.g. 'Miami Beach' or 'Santa Margherita Ligure'."
        )
    name = place.get("name") or location
    kind_label = f"{place['category']}/{place.get('type', '?')}"
    osm_type, osm_id = place.get("osm_type"), int(place.get("osm_id", 0))
    south, north, west, east = (float(x) for x in place["boundingbox"])
    display = place.get("display_name", name)
    if "lat" in place and "lon" in place:
        center = (float(place["lat"]), float(place["lon"]))
    else:
        center = ((south + north) / 2, (west + east) / 2)
    if osm_type in ("relation", "way") and place["category"] in ("boundary", "place"):
        area_id = (3_600_000_000 if osm_type == "relation" else 2_400_000_000) + osm_id
        return SearchScope(
            "area", area_id=area_id, name=name, label=f"{display} ({kind_label})", center=center
        )
    if osm_type in ("relation", "way"):
        return SearchScope(
            "bbox",
            bbox=(south, north, west, east),
            name=name,
            label=f"{display} ({kind_label}, bounding box)",
            center=center,
        )
    radius = PLACE_RADIUS_M.get(place.get("type", ""), 5_000)
    return SearchScope(
        "around",
        point=center,
        radius_m=radius,
        name=name,
        label=f"{display} ({kind_label}, {radius / 1000:g} km radius)",
        center=center,
    )


def place_name_at(client: httpx.Client, lat: float, lon: float) -> str:
    """Human name of the municipality at a point (reverse geocoding); empty on failure."""
    try:
        resp = client.get(
            NOMINATIM_REVERSE_URL,
            params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 14, "addressdetails": 1},
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return ""
    address = data.get("address") or {}
    for key in ("city", "town", "village", "municipality", "suburb", "county"):
        if address.get(key):
            return str(address[key])
    return str(data.get("name") or "")


def pin_scope(client: httpx.Client, lat: float, lon: float, radius_m: int) -> SearchScope:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise LocationNotFound(f"Invalid coordinates {lat}, {lon}")
    radius_m = int(min(max(radius_m, 200), MAX_RADIUS_M))
    name = place_name_at(client, lat, lon) or f"{lat:.4f}, {lon:.4f}"
    return SearchScope(
        "around",
        point=(lat, lon),
        radius_m=radius_m,
        name=name,
        label=f"pin {lat:.4f}, {lon:.4f} near {name} ({radius_m / 1000:g} km radius)",
        center=(lat, lon),
    )


def widening_radii(scope: SearchScope) -> list[int]:
    """Radii to try when a scope returns too few leads (at most two extra queries)."""
    start = scope.radius_m if scope.kind == "around" and scope.radius_m else 2_500
    radii = sorted({min(start * 2, MAX_RADIUS_M), min(start * 4, MAX_RADIUS_M)})
    return [r for r in radii if r > (scope.radius_m or 0)][:2]


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

    def __init__(
        self,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
        country: str | None = None,
        on_step: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client or httpx.Client(headers=HTTP_HEADERS, timeout=timeout)
        self.country = country
        self.last_scope: SearchScope | None = None
        self.notes: list[str] = []
        self._on_step = on_step

    def _step(self, message: str) -> None:
        if self._on_step:
            self._on_step(message)

    def _overpass(self, query: str) -> list[dict]:
        """Try each public Overpass instance; retry once on 429/504 honouring Retry-After."""
        last_error: Exception | None = None
        for position, url in enumerate(OVERPASS_URLS, 1):
            host = url.split("/")[2]
            for attempt in range(2):
                try:
                    self._step(
                        f"Querying OpenStreetMap ({host}, server {position}/{len(OVERPASS_URLS)})…"
                    )
                    resp = self.client.post(url, data={"data": query})
                    if resp.status_code in (429, 504) and attempt == 0:
                        self._step(f"{host} is busy, retrying in a moment…")
                        time.sleep(min(float(resp.headers.get("Retry-After") or 2), 5.0))
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    remark = str(data.get("remark") or "")
                    if "error" in remark.lower():
                        # Overpass reports timeouts/memory errors as HTTP 200 with a remark:
                        # treating that as "no results" would silently hide real businesses.
                        raise ValueError(remark)
                    return data.get("elements", [])
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
                    self._step(
                        f"{host} did not answer ({type(exc).__name__}), trying another server…"
                    )
                    break
        raise ProviderError(
            f"Overpass API unavailable ({last_error}). Try again later or use --source demo."
        )

    def _collect(self, niche: str, scope: SearchScope, limit: int, leads: list[Lead]) -> list[Lead]:
        seen = {lead.company.name.lower() for lead in leads}
        for element in self._overpass(build_query(tag_filters(niche), scope, max(limit * 3, 30))):
            lead = element_to_lead(element, niche, scope.name)
            if lead and lead.company.name.lower() not in seen:
                seen.add(lead.company.name.lower())
                leads.append(lead)
        return leads

    def search(
        self,
        niche: str,
        location: str = "",
        limit: int = 10,
        *,
        near: tuple[float, float] | None = None,
        radius_m: int | None = None,
        expand: bool = True,
    ) -> list[Lead]:
        """Search a named place or a pin (``near`` + ``radius_m``).

        With ``expand`` (default) a search that finds fewer than ``limit`` leads is widened
        around the same centre, up to 25 km, and the widening is reported in ``self.notes``.
        """
        self.notes = []
        if near is not None:
            self._step("Reading the pin position…")
            scope = pin_scope(self.client, near[0], near[1], radius_m or 5_000)
        else:
            self._step(f"Locating '{location}' on the map…")
            scope = geocode(self.client, location, self.country)
        self._step(f"Search area: {scope.label}")
        self.last_scope = scope
        leads = self._collect(niche, scope, limit, [])
        self._step(f"Found {len(leads)} businesses")

        if expand and len(leads) < limit and scope.center:
            for radius in widening_radii(scope):
                before = len(leads)
                self._step(f"Only {before} found — widening to {radius / 1000:g} km…")
                wider = SearchScope(
                    "around",
                    point=scope.center,
                    radius_m=radius,
                    name=scope.name,
                    label=f"{scope.label} → widened to {radius / 1000:g} km",
                    center=scope.center,
                )
                try:
                    leads = self._collect(niche, wider, limit, leads)
                except ProviderError as exc:
                    # Keep what the first search found: a busy Overpass must not cost results.
                    self.notes.append(
                        f"Could not widen the search ({exc}); showing {before} leads."
                    )
                    break
                self.last_scope = wider
                self.notes.append(
                    f"Only {before} found in {scope.name}: widened the search to "
                    f"{radius / 1000:g} km around it (+{len(leads) - before})."
                )
                if len(leads) >= limit:
                    break
        # Most contactable first: website and phone make a lead actionable.
        leads.sort(
            key=lambda ld: (not ld.raw_signals.has_website, not ld.company.phone, ld.company.name)
        )
        return leads[:limit]
