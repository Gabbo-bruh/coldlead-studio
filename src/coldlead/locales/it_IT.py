"""Italy (it-IT): Italian demo businesses and the Italian vocabulary of the heuristics."""

from __future__ import annotations

import random

from coldlead.locales.base import Locale
from coldlead.models import LegalForm


def _phone(r: random.Random, mobile: bool, city: str) -> str:
    """Obviously fictitious numbers (zero-filled subscriber part) so no real person is exposed."""
    if mobile:
        return f"+39 3{r.randint(20, 49)} 000 00{r.randint(10, 99)}"
    return f"+39 0{r.randint(10, 99)} 000 0{r.randint(10, 99)}"


def _address(r: random.Random, city: str) -> str:
    return f"Via {r.choice(SURNAMES)} {r.randint(1, 120)}, {city}"


def _vat(r: random.Random) -> str:
    return f"IT000000{r.randint(10000, 99999)}"  # 13 characters: invalid on purpose


# fmt: off
SURNAMES = (
    "Rossi", "Bianchi", "Ferrari", "Esposito", "Romano", "Colombo", "Ricci", "Marino", "Greco",
    "Bruno", "Gallo", "Conti", "Costa", "Giordano", "Mancini", "Lombardi", "Moretti", "Barbieri",
    "Fontana", "Caruso", "Benvenuti", "Castaldi", "Canale", "De Luca", "Serra", "Pellegrini",
)

PLACES = (
    # Provincial capitals
    "Agrigento", "Alessandria", "Ancona", "Aosta", "Arezzo", "Ascoli Piceno", "Asti", "Avellino",
    "Bari", "Barletta", "Belluno", "Benevento", "Bergamo", "Biella", "Bologna", "Bolzano", "Brescia",
    "Brindisi", "Cagliari", "Caltanissetta", "Campobasso", "Caserta", "Catania", "Catanzaro",
    "Chieti", "Como", "Cosenza", "Cremona", "Crotone", "Cuneo", "Enna", "Fermo", "Ferrara",
    "Firenze", "Foggia", "Forlì", "Frosinone", "Genova", "Gorizia", "Grosseto", "Imperia",
    "Isernia", "L'Aquila", "La Spezia", "Latina", "Lecce", "Lecco", "Livorno", "Lodi", "Lucca",
    "Macerata", "Mantova", "Massa", "Carrara", "Matera", "Messina", "Milano", "Modena", "Monza",
    "Napoli", "Novara", "Nuoro", "Oristano", "Padova", "Palermo", "Parma", "Pavia", "Perugia",
    "Pesaro", "Pescara", "Piacenza", "Pisa", "Pistoia", "Pordenone", "Potenza", "Prato", "Ragusa",
    "Ravenna", "Reggio Calabria", "Reggio Emilia", "Rieti", "Rimini", "Roma", "Rovigo", "Salerno",
    "Sassari", "Savona", "Siena", "Siracusa", "Sondrio", "Taranto", "Teramo", "Terni", "Torino",
    "Trapani", "Trento", "Treviso", "Trieste", "Udine", "Urbino", "Varese", "Venezia", "Verbania",
    "Vercelli", "Verona", "Vibo Valentia", "Vicenza", "Viterbo",
    # English exonyms
    "Rome", "Milan", "Florence", "Venice", "Naples", "Turin", "Genoa", "Padua", "Mantua",
    # Regions and the country itself
    "Liguria", "Toscana", "Tuscany", "Lombardia", "Lombardy", "Piemonte", "Piedmont", "Veneto",
    "Sicilia", "Sicily", "Sardegna", "Sardinia", "Puglia", "Apulia", "Campania", "Calabria",
    "Lazio", "Umbria", "Marche", "Abruzzo", "Molise", "Basilicata", "Trentino", "Alto Adige",
    "Friuli", "Emilia", "Romagna", "Valle d'Aosta", "Costiera Amalfitana", "Amalfi Coast",
    "Italia", "Italy",
)

