"""Google Places API (New) provider — requires ``GOOGLE_PLACES_API_KEY``.

Uses Text Search with a minimal field mask to keep costs low (no reviews/atmosphere fields).
"""

from __future__ import annotations

import httpx

from coldlead import knowledge
from coldlead.models import Company, Lead, RawSignals, make_lead_id
from coldlead.providers.osm import ProviderError

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.nationalPhoneNumber",
        "places.internationalPhoneNumber",
        "places.websiteUri",
        "places.rating",
        "places.userRatingCount",
        "places.businessStatus",
        "nextPageToken",
    )
)


def place_to_lead(place: dict, niche: str, city: str) -> Lead:
    name = (place.get("displayName") or {}).get("text", "Unknown business")
    website = place.get("websiteUri")
    phone = place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber") or ""
    return Lead(
        id=make_lead_id("google", place.get("id", name)),
        company=Company(
            name=name,
            niche=niche,
            city=city,
            address=place.get("formattedAddress", ""),
            phone=phone,
            legal_form=knowledge.parse_legal_form(name),
            contact_channels=["Phone"] if phone else [],
        ),
        raw_signals=RawSignals(
            has_website=bool(website),
            website_url=website,
            reviews_count=place.get("userRatingCount"),
            average_rating=place.get("rating"),
            business_status=place.get("businessStatus"),
        ),
        source="google_places",
    )


class GooglePlacesProvider:
    name = "google_places"

    def __init__(
        self, api_key: str, client: httpx.Client | None = None, language: str = "it"
    ) -> None:
        if not api_key:
            raise ProviderError("GOOGLE_PLACES_API_KEY is not set")
        self.api_key = api_key
        self.language = language
        self.client = client or httpx.Client(timeout=15.0)

    def search(
        self,
        niche: str,
        location: str = "",
        limit: int = 10,
        *,
        near: tuple[float, float] | None = None,
        radius_m: int | None = None,
        **_: object,
    ) -> list[Lead]:
        leads: list[Lead] = []
        page_token: str | None = None
        while len(leads) < limit:
            body: dict = {
                "textQuery": f"{niche} {location}".strip(),
                "pageSize": min(20, limit - len(leads)),
                "languageCode": self.language,
            }
            if near is not None:
                body["locationBias"] = {
                    "circle": {
                        "center": {"latitude": near[0], "longitude": near[1]},
                        "radius": float(min(radius_m or 5_000, 50_000)),
                    }
                }
            if page_token:
                body["pageToken"] = page_token
            resp = self.client.post(
                SEARCH_URL,
                json=body,
                headers={"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": FIELD_MASK},
            )
            if resp.status_code >= 400:
                message = resp.json().get("error", {}).get("message", resp.text[:200])
                raise ProviderError(f"Google Places error {resp.status_code}: {message}")
            data = resp.json()
            city = location.title() or ""
            leads.extend(place_to_lead(p, niche, city) for p in data.get("places", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return leads[:limit]
