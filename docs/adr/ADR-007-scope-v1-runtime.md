# ADR 007: Scope v1 runtime — one Python process, server-rendered, SQLite, one droplet

**Status.** Accepted. **Date.** 2026-10-16. **Deciders.** Founder/CEO, Engineering. **Design.** Project document `scope_v1_technical_design_v1.md` (v1.1); build plan `scope_v1_build_plan_v1.md`.

## Context

PRD v1.2 is frozen. v1 is infrastructure with a user-facing surface: invite-only intake, reconstruction, risk budget, eligibility, the Mirror with an evidence drawer, the Journal, consent and deletion. It serves a handful of invited design partners before the research gate; no Findings, no LLM, no payment. One builder. The data-flow map in PRD §10 is a release gate, so every external service is a cost to be justified. ADR-004 fixes Python 3.11 + uv; ADR-005 fixes SQLite at Phase 0 and Postgres 16 at Phase 1; the methodology forbids production importing research (Rule 5) while the PRD requires the Mirror and the research library to share one B2 function.

## Decision

| Concern | Choice |
|---|---|
| UI | Server-rendered: FastAPI + Jinja2 + HTMX vendored into our static folder. No frontend build. The methodology's `web/` stays reserved for the Phase 1 React app. |
| Database | SQLite (WAL) via SQLAlchemy 2 + Alembic, schema portable; Postgres 16 at Phase 1 per ADR-005. |
| Raw files | On the server disk, named by the SHA-256 of the uploaded bytes, never modified; encrypted at rest with a server key held in `/etc/scope/` and in the founder's password manager; the restore drill proves recoverability. |
| Hosting | One DigitalOcean Basic Droplet, Bangalore, under a product-only account; Caddy + Let's Encrypt; systemd; daily droplet backups. Hostname `scope.plusev.in` when DNS is available; self-signed TLS for internal testing until then. |
| Login | Invite code redeemed once, then login id + password (argon2id). Credentials handed to beta traders directly. No email service exists in v1. |
| Uploads | Synchronous in the request, with stated size and row caps. No queue, no worker. |
| Prose | Deterministic Jinja2 templates over counted facts. No LLM until a Finding exists (Manual B-9). |
| B2 condition | `population_and_condition()` moves byte-for-byte to `services/shared/conditions/b2_condition.py`; research imports it from there. Only `shared` satisfies both the PRD's one-function rule and methodology Rule 5. |
| Dependencies | Research stack (`numpyro`, `pymc`, `nutpie`, `arviz`) in a `research` dependency group; the server installs runtime only. Each new runtime dependency carries a note in `pyproject.toml`. |
| Interpreter | uv-managed CPython **3.11.5** (ADR-004: minor pinned, patch recorded). pyenv's 3.11.5 on the builder's Mac lacks `_lzma` and is not used. |
| Sealing | No admin view of any trader's Mirror or Journals; the admin CLI reads no trade data. Proposed as a standing rule for the kickoff minutes. |

## Consequences

- The data-flow map is: the droplet, its backups, Let's Encrypt (hostname only), the trader's browser. Nothing else.
- Every trader-facing page stamps the import version and code version it was computed from.
- Every versioned table in the design is insert-only in code; corrections are new rows.
- Password resets and account creation are admin CLI commands, not self-service.
- Deletion confirmation is shown on screen and recorded, not emailed — a stage-0 substitution for Thesis §19.4's email, to be minuted at the kickoff.
- Moving to Postgres, a worker, or a React front end is additive; none requires revisiting this ADR.
- Phase 0 proceeds on a `main` with one named red (TD-023, research layer).

## Alternatives considered

- **Next.js app (in TradeIntel or on Vercel) calling a JSON API.** Rejected for v1: two runtimes and two deploys for one builder; on Vercel, a third party renders trader data and enters the consent text.
- **Postgres now.** Deferred, not rejected: ADR-005 already schedules it for Phase 1; nothing in v1 needs it.
- **Background worker or queue.** Rejected: reconstruction of a few thousand rows takes seconds; a second process adds supervision for no v1 benefit. Documented as a one-day upgrade.
- **Email magic-link login.** Rejected by founder ruling on 16 Oct in favour of handing credentials to a handful of beta traders; it would have added the only non-hosting vendor to the map.
- **Managed PaaS or a fully managed cloud stack.** Rejected: few Indian regions, longer data-flow map, higher cost for a load that fits a ₹500/month box.
- **A free-tier VM (Oracle).** Rejected: no SLA, reclaim risk, and other people's tradebooks on it.
- **An LLM for Journal prose.** Rejected for v1: the voice is counted prose, every number must resolve to a field, and the thesis reserves narration for promoted Findings.
