# Examples

Lead lists you can score with `coldlead import`. All businesses are fictitious.

| File | Shows |
|---|---|
| [`my_leads.csv`](my_leads.csv) | English column names, comma-separated |
| [`my_leads.it.csv`](my_leads.it.csv) | Italian column names (`azienda`, `sito`, `città`, `telefono`…), semicolon-separated |

```bash
coldlead import examples/my_leads.csv --no-audit
```

Column names are matched case-insensitively against English and Italian aliases (see
`FIELD_ALIASES` in `src/coldlead/pipeline.py`); only a name column (`name`, `company`, `azienda`…)
is required. Any other column named like a raw signal (`is_running_ads`, `owner_reply_rate`,
`average_rating` …) is imported as that signal.
