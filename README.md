# PlusEV Scope

## What Scope is

PlusEV Scope is a web app for retail traders. A trader uploads his broker's tradebook (Dhan or Groww); Scope rebuilds his trades and shows him what his own record says - the Mirror, the Journal, what he was charged - counted from his file, with nothing inferred. It runs at https://scope.plusev.in.

The same repo holds the pre-registered research engine (`services/research/`). Production never imports it (methodology Rule 5).

Formerly PlusEV-TradeDNA: the product has been named PlusEV Scope since 10 Oct 2026. The repo and the Python package keep the name `tradeintel`.

## Run it locally

You need git and [uv](https://docs.astral.sh/uv/); uv installs Python 3.11 itself. The `make` lines need a bash shell with `make`: macOS and Linux have both. Windows has no `make`, so use WSL, or a Git Bash with `make` installed, and set `PYTHONUTF8=1` once (several files are read without an explicit encoding, and Windows would read them as cp1252).

1. Install uv, once:

       curl -LsSf https://astral.sh/uv/install.sh | sh

   On Windows PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.

2. Clone and install:

       git clone https://github.com/stoic97/TradeIntel.git
       cd TradeIntel
       uv sync              # Python 3.11 and every dependency group, pinned by uv.lock

3. Make your local keys and paths, once:

       make .dev-env        # writes .dev-env (gitignored, never committed)

   Keep that file. Change its file key and the files you already uploaded stop decrypting.

4. Start the app:

       make run             # creates the database, then serves http://127.0.0.1:8000 with reload

   Then open http://127.0.0.1:8000/signup and sign up the way a trader does. Made-up tradebooks to upload are in `data/fixtures/` and `data/fixtures/demo/`.

   Admin route instead: `uv run python -m services.production.api.cli create-trader --help`.

5. Run the tests:

       make test            # the whole suite, to the end: the deploy check, and what CI runs

   The count line shows a few xfailed: research results known to depend on the platform (TD-023 on macOS, TD-034 on Linux; see `docs/deferrals.md`). `make help` lists every command; `make test-fast` stops at the first failure, for local use only.

## Layout

Layout follows `docs/methodology.md` section 5. A folder is created when its first file exists, not before. **Current methodology stage: 0** (see the activation table at the top of that document).

| Folder | What |
|---|---|
| `services/production/` | The Scope app. It may not import `services/research/` |
| `services/production/accounts/` | Passwords (argon2id), sessions and CSRF; the consent text and its ledger; deletion that executes |
| `services/production/api/` | The FastAPI app: `app.py`, `cli.py`, the `routes_*.py` pages, `/admin`, `templates/` (Jinja) and `static/` |
| `services/production/charges/` | What a trade was charged: statutory rates as a dated, append-only table (`rates.yaml`), brokerage presets (`brokerage.yaml`), the computation |
| `services/production/ctr/` | Broker export -> Canonical Trade Record: one adapter per broker (`adapters/`), the import pipeline (`intake/`), instrument profiles (`profiles/`), fills -> round trips (`reconstruct.py`) |
| `services/production/db/` | The product tables (`models.py`), the engine, session and migration runner, and the column types |
| `services/production/eligibility/` | Which checks a history can support, and which it cannot |
| `services/production/journal/` | The Journal: its fields, periods and prose, and which five he sees |
| `services/production/mirror/` | The Mirror: `metrics.py` is the one place each figure is decided; the loader, the guess before the reveal, chapter feedback |
| `services/production/prices/` | Price-series layer: one 1-minute series per underlying (`underlyings.yaml`) |
| `services/production/replay/` | Blind replay: his real entries mixed with random moments, the result hidden |
| `services/production/rules/` | Rules a trader sets by tapping, and whether he kept them |
| `services/research/` | Pre-registered research. Production never imports it, and the server does not install its packages |
| `services/research/engine/` | Promotion evidence and the four zones (Research Spec sections 4.6, 5.2) |
| `services/research/evaluation/` | Null rate, simulation-based calibration, the finding bar; `synthetic/` is corpus A (`docs/phase0/corpus-a.md`) |
| `services/research/library/` | The pre-registered tests; `b2.py` (post-loss expectancy) is the template for every test |
| `services/research/models/` | Shared fitting machinery, M1's conjugate core, the ADR-006 benchmark record |
| `services/research/prereg/` | `framework_v1.yaml`, the pre-registered framework (+ `.sha256` once locked at kickoff) |
| `services/shared/` | What production and research both use: the only place both may reach |
| `services/shared/conditions/` | The B2 condition, defined once; B2's shuffle test; the halves shuffle for the plain-counts page |
| `services/shared/market/` | Market calendars as data: exchange closures, MCX part sessions |
| `services/shared/prereg/` | The pre-registered framework, read by the product (eligibility thresholds) |
| `services/shared/schemas/` | Contracts both sides use: `ctr_v1.py`, `ctr_v2.py`, versioned by file |
| `migrations/` | Alembic. `versions/` is one chain; a new table is a new file whose `down_revision` is the current head |
| `deploy/` | The droplet: `Caddyfile`, the systemd units, `backup.sh`, `restore-drill.sh`, `refresh-staging.sh`, `staging.env.example` (runbook: `docs/runbooks/deploy.md`) |
| `docs/` | `methodology.md`, `deferrals.md`, `process_standing_rules.md`, `references.md`, and the frozen documents (Thesis, Workbook, Research Spec, Phase 0 plan; they change only by a version bump, SR-011) |
| `docs/product/` | The Scope build spec (`scope_engineering_handoff_v1.md`), the shared definitions (`definitions_v1.md`), the trade-count reconciliation, the broker connector note |
| `docs/design/` | The design kit and screens; start at `docs/design/README.md` |
| `docs/adr/` | Architecture decisions, ADR-001 onward |
| `docs/runbooks/` | Deploy, data deletion, the data-flow map, charge rates, the crude series |
| `docs/phase0/` | Phase 0 method findings, corpus A, measured results |
| `docs/architecture/` | `tech-stack.md`: what the ADRs add up to |
| `docs/research/` | Research experiment records (`experiments/`) |
| `data/` | Synthetic data and records only. No trader data, ever (rule 1) |
| `data/fixtures/` | Synthetic or anonymised samples only |
| `data/golden/` | Golden outputs regenerated by `scripts/regenerate_golden.py`, never hand-edited |
| `data/market/` | Market data crossed from the fund (ADR 002): data files gitignored, `CROSSINGS.md` is the record |
| `data/null_rate/` | Records of the B2 null-rate and recall runs |
| `data/corpus/` | Built corpora - gitignored; they regenerate from code + seeds |
| `scripts/` | Runners and jobs outside the app; one row each in Scripts below |
| `tests/` | pytest; `tests/conftest.py` sets the environment and a per-test SQLite |
| `tests/unit/` | Unit tests by area; `tests/unit/repo/` holds the repo guards (no trader data, references, Makefile, this README) |
| `tests/integration/` | Upload to stored trips, through every layer |
| `tests/reproducibility/` | Every transformation run twice; hashes must match; pinned digests |
| `tests/fixtures/` | Test fixtures: the Mirror contract, the frozen Mirror wording, the dial geometry |
| `tests/helpers/` | What test files share; a test file never imports another test file |
| `.github/` | The pull request template and the CI workflows |

## Scripts

Each runs from the repo root with `uv run python scripts/<name>`, unless its row says otherwise. The scripts run only by hand open with three lines: who runs it, when, and what it writes.

| Script | What it does | When it is run | Still in use |
|---|---|---|---|
| `benchmark_m1_core.py` | Measures effective samples per second for M1's conjugate core on each sampler backend (ADR-006); writes `docs/phase0/adr-006-benchmark.json` | By hand, when ADR-006's sampler choice is revisited | Yes, research; kept by founder ruling, 19 Nov 2026 |
| `build_corpus_a.py` | Builds corpus A (planted histories and nulls) into `data/corpus/`; `--quick` for a smoke run | When corpus A is rebuilt (`docs/phase0/corpus-a.md`) | Yes, research |
| `build_exchange_closures.py` | Writes the NSE and BSE closure days into `services/shared/market/exchange_closures.yaml` from the exchanges' daily bars; run with `uv run --with fyers-apiv3` and a token file | Monthly, with the crude refresh | Yes |
| `check_charge_rates.py` | Prices made-up orders with `rates.yaml` and with two brokers' published rates; exits 1 if they differ; never edits the table | As a job (`docs/runbooks/charge-rates.md`) | Yes |
| `extend_crude_series.py` | Brings the MCX crude 1-minute series current; run with `uv run --with fyers-apiv3` and a token file | Monthly (`docs/runbooks/crude-series.md`) | Yes |
| `first_real_run.py` | Runs the import on one real tradebook and prints counts only; writes nothing. The tradebook stays outside the repo and nothing it prints is committed: no real trader's history or figure goes in git (rule 1) | By hand, when an import needs checking on a real file | Yes, by hand; kept by founder ruling, 19 Nov 2026 |
| `lock_charge_rates.py` | Pins new rows of `rates.yaml` in its lock file; refuses if a pinned row changed | After appending rows to `rates.yaml` | Yes |
| `make_groww_fixture.py` | Writes the made-up Groww fixture workbook, the same bytes on every OS | When the Groww fixture changes | Yes; the Groww golden test uses it |
| `mirror_report.py` | The concierge HTML report: a second way of rendering the Mirror, outside the app; writes under `out/` (gitignored); `tests/unit/test_sold_trades_accounted.py` imports it | No longer run: the app's Mirror (`services/production/mirror/`) replaces it | Retired - removal in TICKET-989 |
| `real_shape_check.py` | Checks, in aggregates only, whether a trader's data has the shape M1 assumes; prints only, writes nothing, and what it prints is never committed (rule 1) | By hand, when M1's shape assumption is in question; TICKET-897 Stage A cites it | Yes, research; kept by founder ruling, 19 Nov 2026 |
| `regenerate_golden.py` | Shows the golden diff and, with `--yes`, rewrites `data/golden/` (`--groww` for Groww's) | Only when a behaviour change is intended | Yes |
| `run_null_rate_b2.py` | How often B2 fires on corpus A's nulls, with nothing planted (Research Spec section 6.2); writes `docs/phase0/null-rate-b2.json` (`recall-b2.json` with `--planted`), rows to `data/null_rate/` | TICKET-897 Stage A, step 5 | Yes, research |
| `run_sbc_m1.py` | Simulation-based calibration of M1, 1,000 replications (Research Spec section 6.4); writes `docs/phase0/sbc-m1.json` | TICKET-897 Stage A, step 6 | Yes, research |

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

## Where the docs live

- [docs/README.md](docs/README.md) - the index of every document (written under the repo audit, Order 6; until it lands, start from the lines below).
- `docs/product/scope_engineering_handoff_v1.md` - the Scope build spec. If anything elsewhere disagrees, it wins.
- `docs/product/definitions_v1.md` - trading day, same-day vs held, B2, net vs gross, win and loss.
- `docs/methodology.md`, `docs/deferrals.md`, `docs/process_standing_rules.md`, `docs/adr/`.
- How a change reaches `main` (branches, commits, review, merge): [CONTRIBUTING.md](CONTRIBUTING.md). Where the documents the code cites live: [docs/references.md](docs/references.md).
