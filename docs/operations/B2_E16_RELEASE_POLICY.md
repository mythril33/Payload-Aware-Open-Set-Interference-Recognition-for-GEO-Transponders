# B2 E16 — DR-04 release policy

2026-10-25. Policy and engineering contract only. **DR-04 NO-GO — NO COMPUTE AUTHORIZED.** Nothing here approves,
schedules or starts generation. The real canonical gates, the scientific approvals and every guard are unchanged.

## 1. Three things that must never be confused

| Thing | Where it lives | E16 treatment |
|---|---|---|
| **Scientific approvals** — K18, K17d, OBS-CANCEL-2, R1–R10, D-1–D-8 | gates JSON, memorandum twin, `b2_e9_approved_scientific_protocol.json`, E12 register | immutable history; E16 reads and re-checks them (approver, instant, record, choice, 13 decisions) and never edits them |
| **Canonical compute gates** — `full_generation`, `full_gpu_training`, `full_loko_sweep` | same JSON files | all `NOT_AUTHORIZED`; the readiness CI asserts it; E16 changes nothing |
| **DR-04 operational record** — the researcher's committed compute authorization for generation only | a `docs/` record that does not exist yet | E16 can *recognise* a complete one (and tell it from a forged one); it cannot create, sign or act on one |

Scientific approval is not compute authorization. A green CI run, an independent review (human or model), a consistent
plan and a valid-looking record are all evidence; none of them starts anything. Even
`DR04_GENERATION_RECORD_VALID` reports `verdict=NO-GO`, `execution_permitted=false`.

## 2. States

`python scripts/b2_e16_policy.py ci-gate` and `classify_gates` return one of (an enumerated check over the listed fields, read strictly; it does not prove that no other
field anywhere in a document says otherwise):

| State | Gate JSON + twin | `ci-gate` exit | Accepted by CI today |
|---|---|---|---|
| `CLOSED_CANONICAL` | the three compute gates exactly `NOT_AUTHORIZED` with no approval; scientific half intact; no other decision open; strict JSON | 0 | **yes** |
| `OPEN_CANDIDATE_REQUIRES_RECORD` | only `full_generation` open, consistently, with structurally complete provenance | 3 | no |
| `DENIED` | anything else: one-sided or partial opening, another compute gate opened, a scientific approval altered, `benchmark_complete` changed, GPU probe/production launch not closed, `merge_to_main` open | 2 | no |

`evaluate_operational_authorization` adds the record-level result `DR04_GENERATION_RECORD_VALID` (a statement about
documents) or `DENIED`.

## 3. Scope

The only grantable scope is `{"gate": "full_generation", "stages": ["known", "test", "matched"]}` — exactly this, in this
order, with no other field. Every other request is refused by name and in every state:
`gpu_probe`, `full_gpu_training`, `full_loko_sweep`, `nine_cell_freeze`, `held_out_final_evaluation`,
`production_launch_flag_change`, `d5_sweep`. Opening one of the other compute gates alongside `full_generation` makes
the whole state `DENIED`.

## 4. The committed record

The researcher (not the plan author, not a model) writes and commits a record under `docs/` (never one of the scientific
approval records, never a copy of one). It must contain **two** fenced `json` blocks:

1. the E13 approval block `B2-E13-dr04-approval-block/1` (`decision`, `approved_by`, `approved_plan_digest`, `host_id`,
   `expires_at`, validity ≤ 30 days; `B2_E13_DR04_APPROVAL_CHECKLIST.md`), and
2. the E16 operational block below.

```json
{
  "schema": "B2-E16-dr04-operational-block/1",
  "scope": {"gate": "full_generation", "stages": ["known", "test", "matched"]},
  "approved_by": "<the researcher who ratified the scientific protocol>",
  "expires_at": "<ISO-8601 instant, the same as the E13 block>",
  "approved_plan_digest": "<E13 approved_plan_digest, 64 hex>",
  "reviewed_code_commit": "<40-hex commit R of the final reviewed code>",
  "host_id": "<designated host>",
  "working_storage_id": "<measured working storage id>",
  "backup_storage_id": "<measured backup storage id>",
  "ceilings": {"wall_hours": 0, "core_hours": 0, "max_rss_gib": 0, "min_free_disk_gib": 0, "backup_disk_gb": 0,
               "max_failed_attempts_per_stage": 0, "max_interruptions_per_stage": 0},
  "revocation_id": "<identifier that a revocation source can invalidate>",
  "signature": {"scheme": "git-signed-commit | ssh-signature | gpg-detached-signature", "evidence_sha256": "<64 hex>"}
}
```

