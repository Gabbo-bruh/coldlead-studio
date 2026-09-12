# 🎯 Scientific Cold Lead Scout & Precision Opportunity Score (POS) Studio

Strumento scientifico di scouting B2B e lead scoring per prodotti e servizi creati in **VibeCoding** (micro-applicativi interattivi, automazioni AI, bot WhatsApp, replatforming ad altissima velocità).

---

## 🌟 Caratteristiche Principali

- **Formula Matematica POS Normalizzata (0 - 100)** con pesi ed esponenti configurabili.
- **8 Variabili Scientifiche**:
  1. $G_{dig}$ — Digital & AI Readiness Gap (Lighthouse, stack obsoleto, assenza viewport).
  2. $V_{ticket}$ — Valore Ticket / Margine Settore (Yacht, ville di lusso, boutique hotel, cliniche).
  3. $F_{fin}$ — Solidità Finanziaria (S.p.A. / S.r.l. storica vs Ditta individuale).
  4. $C_{press}$ — Pressione Competitiva Locale (gap con i competitor che dominano online).
  5. $M_{reach}$ — Frizione Mercato Estero (turisti esteri ad alto budget senza sito in lingua).
  6. $A_{decision}$ — Accessibilità Decision Maker (titolare su WhatsApp/telefono diretto).
  7. $B_{care}$ — Cura del Brand & Psicologia (analisi sentiment e risposte alle recensioni).
  8. $U_{vibe}$ — Superficie VibeCoding (processi manuali convertibili in micro-tool in 24h).
- **Moltiplicatori & Penalità**:
  - $M_{Ads}$ (1.25x): l'azienda spende in Ads su un sito che perde conversioni.
  - $M_{Friction}$ (1.15x): errori critici come assenza SSL o layout mobile rotto.
  - $T_{win}$ (0.5x - 1.4x): moltiplicatore di finestra stagionale / temporale.
- **Filtro Red Flag Immediato**:
  - Titolare aggressivo o litigioso nelle risposte Google.
  - Forte vendor lock-in con agenzie web contrattualizzate.
  - Segnali di insolvenza, liquidazione o chiusura.
- **Manomissione Pesi in Tempo Reale**:
  - Slider interattivi nella WebApp: sposti lo slider e l'intera lista si ricalcola istantaneamente.
  - Preset pronti in `weights_config.json` (`vibe_coding`, `automation_first`, `luxury_high_ticket`, `speedy_cashflow`).
  - Override diretto da riga di comando o parametro MCP (`custom_weights`).
- **Formati di Output Multipli**:
  - 📊 **CSV**: pronto per CRM (Hubspot, Notion, Airtable, Google Sheets).
  - 📦 **JSON Completo**: schema completo per database o pipeline esterne.
  - ⚡ **JSON Compatto**: ottimizzato per prompt AI a basso consumo di token.
  - 📋 **Dossier Markdown**: report formattato con classifiche e alert.
  - 🚀 **Action Kit**: Loom script (90s con timing), cold email chirurgica, WhatsApp opener, e prompt VibeCoding per generare il prototipo funzionante con AI.

---

## 🏗️ Le 3 Forme del Prodotto

### 1. Antigravity Skill & CLI
Registrata nativamente in `.agents/skills/coldlead-scout/SKILL.md`.

```bash
# Esecuzione standard con report Markdown
python skill/run_scout.py --niche "Charter nautico" --location "Rapallo" --format markdown

# Esportazione in CSV per CRM
python skill/run_scout.py --niche "Hotel di lusso" --location "Portofino" --format csv --out leads.csv

# Generazione Action Kit del top lead
python skill/run_scout.py --niche "Ristoranti gourmet" --location "Chiavari" --format action_kit

# Manomissione pesi manuale da CLI
python skill/run_scout.py --niche "Immobiliari" --location "Santa Margherita" --weights '{"w_A": 3.5, "w_G": 2.0}'
```

### 2. Server MCP (Model Context Protocol)
Compatibile con qualsiasi client AI standard (Cursor, Claude Desktop, Antigravity, Windsurf).

```bash
python mcp_server/server.py
```

**Tool esposti:**
- `coldlead_search(niche, location, limit, preset, format)`
- `coldlead_audit(url)`
- `coldlead_score(company_name, niche, city, website_url, custom_weights, season)`
- `coldlead_generate_pitch(company_name, niche, city, website_url, vibe_opportunity)`

### 3. Local WebApp (Dashboard Interattiva)

```bash
# Avvio del server locale
python webapp/app.py
```
Apri il browser su: **`http://127.0.0.1:8000`**

- Slider reattivi in tempo reale per manomettere i pesi ($w_G, w_T, w_F, w_P, w_I, w_D, w_C, w_A$).
- Radar Chart dinamico via Chart.js per ogni prospect.
- Modale Action Kit con 1-click copy per Loom, Email, WhatsApp e VibeCoding Prompt.
- Download con un clic di CSV, JSON e Markdown.

---

## 🔑 Configurazione API (Opzionale)
Il sistema include dati di benchmark realistici pronti all'uso per test immediati anche senza chiavi API. Per collegare API live:
1. Copia `.env.example` in `.env`.
2. Inserisci le tue chiavi (`GEMINI_API_KEY`, `GOOGLE_PLACES_API_KEY`, `PAGESPEED_API_KEY`).
