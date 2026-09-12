"""End-to-end checks of the four product surfaces: CLI, web dashboard API, MCP server, skills."""

from __future__ import annotations

import asyncio
import csv
import io
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from coldlead.cli import app

ROOT = Path(__file__).parent.parent
runner = CliRunner()


def cli(*args: str):
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result


# --------------------------------------------------------------------------------------- CLI


def test_cli_scout_rescore_explain_kit_export(tmp_path):
    out = cli(
        "scout", "Charter nautico", "Portofino", "--source", "demo", "-n", "8", "-f", "json"
    ).stdout
    payload = json.loads(out)
    assert payload["summary"]["total"] == 8
    first_id = payload["leads"][0]["id"]

    tuned = json.loads(cli("rescore", "-w", "w_A=10", "-w", "G_dig=0", "-f", "json").stdout)
    assert tuned["scoring"]["weights"]["w_A"] == 10.0
    assert tuned["scoring"]["weights"]["w_G"] == 0.0

    assert "Σ(w·V)/Σw×10" in cli("explain", "1").stdout
    assert first_id in cli("explain", first_id).stdout

    kit = json.loads(cli("kit", "1", "--json", "--lang", "en").stdout)
    assert kit["action_kit"]["language"] == "en"
    assert len(kit["action_kit"]["whatsapp_opener"]) <= 300

    target = tmp_path / "leads.csv"
    cli("export", "-f", "csv", "-o", str(target), "-p", "automation_first")
    rows = list(csv.DictReader(io.StringIO(target.read_text(encoding="utf-8"), newline="")))
    assert len(rows) == 8

    md = cli("export", "-f", "markdown", "--with-kits").stdout
    assert "🚀 Action Kit" in md


def test_cli_table_output_and_listing():
    cli("scout", "Ristorante", "Firenze", "--source", "demo", "-n", "4")
    assert "Ristorante" in cli("sessions").stdout
    assert "default_vibe_coding" in cli("presets").stdout
    assert "hot" in cli("rescore", "--top", "2", "--vars").stdout.lower()


def test_cli_errors_are_friendly():
    result = runner.invoke(app, ["rescore"])
    assert result.exit_code == 1
    assert "No sessions yet" in result.output
    cli("scout", "Bar", "Asti", "--source", "demo", "-n", "3", "-f", "compact")
    bad = runner.invoke(app, ["rescore", "-w", "w_Z=3"])
    assert bad.exit_code == 1 and "Unknown weight" in bad.output
    missing = runner.invoke(app, ["explain", "zzz-not-there"])
    assert missing.exit_code == 1


def test_cli_import(tmp_path):
    f = tmp_path / "mine.csv"
    f.write_text(
        "name,city,niche\nHotel Lago S.r.l.,Como,Hotel\nB&B Sole,Como,B&B\n", encoding="utf-8"
    )
    out = cli("import", str(f), "--no-audit").stdout
    assert "Hotel Lago" in out


def test_cli_config_schema_doctor_version(isolated):
    cli("config", "--init")
    assert (isolated / "config.json").exists()
    assert "my_luxury_automation" in cli("presets").stdout
    assert json.loads(cli("schema").stdout)["title"] == "LeadDossier"
    assert "ColdLead Studio" in cli("doctor").stdout
    assert "coldlead-studio" in cli("--version").stdout


# --------------------------------------------------------------------------------------- Web

fastapi = pytest.importorskip("fastapi")


@pytest.fixture
def client(store):
    from fastapi.testclient import TestClient

    from coldlead.web.app import create_app

    return TestClient(create_app(store))


def test_web_index_and_meta(client):
    assert "ColdLead" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    meta = client.get("/api/meta").json()
    assert len(meta["variables"]) == 8
    assert "high_ticket_luxury" in meta["presets"]


def test_web_flow(client):
    assert client.post("/api/score", json={}).status_code == 404
    scouted = client.post(
        "/api/scout", json={"niche": "Hotel", "location": "Como", "limit": 6, "source": "demo"}
    )
    assert scouted.status_code == 200
    data = scouted.json()
    session_id = data["session"]["id"]
    assert data["counts"]["total"] == 6

    tuned = client.post(
        "/api/score", json={"session_id": session_id, "weights": {"w_A": 10, "w_G": 0}}
    ).json()
    assert tuned["config"]["weights"]["w_A"] == 10
    assert tuned["elapsed_ms"] < 100
    assert client.post("/api/score", json={"weights": {"nope": 1}}).status_code == 422

    lead_id = tuned["leads"][0]["id"]
    kit = client.get(f"/api/kit/{session_id}/{lead_id}?lang=en").json()
    assert kit["language"] == "en"
    assert client.get(f"/api/kit/{session_id}/missing").status_code == 404

    export = client.post("/api/export", json={"session_id": session_id, "format": "csv"})
    assert export.headers["content-disposition"].endswith('.csv"')
    assert export.text.startswith("rank,id,name")
    assert client.post("/api/export", json={"format": "xml"}).status_code == 422

    assert len(client.get("/api/sessions").json()) == 1
    assert client.delete(f"/api/sessions/{session_id}").status_code == 200
    assert client.get("/api/sessions").json() == []