TOURIST_HUBS = (
    # Liguria
    "portofino", "santa margherita", "rapallo", "camogli", "sestri levante", "cinque terre",
    "monterosso", "vernazza", "riomaggiore", "portovenere", "lerici", "sanremo", "alassio",
    "genova", "chiavari", "zoagli", "finale ligure",
    # Tuscany
    "firenze", "florence", "siena", "pisa", "lucca", "forte dei marmi", "viareggio",
    "san gimignano", "montepulciano", "chianti", "val d'orcia", "elba", "cortona",
    "castiglione della pescaia",
    # Big cities & art cities
    "roma", "rome", "venezia", "venice", "milano", "milan", "verona", "bologna", "napoli",
    "naples", "torino", "turin", "palermo", "matera", "lecce",
    # Lakes & mountains
    "como", "bellagio", "menaggio", "varenna", "garda", "sirmione", "riva del garda", "malcesine",
    "stresa", "lago maggiore", "cortina", "courmayeur", "madonna di campiglio", "livigno", "bormio",
    "val gardena", "ortisei", "merano", "bolzano", "cervinia",
    # South & islands
    "amalfi", "positano", "ravello", "sorrento", "capri", "ischia", "procida", "taormina", "cefalù",
    "siracusa", "ortigia", "noto", "costa smeralda", "porto cervo", "olbia", "alghero",
    "villasimius", "polignano", "ostuni", "otranto", "gallipoli", "tropea", "maratea", "salento",
    "costiera",
)

