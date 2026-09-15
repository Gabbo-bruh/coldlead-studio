"""Meta Ad Library check (optional, needs ``META_AD_LIBRARY_ACCESS_TOKEN``).

Complements the offline evidence gathered by the tech auditor (Meta Pixel / Google Ads tags).
"""

from __future__ import annotations

import json
import re

import httpx

AD_LIBRARY_URL = "https://graph.facebook.com/v23.0/ads_archive"


def _norm(text: str) -> str:
    text = re.sub(r"\b(s\.?r\.?l\.?s?|s\.?p\.?a\.?|s\.?n\.?c\.?|s\.?a\.?s\.?)\b", "", text.lower())
    return re.sub(r"[^a-z0-9]+", "", text)


def has_active_meta_ads(
    company_name: str,
    token: str,
    country: str | None = None,
    client: httpx.Client | None = None,
) -> bool | None:
    """``True``/``False`` when the Ad Library answers, ``None`` when it can't be checked.

    ``country`` is the ISO code of the market to check; ``None`` searches every country.
    """
    owns = client is None
    client = client or httpx.Client(timeout=15.0)
    try:
        resp = client.get(
            AD_LIBRARY_URL,
            params={
                "search_terms": company_name,
                "ad_reached_countries": json.dumps([(country or "ALL").upper()]),
                "ad_active_status": "ACTIVE",
                "ad_type": "ALL",
                "fields": "page_name",
                "limit": 10,
                "access_token": token,
            },
        )
        resp.raise_for_status()
        target = _norm(company_name)
        return any(
            target
            and (
                target in _norm(ad.get("page_name", "")) or _norm(ad.get("page_name", "")) in target
            )
            for ad in resp.json().get("data", [])
            if ad.get("page_name")
        )
    except (httpx.HTTPError, ValueError):
        return None
    finally:
        if owns:
            client.close()