# --------------------------------------------------------------------------------------- MCP

mcp = pytest.importorskip("mcp")


def _call(server, name: str, args: dict) -> str:
    result = asyncio.run(server.call_tool(name, args))
    assert not result.is_error, result
    return result.content[0].text


def test_mcp_tools(store):
    from coldlead.mcp_server import build_server

    server = build_server(store)
    tools = {t.name for t in asyncio.run(server.list_tools())}
    assert tools == {
        "coldlead_search",
        "coldlead_rescore",
        "coldlead_explain",
        "coldlead_audit",
        "coldlead_score",
        "coldlead_generate_pitch",
        "coldlead_list",
        "coldlead_open_dashboard",
    }
    text = _call(
        server,
        "coldlead_search",
        {"niche": "Charter", "location": "Portofino", "limit": 5, "source": "demo"},
    )
    assert "Session `" in text and "Leaderboard" in text
    rescored = _call(
        server, "coldlead_rescore", {"custom_weights": {"automation": 9}, "format": "compact"}
    )
    assert rescored.startswith("Re-scored 5 leads")
    assert "raw" in _call(server, "coldlead_explain", {"lead": "1"})
    pitch = _call(server, "coldlead_generate_pitch", {"lead": "1", "language": "en"})
    assert "Loom script" in pitch and "WhatsApp" in pitch
    assert "default_vibe_coding" in _call(server, "coldlead_list", {"what": "presets"})
    scored = json.loads(
        _call(
            server,
            "coldlead_score",
            {
                "company_name": "Rossi S.r.l.",
                "niche": "Dentista",
                "city": "Milano",
                "is_running_ads": True,
            },
        )
    )
    assert scored["pos_evaluation"]["multipliers_applied"]["m_ads"] == 1.25


# --------------------------------------------------------------------------------------- Skills


def test_skill_copies_are_identical_and_valid():
    canonical = ROOT / "skills" / "coldlead-scout" / "SKILL.md"
    copies = [
        ROOT / ".agents" / "skills" / "coldlead-scout" / "SKILL.md",
        ROOT / ".claude" / "skills" / "coldlead-scout" / "SKILL.md",
    ]
    text = canonical.read_text(encoding="utf-8")
    assert text.startswith("---\nname: coldlead-scout\n")
    assert "description:" in text.split("---")[1]
    for copy in copies:
        assert copy.read_text(encoding="utf-8") == text, f"{copy} is out of sync with {canonical}"


def test_plugin_manifest():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "coldlead-studio"
    mcp_config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert "coldlead" in mcp_config["mcpServers"]


def test_web_pin_scout_and_geocode(client, monkeypatch):
    from coldlead.providers import osm

    bad = client.post("/api/scout", json={"niche": "Bar", "source": "demo"})
    assert bad.status_code == 422 and "pin" in bad.json()["detail"]
    pinned = client.post(
        "/api/scout",
        json={"niche": "Bar", "source": "demo", "lat": 44.35, "lon": 9.15, "radius_km": 3},
    ).json()
    assert pinned["session"]["location"].startswith("📍")
    assert pinned["session"]["location"].endswith("· 3 km")

    monkeypatch.setattr(
        osm,
        "geocode",
        lambda client, q, country: osm.SearchScope("area", name="Chiavari", center=(44.32, 9.32)),
    )
    assert client.get("/api/geocode?q=Chiavari").json() == {
        "lat": 44.32,
        "lon": 9.32,
        "name": "Chiavari",
        "label": "",
    }


def test_cli_near_option():
    out = cli(
        "scout", "Bar", "--near", "44.35,9.15", "-r", "2", "--source", "demo", "-f", "json"
    ).stdout
    assert json.loads(out)["session"]["location"].endswith("· 2 km")
    bad = runner.invoke(app, ["scout", "Bar", "--near", "nope"])
    assert bad.exit_code == 1 and "LAT,LON" in bad.output
    missing = runner.invoke(app, ["scout", "Bar", "--source", "demo"])
    assert missing.exit_code == 1 and "map pin" in missing.output


def test_web_scout_job_reports_progress(client):
    import time as _time

    job_id = client.post(
        "/api/jobs/scout", json={"niche": "Hotel", "location": "Como", "limit": 4, "source": "demo"}
    ).json()["job_id"]
    for _ in range(100):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        _time.sleep(0.05)
    assert job["status"] == "done", job
    assert job["result"]["counts"]["total"] == 4
    assert any("Generating demo prospects" in line for line in job["log"])
    assert job["stage"] == "save" and job["done"] == job["total"] == 1
    assert client.get("/api/jobs/nope").status_code == 404

    failed = client.post(
        "/api/jobs/scout", json={"niche": "Hotel", "location": "", "source": "demo"}
    )
    assert failed.status_code == 422  # validation happens before the job starts
