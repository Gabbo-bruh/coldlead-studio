"""United States (en-US): American demo businesses. Also the fallback for unknown places."""

from __future__ import annotations

import random

from coldlead.locales.base import Locale, fold
from coldlead.models import LegalForm

# Real area codes, so demo numbers look local; the 555-0100…0199 block is reserved for fiction.
AREA_CODES = {
    "miami": "305", "miami beach": "305", "key west": "305", "fort lauderdale": "954",
    "palm beach": "561", "orlando": "407", "tampa": "813", "new york": "212", "brooklyn": "718",
    "los angeles": "213", "san francisco": "415", "san diego": "619", "napa": "707",
    "chicago": "312", "houston": "713", "dallas": "214", "austin": "512", "seattle": "206",
    "boston": "617", "denver": "303", "aspen": "970", "las vegas": "702", "nashville": "615",
    "atlanta": "404", "phoenix": "602", "portland": "503", "philadelphia": "215",
    "washington": "202", "new orleans": "504", "honolulu": "808", "charleston": "843",
    "savannah": "912",
}  # fmt: skip
STREETS = (
    "Main Street", "Ocean Drive", "Harbor Boulevard", "Park Avenue", "Maple Street", "Bay Road",
    "Washington Avenue", "Lake Street", "Sunset Boulevard", "Broadway",
)  # fmt: skip


def _phone(r: random.Random, mobile: bool, city: str) -> str:
    """North American numbers are not split into mobile and landline ranges, so ``mobile`` is
    ignored; 555-01xx numbers are reserved for fiction and never reach a real subscriber."""
    area = AREA_CODES.get(fold(city)) or r.choice(sorted(set(AREA_CODES.values())))
    return f"+1 {area}-555-01{r.randint(10, 99)}"


def _address(r: random.Random, city: str) -> str:
    return f"{r.randint(10, 9899)} {r.choice(STREETS)}, {city}"


def _vat(r: random.Random) -> str:
    return ""  # no VAT in the US, and EINs are not public


# fmt: off
LOCALE = Locale(
    code="en-US",
    countries=("US",),
    language="en",
    places=(
        "Miami", "Miami Beach", "Key West", "Fort Lauderdale", "Palm Beach", "Orlando", "Tampa",
        "Jacksonville", "New York", "NYC", "Manhattan", "Brooklyn", "Los Angeles", "San Francisco",
        "San Diego", "San Jose", "Sacramento", "Napa", "Chicago", "Houston", "Dallas", "Austin",
        "San Antonio", "Seattle", "Boston", "Denver", "Aspen", "Las Vegas", "Nashville", "Atlanta",
        "Phoenix", "Scottsdale", "Portland", "Philadelphia", "Washington, D.C.", "New Orleans",
        "Honolulu", "Charleston", "Savannah", "Detroit", "Minneapolis", "Salt Lake City",
        # States and the country itself
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
        "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
        "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
        "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
        "New Jersey", "New Mexico", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
        "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas",
        "Utah", "Vermont", "Virginia", "West Virginia", "Wisconsin", "Wyoming",
        "USA", "U.S.A.", "United States",
    ),
    default_city="Miami",
    default_niche="Yacht charter",
    surnames=(
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez",
        "Martinez", "Hernandez", "Lopez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore",
        "Jackson", "Martin", "Lee", "Thompson", "White", "Harris", "Clark", "Lewis", "Walker",
    ),
    first_names=(
        "James", "Mary", "Michael", "Jennifer", "David", "Jessica", "Chris", "Sarah", "Daniel",
        "Emily", "Matthew", "Ashley", "Ryan", "Megan", "Kevin", "Olivia", "Carlos", "Maria",
    ),
    place_words=("Harbor", "Bayside", "Oceanview", "Sunset", "Coastal", "Downtown", "Palm Grove",
                 "Main Street"),
    name_templates={
        "nautical": ("{city} Yacht Charters", "{surname} Boat Rentals", "Blue Horizon Charters",
                     "{place} Marine", "Captain {first}'s Charters", "{surname} Sailing Co."),
        "real_estate": ("{surname} Realty", "{city} Luxury Homes", "{place} Properties",
                        "{surname} & Associates Real Estate", "Keystone Realty Group"),
        "hospitality": ("The {place} Hotel", "{surname} Inn", "{city} Boutique Hotel",
                        "{place} Suites", "{surname} House B&B"),
        "restaurant": ("{first}'s Kitchen", "The {place} Grill", "{surname}'s Steakhouse",
                       "{city} Bistro", "{first}'s Diner", "{place} Tavern"),
        "cafe_bar": ("{place} Coffee Co.", "{first}'s Bakery", "The {place} Bar", "{surname} Cafe"),
        "clinic": ("{surname} Family Dentistry", "{city} Smile Studio", "{place} Medical Group",
                   "{surname} Dental Care", "{city} Wellness Clinic"),
        "beauty": ("{first}'s Salon", "{surname} Beauty Lab", "{place} Day Spa",
                   "{surname} Barbershop"),
        "professional": ("{surname} Law Group", "{surname} & Associates", "{first} {surname} CPA",
                         "{surname} Architects"),
        "fitness": ("{place} Fitness", "{city} Athletic Club", "{first}'s Pilates Studio",
                    "CrossFit {place}"),
        "automotive": ("{surname} Auto Repair", "{city} Car Care", "{surname} Motors",
                       "{place} Limo Service"),
        "retail": ("{first}'s Boutique", "{surname} Jewelers", "{place} Eyewear", "{surname} Goods"),
        "events": ("{first} {surname} Weddings", "{place} Events", "{surname} Catering",
                   "{first} {surname} Photography"),
        "generic": ("{surname} {niche}", "{niche} of {city}", "{place} {niche}", "{city} {niche} Co."),
    },
    generic_niche="Services",
    legal_forms={
        LegalForm.SPA: (" Inc.", LegalForm.LTD),
        LegalForm.SRL: (" LLC", LegalForm.LTD),
        LegalForm.SRLS: (" LLC", LegalForm.LTD),
        LegalForm.SNC_SAS: (" LLP", LegalForm.SNC_SAS),
        LegalForm.SOLE_TRADER: ("", LegalForm.SOLE_TRADER),
    },
    insolvency_suffix=" (in liquidation)",
    polite_replies=(
        "Thank you so much, {reviewer}! We loved having you and hope to see you again in {city}.",
        "Hi {reviewer}, thanks for the kind words, it was a pleasure hosting you. See you soon!",
        "Dear {reviewer}, we're thrilled you enjoyed your experience. Warm regards from the team.",
    ),
    toxic_replies=(
        "You're a liar. My lawyer will sue you for defamation and I'm reporting your account.",
        "This is a fake review written by a competitor. Don't ever come back here, idiot.",
    ),
    reviewers=("Emily", "Carlos", "Sophie", "Mike", "Priya", "Daniel", "Grace", "Luis"),
    agencies=("Pixel Digital", "Brightside Web Studio", "Northstar Creative", "WebCraft Agency"),
    phone=_phone,
    address=_address,
    vat_number=_vat,
    # --- US vocabulary, merged into knowledge.py (English words live in knowledge.py itself) ----
    tourist_hubs=(
        "miami", "orlando", "new york", "manhattan", "las vegas", "los angeles", "san francisco",
        "honolulu", "maui", "key west", "new orleans", "washington, d.c.", "palm beach", "napa",
        "aspen",
    ),
    legal_form_patterns=((r"\bl\.?l\.?p\b\.?", LegalForm.SNC_SAS),),
)
# fmt: on
