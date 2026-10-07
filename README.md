# TradeIntel — PlusEV TradeDNA

Research engine that reads a trader's own trade history and reports, with evidence, where his edge is and where money leaks.

## Layout
Layout follows `docs/methodology.md` §5. A folder is created when its first file exists, not before. **Current methodology stage: 0** (see the activation table at the top of that document).

| Folder | What |
|---|---|
| `docs/` | Frozen documents (Thesis v1.4, Workbook v1.1, Research Spec v1.0, Phase 0 plan), `methodology.md`, `adr/`, `runbooks/`, `architecture/`, `phase0/` (method findings, corpus A) |
| `services/shared/schemas/` | Contracts both sides use: `ctr_v1.py` (and `evidence_object_v1.py`, when written) — versioned by file |
| `services/production/ctr/` | Broker export → Canonical Trade Record. One adapter per broker |
| `services/research/prereg/` | `framework_v1.yaml` (+ `.sha256` once locked at kickoff) — Part I of the Research Spec |
| `services/research/evaluation/synthetic/` | Corpus A: the synthetic market layer, base trader, 17 planted behaviours, the grid and nulls, CTR export (`docs/phase0/corpus-a.md`) |
| `services/research/library/` | The 18 pre-registered tests (created with the first test) |
| `data/fixtures/` | Synthetic or anonymised samples only |
| `data/golden/` | Golden outputs regenerated from fixtures, never hand-edited |
| `data/market/` | Market data crossed from the fund (ADR 002): data files gitignored, `CROSSINGS.md` is the record |
| `data/corpus/` | Built corpora — gitignored; they regenerate from code + seeds |
| `scripts/` | One-off runners (`build_corpus_a.py`, `first_real_run.py`, `regenerate_golden.py`) |
| `tests/reproducibility/` | Every transformation run twice; hashes must match; pinned digests |

`make help` lists the commands.

## Rules
1. **No trader data in this repo. Ever** — and that includes anything *derived* from
   one trader's history: a count, a rate, a distribution, a holding-time median. Git
   history cannot be deleted on request, so a trader fact committed here breaks the
   deletion promise made to recruits. Findings split three ways:
   - **about the method** (instrument-agnostic, no trader in it) → `docs/phase0/method-findings.md`
   - **about one trader** → outside the repo, beside the tradebooks, under the deletion runbook
   - **across partners** (a distribution, not a profile) → the repo, at week 8
   This applies to commit messages too. `.gitignore` blocks csv/xlsx outside `fixtures/`.
2. **No fund code or fund data in this repo.** The fund/product wall (Thesis §19) is enforced by keeping them apart.
3. **Pre-registrations live here, in git** (Research Spec §14). A change to `prereg/` after the kickoff hash is a major version with a decision-log row.
4. Runner ≠ ruler: whoever runs a charged analysis does not rule on it.
