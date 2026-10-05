# TradeIntel — PlusEV TradeDNA

Research engine that reads a trader's own trade history and reports, with evidence, where his edge is and where money leaks.

## Layout
Layout follows `docs/methodology.md` §5. A folder is created when its first file exists, not before. **Current methodology stage: 0** (see the activation table at the top of that document).

| Folder | What |
|---|---|
| `docs/` | Frozen documents (Thesis v1.4, Workbook v1.1, Research Spec v1.0, Phase 0 plan), `methodology.md`, `adr/`, `runbooks/` |
| `services/shared/schemas/` | Contracts both sides use: `ctr_v1.py`, `evidence_object_v1.py` — versioned by file |
| `services/production/ctr/` | Broker export → Canonical Trade Record. One adapter per broker |
| `services/research/prereg/` | `framework_v1.yaml` + `.sha256` — Part I of the Research Spec, locked at kickoff |
| `services/research/library/` | The 18 pre-registered tests (created with the first test) |
| `data/fixtures/` | Synthetic or anonymised samples only |
| `tests/reproducibility/` | Every transformation run twice; hashes must match |

`make help` lists the commands.

## Rules
1. **No trader data in this repo. Ever.** Tradebooks stay in a separate, access-controlled folder. `.gitignore` blocks csv/xlsx outside `fixtures/`.
2. **No fund code or fund data in this repo.** The fund/product wall (Thesis §19) is enforced by keeping them apart.
3. **Pre-registrations live here, in git** (Research Spec §14). A change to `prereg/` after the kickoff hash is a major version with a decision-log row.
4. Runner ≠ ruler: whoever runs a charged analysis does not rule on it.