This is a **template with placeholder values, not an approval and not a decision.** The ceilings above are zeros on
purpose: the researcher chooses them (proposed, unapproved reference: 36 h / 42 core-h / 2 GiB RSS / 25 GiB reserve /
9 GB backup floor / ≤ 2 failed attempts / 20 interruptions).

## 5. What the policy checks

All of the E13 authorization checks (basis, record, approver, provenance, binding to plan/lock/host/storage, ceilings,
scope, gate, supervisor view, scope isolation) plus, in E16:

1. requested scope is exactly the grantable scope;
2. the canonical gates are classified consistently and every other compute gate is closed in both the gate and the twin;
3. K18/K17d/OBS-CANCEL-2 agree between gate, memorandum twin and protocol (approver, instant, record, choice);
4. the E13 validator finds the plan complete and consistent (no failure, no blocked prerequisite);
5. the reference was collected within the freshness bound (stale environment lock, host report or checkout refused);
6. the authorization is unexpired at the injected time;
7. the parsed record text is byte-for-byte the document whose hash the authorization cites (no TOCTOU, no truncation);
8. exactly one E16 block with exactly the contract fields, restating scope, approver, expiry, digest, host, both storage
   ids and every ceiling;
9. gate approval, plan authorization, record block and ratified protocol agree on approver, instant, decision and record;
10. an injected **signature verifier** returned exactly `True` for this record, signer and signature reference;
11. an injected **ancestry checker** shows `reviewed_code_commit` is a strict ancestor of the plan commit and that only the
    gate JSON, its memorandum twin and the record changed since (a code, config, test or workflow change voids it);
12. an injected **revocation query** answered fresh and negative.

A missing adapter, an adapter that raises, or a malformed answer is a refusal. Real adapters (a signature verifier that
checks a signed commit against a pinned allowed-signers file, a read-only `git merge-base`/`git diff --name-only`, a
revocation source) **do not exist yet**; building them is recommended E17 scope.

## 6. Release order and the hash cycle

`check_release_order` enforces: `final_reviewed_code` → `design_digest` → `researcher_authorization` →
`authorization_commit` → `final_lock` → `revalidation` → `launch_decision`. The design digest excludes exactly what later
steps create; every later step restates and is compared with it. The authorization commit must be a direct child of the
reviewed commit; the lock must be created on the authorization commit (the gates JSON is hashed into it); the
revalidation must use that lock and the same digest. A `launch_decision` is a separate decision that this build refuses to
record. No hash is omitted and no guard is bypassed to break the cycle. Details: [B2_E16_PRODUCTION_INTEGRATION.md](../plan/B2_E16_PRODUCTION_INTEGRATION.md) §5.

## 7. The readiness-CI conflict and the future reviewed change

Today `b2-readiness-ci.yml` asserts, for `full_generation`, `full_gpu_training` and `full_loko_sweep`:
`status == NOT_AUTHORIZED`, `approval is None`, twin `approved_by`/`approved_at` null. **E16 does not edit that
workflow** and does not weaken it.

When (and only when) a researcher has given a DR-04 authorization, a **separate, reviewed change that is part of the
final reviewed code R** (never the authorization commit A) may replace the `full_generation` iteration of that loop with a
call to the policy. It must:

* keep the existing assertions for `full_gpu_training` and `full_loko_sweep`;
* accept `full_generation` only as `CLOSED_CANONICAL`, or as `OPEN_CANDIDATE_REQUIRES_RECORD` **and** a successful
  full operational evaluation with real adapters — never on the shape of the gate alone;
* be tested, before merge, against all four fixture families that `tests/test_b2_e16_policy.py` already encodes:
  the real closed gates (accepted), an approved-shaped record (accepted only with all adapters), a forged gate without a
  record (rejected), and partial / one-sided / contradictory / stale / expired / revoked variants (rejected);
* keep the scientific half of the step (13 ratified decisions, approver/instant/record equality, flags) byte-for-byte.

Until then the scoped E16 workflow runs `ci-gate` against the real files and requires `CLOSED_CANONICAL`.

## 8. Revocation and expiry

Authorizations are short-lived (≤ 30 days, E13) and revocable by id. The stop evaluator re-checks expiry and
revocation at every stage boundary; an expired or revoked authorization stops admission of the next stage. Revocation
never deletes evidence: the run halts, the ledger records the incident, quarantine notes preserve files in place.

## 9. Authority of reviews

A model-agent review is an engineering check by an agent independent of the author. It is **not** human release
approval and cannot supply a signature, a DR-04 decision, a host designation or a launch decision.
