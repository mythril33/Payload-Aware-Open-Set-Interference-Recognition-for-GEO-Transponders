# B2 E17 — trusted release evidence

Version 1, 2026-10-25. Verified base:
`d82873967d6eb3a3f8f75a3f0ec9f89637e5873e` (PR #40 merged).
**Engineering only — DR-04 NO-GO — NO COMPUTE AUTHORIZED.**

## Prioritized audit

| Priority | Verified defect or gap before E17 | Required E17 disposition |
|---|---|---|
| P0 | PR #40 final-head readiness run was still in progress at task start | Both final-head runs are now verified successful from raw logs: integration 2040 passed; readiness 107 + 3844 passed, zero skips, 46 existing warnings. E17 has separate exact-head evidence |
| P0 | E15 compares living source/scripts/tests with its historical 9e176ad snapshot, so a legitimate later engineering update can fail an archival dossier check | Validate the historical dossier as history, separately protect frozen science and current closed authority, and test legitimate later source changes versus altered scientific records |
| P1 | E16 signature/ancestry/revocation callbacks were injected assertions; default absence correctly denied but no cryptographic or object-history adapter existed | Add bounded read-only adapters; keep the original E16 policy as the evaluator rather than reimplementing its contract |
| P1 | A name, Verified string, unsigned CI success or absent revocation entry is not authenticated evidence | Independently pinned signer/issuer policy, exact signed bytes, exact Git objects, explicit fresh grant status and authenticated exact-head CI evidence |
| P1 | Evidence can be replayed, expired or applied to a different record/design/source | Bind request challenge, validity, source/reviewed/approval identity, record/design digests and externally retained replay state; fail closed on any missing dependency |
| P2 | No production executor calls the E16 controls; host, backup, journal, real trust services, DR-04 and launch authorization remain absent | Prepare the bounded E18 integration handoff only; no E18 implementation or production launch |

PR #40 head was `3d0b24625c582b472d27fc77524c60f7b1265f27`.
Its merge is not evidence that its CI succeeded. E16's documentation and earlier
code-head results are historical evidence, not substitutes for the final-head
run conclusions. See [verification](../results/B2_E17_VERIFICATION.md).

## Trust boundary

E17 separates cryptographic verification from operational authorization. A
signature proves that a configured private-key holder signed exact bytes; it
does not establish that the key belongs to the researcher. That association must
come from an independently reviewed and pinned trust root, not from the record
author's identity claim. No real signer or revocation authority is configured
by this milestone. Missing trust returns `BLOCKED_TRUST_ROOT_MISSING` or the
applicable blocked evidence result, never approval.

The supported detached-signature path uses Ed25519 SSHSIG and purpose-separated
namespaces. Product code verifies; it creates no signing key and exposes no
signing API. Fabricated keys in temporary test repositories are test trust roots,
not researcher approval. No private key, credential, real authorization or real
revocation entry is committed.

The actual public integration entry is
`scripts/b2_e17_evidence.py:evaluate_trusted_authorization`. Its application trust
root is the literal `PINNED_TRUST_ROOT=None`; there is no caller, environment or
approval-JSON root override. Closed canonical gates can still be classified as
closed. An open candidate cannot pass trusted admission without a separately
reviewed root configuration. The internal configured-root harness labels its
results `SYNTHETIC_TEST_ROOT`; it is not a provisioned production root.

The low-level APIs are `b2_e17_signatures.verify_signature`,
`b2_e17_git.verify_lineage`/`read_blob`, and
`b2_e17_evidence.verify_revocation`/`verify_ci_snapshot`. They return verification
evidence under the supplied context, not an approval. The integration constructs
E16's callbacks only after these checks and exact Git-object reads succeed.

| Evidence | Trusted verification | What is insufficient |
|---|---|---|
| Signature | Exact canonical record bytes, configured principal, allowed public key and purpose, independently pinned policy digest | Embedded signer name, public key supplied by the same untrusted record, Verified field, boolean callback |
| Git lineage | Exact reviewed R and approval A objects; A is the direct single-parent child; only gate, memorandum twin and a new grant record may change; source/config/tools unchanged | Branch name, stale SHA, supplied changed-path JSON, overwritten historical record, unexpected merge or replaced history |
| Revocation | Independently authenticated issuer; explicit status for the bound grant; issued/expiry/freshness and challenge/replay checks | Missing entry interpreted as active, unsigned list, stale cache or unreachable source |
| CI | Independently authenticated evidence for the exact repository/head and required workflow identities, terminal successful conclusions and freshness | A plan author's success string, wrong head, unrelated workflow or old green run |

Trusted configuration and replay anchors remain external dependencies. A caller
that controls both a root pin and its evidence can invent a trust domain; accepting
such a pair is not real researcher authentication. A future executor must obtain
these inputs from separately reviewed operator-controlled configuration.

For the E17 SSH profile the operational block keeps `scheme="ssh-signature"`.
Its `evidence_sha256` is the canonical allowed-signers policy digest, which is
independently pinned and known before signing. Detached signature bytes are
provided separately, never embedded in the signed record. The signature covers
the entire exact committed record, including the policy reference, design digest
and reviewed commit. This avoids a self-referential signature-byte hash without
omitting any signed record field.

## E16 semantics and integration

The trusted entry path constructs evidence-backed adapters and calls the existing
E16 operational evaluator. It does not accept an untrusted author's replacement
callback that simply returns True. Historical E16 callback fixtures remain useful
for unit tests and are identified as mocks, not trusted production evidence.

| State | Meaning in E17 |
|---|---|
| `CLOSED_CANONICAL` | Current real canonical compute gates are closed and the scientific records agree |
| `OPEN_CANDIDATE_REQUIRES_RECORD` | A DR-04-only gate has an approved shape; full independently verified record evidence is still required |
| `DENIED` | Inconsistent, forged, stale, revoked, wrong-scope or otherwise invalid evidence |
| `DR04_GENERATION_RECORD_VALID` | The record checks passed under configured trust; still a document-level result, never runtime permission |

Even the closed-state entry binds its gate, memorandum and scientific-protocol
documents to exact committed bytes and a clean checkout. A caller-supplied closed
snapshot cannot hide an actually open checkout. The read-only Git adapter rejects
skip-worktree/assume-unchanged flags and ignored importable content, including
Python bytecode caches. Verification requires a cache-free evidence checkout;
it never deletes or cleans the caller's files. The running verifier, OS and import
loader must themselves be trusted and locked by the future deployment process.

Every result remains `execution_permitted=false`. The E9 guard, E14/E16 execution
refusals, `PRODUCTION_LAUNCH_ENABLED=False` and the two-group runnable fixture
ceiling remain intact. No production subprocess, generator callback or launch
entry point is exposed by these read-only adapters.

## Preserved science and provenance

No new model, dataset or evaluation protocol is introduced. Preserve R1–R10,
D-1–D-8, 21,350 observations, 2,450 groups, 739 shards, source/config/cancellation
physics and historical artifact/checkpoint identities. D-1 remains non-pristine,
with headline 500/150 groups and mandatory 498/148 exposure-exclusion rows. D-8
retains exact 500/co35/cross43/total78/complement465 identities; actual production
metadata cross-verification is not performed here.

E17 script changes intentionally change tool-bound plan/design identity. Future
plans and locks must bind the final reviewed code; no historical result or
checkpoint is relabelled. A later geosim change still requires the explicit D-8
provenance re-derivation/review/acceptance sequence before reuse.

## Limitations and next step

Read-only evidence verification does not authenticate physical storage, designate
a host, create a persistent journal, enforce runtime resources or authorize a
process. Snapshot checks cannot prevent a later hostile filesystem change.
Signature validity also does not provide a trusted wall clock or durable replay
storage. See [signer/revocation policy](../operations/B2_E17_SIGNER_REVOCATION_POLICY.md),
[CI authority matrix](../operations/B2_E17_CI_AUTHORITY_MATRIX.md) and
[E18 handoff](B2_E18_EXECUTOR_INTEGRATION_HANDOFF.md).
