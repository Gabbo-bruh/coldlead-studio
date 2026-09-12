---
name: coldlead-scout
description: >-
  Scout scientifico per prospezione B2B e calcolo del Precision Opportunity Score (POS).
  Analizza nicchie locali e prodotti VibeCoding, calcola il punteggio delle 8 variabili
  (G_dig, V_ticket, F_fin, C_press, M_reach, A_decision, B_care, U_vibe), intercetta
  Red Flag (titolari tossici o fallimenti) e genera automaticamente Action Kit con
  script video Loom da 90s, cold email chirurgiche e prompt prototipo.
---

# Scientific Cold Lead Scout & POS Skill

Questa skill permette all'agente di condurre sessioni di scouting scientifico per individuare aziende locali e ad alto ticket ideali per vendere soluzioni digitali veloci create in **VibeCoding** (micro-app, calcolatori, automazioni, restyling ad alta velocità).

## Quando usare questa Skill
- Quando l'utente chiede di trovare clienti o fare lead generation a freddo su una zona geografica o un settore specifico.
- Quando si vuole valutare il potenziale di vendita ($POS$) di una singola azienda o di una lista di prospect.
- Quando si desidera preparare una sequenza di outreach con script video Loom da 90 secondi, email a freddo e prototipo interattivo pronto.

---

## Esecuzione da CLI

L'agente può invocare lo script Python `skill/run_scout.py` con vari parametri:

```bash
# Esempio standard con report in Markdown
python skill/run_scout.py --niche "Charter barche" --location "Rapallo" --format markdown

# Esempio con pesi manomessi (es. focus solo su automazioni)
python skill/run_scout.py --niche "Ristoranti gourmet" --location "Portofino" --weights '{"w_A": 3.0, "w_G": 2.0}' --format json

# Esempio per generare l'Action Kit (Loom, Cold Email, Prompt Mockup) del miglior prospect
python skill/run_scout.py --niche "Immobiliare di pregio" --location "Santa Margherita Ligure" --format action_kit
```

---

## Le 8 Variabili del Modello POS (0 - 10)

1. **$G_{dig}$ (Digital Gap)**: Sito lento, non responsive o assente.
2. **$V_{ticket}$ (Ticket / Margine)**: Settore ad alto scontrino (yacht, ville, gourmet, cliniche).
3. **$F_{fin}$ (Solidità Finanziaria)**: Forma societaria (S.r.l./S.p.A. storica vs Ditta individuale).
4. **$C_{press}$ (Pressione Concorrenti)**: Concorrenti locali che dominano online con strumenti moderni.
5. **$M_{reach}$ (Frizione Estera / Multilingua)**: Settore per turisti esteri ma senza traduzioni adeguate.
6. **$A_{decision}$ (Accessibilità Decision Maker)**: Titolare contattabile direttamente su WhatsApp o telefono.
7. **$B_{care}$ (Brand Care)**: Titolare attento che risponde alle recensioni online con professionalità.
8. **$U_{vibe}$ (Superficie VibeCoding)**: Processi manuali convertibili in un micro-applicativo in 24h.

---

## Filtro Red Flag ($P_{risk}$)
Prima di proporre qualsiasi lead, scartare immediatamente:
- **Titolare Tossico**: Risponde alle recensioni insultando o minacciando querele.
- **Insolvenza**: Procedure concorsuali o liquidazione.
- **Forte Lock-in**: Sito vincolato a contratto canone con agenzia esterna.
