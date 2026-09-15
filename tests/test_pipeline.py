from __future__ import annotations

import json
from pathlib import Path

import pytest

from coldlead import pipeline
from coldlead.models import Session
from coldlead.providers.osm import ProviderError
from coldlead.settings import Settings
from coldlead.storage import SessionNotFound


def test_scout_demo_persists_raw_session(store):
    session = pipeline.scout(
        "Charter nautico", "Portofino", 6, source="demo", store=store, settings=Settings()
    )
    assert session.source == "demo"
    assert len(session.leads) == 6
    assert any("DEMO DATA" in n for n in session.notices)
    assert all(lead.enrichment.vibe_opportunity_summary for lead in session.leads)
    raw = json.loads(store._path(session.id).read_text(encoding="utf-8"))
    assert "pos_evaluation" not in json.dumps(raw)  # scores are never cached, only raw signals
    assert store.load().id == session.id


def test_auto_falls_back_to_demo(monkeypatch, store):
    class Broken:
        def __init__(self, **kwargs):
            pass

        def search(self, *args, **kwargs):
            raise ProviderError("offline")

    monkeypatch.setattr(pipeline, "OSMProvider", Broken)
    session = pipeline.scout("Hotel", "Como", 3, source="auto", store=store, settings=Settings())
    assert session.source == "demo"
    assert any("osm unavailable" in n for n in session.notices)


def test_empty_live_results_never_become_demo(monkeypatch, store):
    class Empty:
        last_scope = None

        def __init__(self, **kwargs):
            pass

        def search(self, *args, **kwargs):
            return []

    monkeypatch.setattr(pipeline, "OSMProvider", Empty)
    leads, source, notices = pipeline.discover("nautico", "Tigullio", 5, "auto", Settings())
    assert (leads, source) == ([], "none")
    assert "found no 'nautico' businesses" in notices[-1]


def test_unknown_location_is_an_error_even_in_auto(monkeypatch):
    from coldlead.providers.osm import LocationNotFound

    class Lost:
        def __init__(self, **kwargs):
            pass

        def search(self, *args, **kwargs):
            raise LocationNotFound("'Atlantide' was not found")

    monkeypatch.setattr(pipeline, "OSMProvider", Lost)
    with pytest.raises(LocationNotFound):
        pipeline.discover("Bar", "Atlantide", 3, "auto", Settings())


def test_explicit_source_errors_propagate(monkeypatch):
    class Broken:
        def __init__(self, **kwargs):
            pass

        def search(self, *args, **kwargs):
            raise ProviderError("offline")

    monkeypatch.setattr(pipeline, "OSMProvider", Broken)
    with pytest.raises(ProviderError):
        pipeline.discover("Hotel", "Como", 3, "osm", Settings())
    with pytest.raises(ProviderError, match="GOOGLE_PLACES_API_KEY"):
        pipeline.discover("Hotel", "Como", 3, "google", Settings())


def test_import_csv_with_italian_headers(tmp_path, store):
    csv_file = tmp_path / "leads.csv"
    csv_file.write_text(
        "Azienda;Sito;Città;Telefono;is_running_ads\n"
        "Trattoria da Mario S.n.c.;;Rapallo;+39 0185 1;sì\n"
        "Hotel Bellavista S.r.l.;;Como;;no\n"
        ";;;;\n",
        encoding="utf-8",
    )
    session = pipeline.import_leads(
        csv_file, niche="Ristorante", audit=False, store=store, settings=Settings()
    )
    assert len(session.leads) == 2
    mario = session.leads[0]
    assert mario.company.legal_form.value == "S.n.c. / S.a.s."
    assert mario.company.niche == "Ristorante"
    assert mario.raw_signals.is_running_ads is True
    assert session.leads[1].raw_signals.is_running_ads is False


@pytest.mark.parametrize("name", ["my_leads.csv", "my_leads.it.csv"])
def test_example_lead_lists_import_the_same_way(name):
    path = Path(__file__).parent.parent / "examples" / name
    leads = pipeline.read_leads_file(path)
    assert len(leads) == 3
    charter = leads[1]
    assert charter.company.direct_contact_person  # "contact" / "referente"
    assert charter.company.phone and charter.company.city
    assert charter.raw_signals.is_running_ads is True
    assert charter.raw_signals.owner_reply_rate == 90
    assert leads[2].raw_signals.owner_reply_rate is None  # empty cell = unknown


def test_import_json_dossiers_roundtrip(tmp_path, store, leads, config):
    from coldlead.export import to_json
    from coldlead.scoring import score_leads

    exported = tmp_path / "export.json"
    exported.write_text(to_json(score_leads(leads, config), config), encoding="utf-8")
    back = pipeline.read_leads_file(exported)
    assert {ld.id for ld in back} == {ld.id for ld in leads}
    assert back[0].raw_signals == next(ld for ld in leads if ld.id == back[0].id).raw_signals


def test_single_lead_without_network():
    lead = pipeline.single_lead(
        "Rossi S.r.l.", "Dentista", "Milano", None, is_running_ads=True, settings=Settings()
    )
    assert lead.raw_signals.is_running_ads is True
    assert lead.company.legal_form.value == "S.r.l."
    assert lead.enrichment.vibe_opportunity_summary


def test_store_list_prefix_and_delete(store):
    s1 = Session(id="20260101-000000-a", niche="a")
    s2 = Session(id="20260102-000000-b", niche="b")
    store.save(s1)
    store.save(s2)
    assert [s.id for s in store.list()] == [s2.id, s1.id]
    assert store.load("20260101").id == s1.id
    store.delete(s1.id)
    with pytest.raises(SessionNotFound):
        store.load(s1.id)
    with pytest.raises(SessionNotFound):
        store.load("../etc/passwd")
