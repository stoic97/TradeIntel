# Documents cited from this repository

Code, templates and docs cite documents by name: "PRD §7.3", "handoff section 6", "Manual B-9",
"Technical Design", "R-Spec §6.2". This page says where each one lives, its current version,
and who grants access, so a citation never points at nothing (TICKET-936).

**Access.** Every document marked *Project* lives in the claude.ai Project **"plusEV – Scope"**.
The founder, Pawan Rathore, owns it and grants access; ask him. Documents marked *repo* are in
this repository.

`tests/unit/repo/test_references.py` fails if the code names a document that is not listed here.

## Product and build

| Cited as | What it is | Where | Current version |
|---|---|---|---|
| **PRD**, "PRD §x", "PRD section x" | Scope's product requirements | *Project* `scope_prd_v1_2_frozen.md`, with `claude/scope_prd_v1_2_amendments.md` and `claude/scope_prd_v1_2_decision_list.md` | v1.2, frozen 14 Oct 2026; amendments 19 Oct 2026 |
| `prd_v0.1_skeleton.md` (in the Phase 0 plan) | The PRD's first skeleton | Not kept; superseded by v1.2 | superseded |
| **handoff**, "handoff §x", "handoff section x" | The engineering handoff: the Scope UI's phases, gates and release steps | *repo* `docs/product/scope_engineering_handoff_v1.md`; a copy is in the *Project* as `claude/scope_engineering_handoff_v1.md` | v1 |
| **Technical Design**, `scope_v1_technical_design_v1.md` | Scope v1's technical design (cited by ADR-007) | *Project* `scope_v1_technical_design_v1.md` | v1.1, 16 Oct 2026 |
| **build plan**, `scope_v1_build_plan_v1.md` | Scope v1's build plan (cited by ADR-007) | *Project* `scope_v1_build_plan_v1.md` | v1, 16 Oct 2026 |
| `scope_v1_build_completion_v1.md` | What the v1 build completed | *Project* `scope_v1_build_completion_v1.md` | v1, 21 Oct 2026 |
| `scope_thin_slice_plan_v1.md` | The thin-slice plan before the v1 build | *Project* `scope_thin_slice_plan_v1.md` | v1, 12 Oct 2026 |
| **testing register** | Scope's testing register | *repo* `docs/product/scope_testing_register_v1.md`; a copy is in the *Project* | v1 |
| **definitions** | Trading day, the B2 rule, the Journal unit and the import states | *repo* `docs/product/definitions_v1.md` | v1 |
| **Annex H** (multi-leg; spreads) | The multi-leg convention: how legs become one position | *Project* `claude/scope_annex_h_multileg_convention_v2.md` | v2, 4 Nov 2026 |
| **Scope_Feedback**, "Scope_Feedback section x", RN-0001 | T-001's round-1 page-by-page review | Kept by the founder, outside the repo and the Project index, because it is a trader's own words. The loop that acts on it: *Project* `claude/scope_feedback_loop_v1.md`, `claude/scope_feedback_loop_rn0001_status_v1.md`, `claude/scope_rn0002_round2_register_12nov.md` | round 1, 3 Nov 2026; round 2, 12 Nov 2026 |
| **Brand Strategy**, C01–C16, `BRAND_RULES_CARD.md` | The brand strategy chapters and rules card | *Project* folder `Brand Strategy/` | v1.2 (C01–C14), 24 Oct 2026 |
| **design kit** | The Scope UI kit: components, screens, tokens | *repo* `docs/design/scope-kit/` | as committed |

## Research

| Cited as | What it is | Where | Current version |
|---|---|---|---|
| **Research spec**, **R-Spec**, "Spec §x", "Annex B/I/J" | The research specification and its annexes | *repo* `docs/trade_dna_research_spec_v1_0.md` (frozen; SR-011) | see its title and change log |
| **Thesis**, "T§" | The product thesis | *repo* `docs/trade_dna_product_thesis_v1.5.md` (v1.4 kept beside it) | v1.5, frozen 24 Oct 2026 |
| **Workbook**, "B§" | The brainstorm workbook | *repo* `docs/trade_dna_brainstorm_workbook_v1.1_final.md` (frozen; SR-011) | see its title and change log |
| **Phase 0 plan** | Phase 0's plan of work | *repo* `docs/trade_dna_phase0_plan.md` | as committed |

## Process

| Cited as | What it is | Where | Current version |
|---|---|---|---|
| **Developer Manual**, **Manual**, "Manual §x", "Manual B-x" | The Trade DNA Developer Manual: the target-state engineering practice | *Project* `Developer manual` | v1.1, October 2026 |
| **methodology** | What is binding today, by stage; governs where it and the Manual differ on scope or timing | *repo* `docs/methodology.md` | as committed |
| **merge practice** | How a PR gets merged, in full | *Project* `claude/scope_pr_merge_practice_v1.md`; short form in [CONTRIBUTING.md](../CONTRIBUTING.md) | v1.1, 4 Nov 2026 |
| **SR-nnn** | The standing rules | *repo* `docs/process_standing_rules.md` | as committed |
| **TD-nnn** | Deferrals | *repo* `docs/deferrals.md` | as committed |
| **deploy runbook**, **deploy log** | How the live app is updated, and the record of each deploy | *Project* `claude/scope_deploy_update_runbook_v1.md` and `claude/scope_deploy_log.md` | runbook v1.4, 5 Nov 2026 |
