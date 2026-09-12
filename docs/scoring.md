# The Precision Opportunity Score

This document specifies exactly how ColdLead Studio turns raw signals into a ranking. The
implementation lives in [`variables.py`](../src/coldlead/variables.py),
[`scoring.py`](../src/coldlead/scoring.py) and [`red_flags.py`](../src/coldlead/red_flags.py); the
domain tables in [`knowledge.py`](../src/coldlead/knowledge.py).

## Principles

1. **Decoupling.** Raw signals are collected once and cached; scores are never stored. Scoring is a
   pure, deterministic, network-free function of *(leads, configuration)*.
2. **Unknown ≠ bad.** Every signal is optional. A missing value yields a neutral contribution and
   an explicit "unknown" reason instead of a silent penalty.
3. **Explainability.** Every variable returns its value *and* the reasons behind it.

## Formula

```
base      = Σ(w_i · V_i) / Σ w_i × 10                 ∈ [0, 100]
uncapped  = base × M_ads × M_friction × T_win × P_lockin
POS       = min(100, uncapped)                        rounded to 0.1
```

Leads are ranked by `(is_discarded, −uncapped, name)`: red flags always sink to the bottom and
ties at the 100-point cap are broken by the uncapped value.

## Variables (each clamped to [0, 10])

### G_dig — Digital & AI readiness gap (`w_G`)
- No website → **10**.
- Otherwise `(100 − performance) / 10 × 0.6`, plus: not mobile-friendly **+2.0**, no HTTPS **+1.5**,
  no booking/quote tool **+1.0**, legacy stack (WordPress ≤ 4, Joomla, Drupal ≤ 7, Wix, site
  builders, pre-2010 tech) **+1.0…2.0**.
- Unknown performance is assumed to be 50.

### V_ticket — Ticket value & margin (`w_T`)
Highest matching sector rule wins, from 10 (yachts, cosmetic surgery) to 3.5 (bars, cafés);
default 4.0. `ticket_value_hint` in the raw signals overrides it.

### F_fin — Financial strength (`w_F`)
S.p.A. 10 · S.r.l. 9 · Ltd/LLC/GmbH 8.5 · professional firm 7 · S.r.l.s. 6.5 · co-op 6 ·
S.n.c./S.a.s. 5.5 · sole trader 3 · unknown 5. The legal form is parsed from the company name when
not provided. ≥ 10 employees **+1**, no employees **−1**.

### C_press — Local competitive pressure (`w_P`)
Priority: explicit `competitor_pressure` → **session peers** → competitor notes → neutral 5.
Peers are leads in the same sector category and city (groups of ≥ 3). For each lead:

```
quality(l) = performance/20 + 1.5·booking + 1.0·multilingual + 0.5·mobile + max(0, rating − 3)
pressure   = clamp(5 + 0.8 · (mean(top-2 rival quality) − quality(lead)))
```

### M_reach — Foreign-market friction (`w_I`)
A lead is *internationally exposed* if its city is a tourism hub, its niche is structurally
international (yachts, villas, weddings…), or `international_clientele` is set. Exposed and
single-language **9.5** · exposed without website **9** · multilingual unknown **6.5** · already
multilingual **4** · local market **3** (2 if multilingual).

### A_decision — Decision-maker accessibility (`w_D`)
Chain/franchise **1.5** · named owner on WhatsApp **9.5** · named owner or WhatsApp **9** ·
LinkedIn **8** · mobile number **7.5** · landline **6** · email only **4.5** · nothing **3**.

### B_care — Brand care (`w_C`)
Toxic owner **1** · reply rate ≥ 70 % **9** · ≥ 30 % **6** · > 0 % **4** · never **2** · unknown **5**.

### U_vibe — VibeCoding surface (`w_A`)
Baseline 5 · manual bookings/quotes **+2.5** · no chat/FAQ bot **+1.5** · PDF menu/price list
**+1.5** · booking *and* chat already automated **−2**.

## Multipliers

| Factor | Condition | Default |
|---|---|---|
| `M_ads` | `is_running_ads` (Ad Library, Google Ads tag or Meta Pixel evidence) | 1.25 |
| `M_friction` | has a website and (no HTTPS or not mobile-friendly) | 1.15 |
| `T_win` | season: `autumn_winter` (Oct–Feb) / `spring` (Mar–Apr) / `summer_peak` (Jun–Aug) / `year_round` | 1.4 / 1.0 / 0.5 / 1.0 |
| `P_lockin` | footer credits a web agency | 0.85 |

Presets tune these values (see [`presets.json`](../src/coldlead/presets.json)).

## Red flags

| Code | Severity | Trigger | Effect |
|---|---|---|---|
| `TOXIC_OWNER` | CRITICAL | owner tone classified as toxic | discard |
| `LITIGIOUS_OWNER` | CRITICAL | threats, insults, "ti querelo", "polizia postale"… in replies | discard |
| `INSOLVENCY_RISK` | CRITICAL | liquidation, bankruptcy, permanently closed | discard |
| `VENDOR_LOCKIN` | MEDIUM | agency credit in the footer | ×0.85 (discard with `discard_on_lockin`) |

## Tiers

`POS ≥ tier_1_min` (85) → **Hot**: 90-second Loom + interactive micro-prototype.
`POS ≥ tier_2_min` (65) → **Warm**: cold email with two specific screenshots.
Otherwise **Low priority**. Red-flagged leads are **Discarded** regardless of score.
