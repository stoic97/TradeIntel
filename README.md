# TradeIntel — PlusEV TradeDNA

Research engine that reads a trader's own trade history and reports, with evidence, where his edge is and where money leaks.

## Layout
| Folder | What |
|---|---|
| `docs/` | Frozen documents: Product Thesis v1.4, Workbook v1.1, Research Specification v1.0, Phase 0 plan |
| `prereg/` | `framework_v1.yaml` — Part I of the Research Spec in machine-readable form — and its SHA-256 hash. Locked at the Phase 0 kickoff; changing it is a major version |
| `importer/` | Broker export → canonical trade record (CTR). One adapter per broker |
| `research_tests/` | The 18 pre-registered tests |
| `fixtures/` | Synthetic or anonymised sample files only |

## Rules
1. **No trader data in this repo. Ever.** Tradebooks stay in a separate, access-controlled folder. `.gitignore` blocks csv/xlsx outside `fixtures/`.
2. **No fund code or fund data in this repo.** The fund/product wall (Thesis §19) is enforced by keeping them apart.
3. **Pre-registrations live here, in git** (Research Spec §14). A change to `prereg/` after the kickoff hash is a major version with a decision-log row.
4. Runner ≠ ruler: whoever runs a charged analysis does not rule on it.