LOCALE = Locale(
    code="it-IT",
    countries=("IT", "SM", "VA"),
    language="it",
    places=PLACES + tuple(hub.title() for hub in TOURIST_HUBS),
    default_city="Rapallo",
    default_niche="Charter nautico",
    surnames=SURNAMES,
    first_names=(
        "Marco", "Giulia", "Luca", "Francesca", "Alessandro", "Chiara", "Matteo", "Sara", "Andrea",
        "Elena", "Davide", "Valentina", "Stefano", "Martina", "Paolo", "Federica", "Gianni", "Laura",
    ),
    place_words=("del Porto", "al Mare", "Riviera", "del Golfo", "Belvedere", "Centrale", "Aurora",
                 "Stella"),
    name_templates={
        "nautical": ("{city} Charter", "Yacht Service {surname}", "Noleggio Barche {place}",
                     "{surname} Boats", "Blue Horizon Charter", "Marina {place}"),
        "real_estate": ("Immobiliare {surname}", "{city} Prestige Properties", "Casa & Mare {place}",
                        "Agenzia Immobiliare {place}", "{surname} Real Estate"),
        "hospitality": ("Hotel {place}", "Villa {surname}", "B&B {place}", "Residenza {surname}",
                        "{city} Boutique Hotel", "Agriturismo {surname}"),
        "restaurant": ("Ristorante {place}", "Trattoria da {first}", "Osteria {surname}",
                       "Da {first} & Figli", "Pizzeria {place}", "Il Gusto di {first}"),
        "cafe_bar": ("Bar {place}", "Caffè {surname}", "Pasticceria {surname}", "Gelateria {place}"),
        "clinic": ("Studio Dentistico {surname}", "Clinica {place}", "Poliambulatorio {city}",
                   "Centro Medico {surname}", "Studio Medico {surname}"),
        "beauty": ("Salone {first}", "Beauty Lab {surname}", "Centro Estetico {place}",
                   "Barber {surname}"),
        "professional": ("Studio Legale {surname}", "Studio {surname} & Associati",
                         "Commercialista {first} {surname}", "Architetti {surname}"),
        "fitness": ("Palestra {place}", "{city} Fitness Club", "Studio Pilates {first}",
                    "CrossFit {place}"),
        "automotive": ("Autofficina {surname}", "{city} Car Service", "Noleggio {surname}",
                       "NCC {surname}"),
        "retail": ("Boutique {first}", "Gioielleria {surname}", "Ottica {place}", "Negozio {surname}"),
        "events": ("{first} Wedding Planner", "Eventi {place}", "Catering {surname}",
                   "Foto {first} {surname}"),
        "generic": ("{niche} {surname}", "{surname} {niche}", "{niche} {place}", "{city} {niche}"),
    },
    generic_niche="Servizi",
    legal_forms={
        LegalForm.SRL: (" S.r.l.", LegalForm.SRL),
        LegalForm.SRLS: (" S.r.l.s.", LegalForm.SRLS),
        LegalForm.SNC_SAS: (" S.n.c.", LegalForm.SNC_SAS),
        LegalForm.SOLE_TRADER: ("", LegalForm.SOLE_TRADER),
        LegalForm.SPA: (" S.p.A.", LegalForm.SPA),
    },
    insolvency_suffix=" in liquidazione",
    polite_replies=(
        "Gentile {reviewer}, grazie di cuore per le belle parole! Vi aspettiamo presto a {city}.",
        "Grazie mille {reviewer}, è stato un piacere avervi nostri ospiti. A presto!",
        "Caro {reviewer}, felici che l'esperienza vi sia piaciuta. Un saluto da tutto lo staff.",
    ),
    toxic_replies=(
        "Sei un bugiardo, ti querelo per diffamazione e porto il tuo IP alla polizia postale!",
        "Vergognati, questa è una recensione falsa scritta da un concorrente. Non farti più vedere.",
    ),
    reviewers=("James", "Sophie", "Marco", "Anna", "Thomas", "Claire", "Giorgio", "Hannah"),
    agencies=("Pixel Web Agency", "Digitalia Web Agency", "WebStudio Web Agency",
              "Creativa Web Agency"),
    phone=_phone,
    address=_address,
    vat_number=_vat,
    # --- Italian vocabulary, merged into knowledge.py for every lead -----------------------------
    niche_keywords={
        "nautical": ("barc", "gommon", "vela"),
        "real_estate": ("immobiliar", "case vacanza"),
        "hospitality": ("albergo", "agriturismo", "affittacamere", "ostello"),
        "restaurant": ("ristorant", "ristorazione", "trattoria", "osteria", "enoteca"),
        "clinic": ("chirurg", "estetica medica", "fisioterap", "poliambulator", "ortodon", "psicolog",
                   "nutrizionist"),
        "beauty": ("parrucch", "estetist", "benessere", "centro estetico"),
        "cafe_bar": ("caffè", "caffe", "pasticceria", "gelateria"),
        "professional": ("avvocat", "studio legale", "commercialist", "notai", "architett",
                         "ingegner", "consulen", "agenzia viaggi", "assicuraz"),
        "fitness": ("palestra", "piscina"),
        "automotive": ("autofficina", "officina", "concessionari", "ncc", "noleggio auto"),
        "retail": ("negozio", "gioiell", "abbigliament", "ottica", "fiorist"),
        "events": ("matrimon", "eventi", "fotograf"),
    },
    ticket_keywords={
        10.0: ("jet privat", "chirurgia estetica"),
        9.5: ("lusso", "gioiell", "immobiliare di pregio"),
        9.0: ("chirurg", "ncc"),
        8.5: ("matrimon", "medicina estetica", "ortodon", "concessionari"),
        8.0: ("immobiliar", "albergo", "barc"),
        7.0: ("stellato", "agriturismo", "architett", "studio legale", "notai"),
        6.5: ("ristorant", "enoteca", "stabilimento balneare", "avvocat", "commercialist",
              "centro benessere", "fisioterap", "eventi"),
        5.5: ("palestra", "trattoria", "osteria", "officina", "autofficina", "ottica"),
        4.5: ("parrucch", "estetist", "negozio", "fiorist"),
        3.5: ("caffè", "caffe", "gelateria", "pasticceria"),
    },
    international_niches=("lusso",),
    tourist_hubs=TOURIST_HUBS,
    legal_form_patterns=(
        (r"\bs\.?\s?r\.?\s?l\.?\s?s\b\.?", LegalForm.SRLS),
        (r"\bs\.?\s?p\.?\s?a\b\.?", LegalForm.SPA),
        (r"\bs\.?\s?r\.?\s?l\b\.?", LegalForm.SRL),
        (r"\bs\.?\s?n\.?\s?c\b\.?|\bs\.?\s?a\.?\s?s\b\.?", LegalForm.SNC_SAS),
        (r"\bsoc(ietà|\.)?\s*coop|\bcooperativa\b", LegalForm.COOP),
        (r"\bd\.\s?i\.?(?=\s|$)|\bditta individuale\b", LegalForm.SOLE_TRADER),
        (r"\bstudio (legale|associato|medico|dentistico|notarile|tecnico)\b", LegalForm.PROFESSIONAL),
    ),
    toxic_reply_patterns=(
        r"\bti querelo\b", r"\bquerela\b", r"\bdenunci(o|a|ato|erò)\b", r"\bdiffamazione\b",
        r"\bavvocat[oi] (mio|nostro)\b", r"\bmio legale\b", r"\bpolizia postale\b", r"\btribunale\b",
        r"\bvergognati\b", r"\bidiot[ae]\b", r"\bstronz[oa]\b", r"\bbugiard[oa]\b", r"\bcretin[oa]\b",
        r"\bfals[oi] profil[oi]\b", r"\bnon farti più vedere\b", r"\bchiudi quella bocca\b",
    ),
    insolvency_patterns=(
        r"\bin liquidazione\b", r"\bliquidazione\b", r"\bfallimento\b", r"\bfallit[ao]\b",
        r"\bconcordato preventivo\b", r"\bprocedura concorsuale\b", r"\bcessata attività\b",
        r"\bchiuso definitivamente\b", r"\bprotest[io]\b",
    ),
    mobile_prefixes=("+393", "393", "3"),
)
# fmt: on
