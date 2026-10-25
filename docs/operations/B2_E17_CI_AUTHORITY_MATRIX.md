# B2 E17 — CI authority matrix

Version 1, 2026-10-25. **DR-04 NO-GO — NO COMPUTE AUTHORIZED.**
Green CI is engineering evidence, not researcher authorization or permission to
launch generation. Real canonical compute gates remain closed.

## Historical snapshots versus living checks

E15's dossier describes the source and unqualified host state at its recorded
baseline. It must stay immutable history. Comparing every later living source,
script and test with that baseline turns a historical report into an unintended
freeze on future engineering. E17 repairs this assumption without deleting the
scientific-integrity or authority checks.

The distinction is deliberate: historical dossier bytes and their stated
baseline are checked as historical evidence; frozen scientific/physics/approval
records stay protected; living source/tool provenance is checked against the
current reviewed identity and relevant tests. Legitimate later source updates
must not be labelled alterations to the E15 historical snapshot. Actual changes
to a protected scientific or historical record must still fail.

## Scoped authority cases

| Submitted situation | Required classification / result | Execution permitted |
|---|---|---|
| Real canonical gates closed, scientific approvals and twins agree | `CLOSED_CANONICAL`; current closed-state CI may pass | false |
| DR-04-only approved shape, record evidence incomplete | `OPEN_CANDIDATE_REQUIRES_RECORD` or denied full evaluation; shape alone never passes trusted admission | false |
| Complete DR-04-only record with configured independent signature, Git lineage, fresh explicit revocation status and exact-head CI evidence | `DR04_GENERATION_RECORD_VALID` as a document-level result only | false |
| Forged/unsigned/unknown-signer record or caller-provided Verified/success string | `DENIED` / blocked trust; CI cannot supply identity | false |
| Wrong reviewed/approval parent, unreviewed code/config/tool/workflow change, replacement history, stale SHA or wrong lock | `DENIED` | false |
| Expired, revoked, stale, replayed, unavailable revocation evidence | `DENIED` / blocked evidence | false |
| Wrong CI repository/head/workflow, nonterminal or failed conclusion, unauthenticated snapshot | `DENIED` / blocked evidence | false |
| Gate/memorandum contradiction, changed scientific approval or benchmark flag | `DENIED` | false |
| GPU probe/training, LOKO, held-out evaluation, D-5, freeze or launch-flag grant | `DENIED`; those scopes remain separately unauthorized | false |

The future-open cases use temporary repositories and fabricated signed test
evidence only. They do not alter real canonical records. A test signature proves
the verifier works under the configured test root, not that a researcher approved
generation.

## Workflow boundaries

The readiness, E15 and E16 workflows are audited as distinct checks. Fixing an
archival E15 comparison does not disable readiness tests or globally skip a suite.
Current-state gate protection must continue to reject any unrecorded or malformed
opening. A future scoped policy may recognize DR-04 only after independent evidence
verification; it must retain closed GPU/training/LOKO and all scientific assertions.

Exact-head CI evidence names the actual repository, source head, required workflow
identities and terminal conclusions. A prior code head, a merge event alone, an
unrelated green workflow or an author's unsigned JSON is not equivalent. When no
trusted credentialed reader or reviewed authenticated snapshot is available,
external CI evidence remains blocked rather than synthesized from UI text.

The implemented external-evidence path is an independently signed snapshot, not
a live GitHub network client. Its application root pins the repository and exact
required workflow paths. Each signed run must identify a unique positive run ID
and attempt, a unique positive job ID with completed/success job status, the same
source head, an allowed event, completed status and success conclusion; missing,
extra or duplicate workflows/jobs are refused. The E13 run and job claims must
match this authenticated evidence. The attestor must
obtain real authenticated GitHub results independently and retain their raw
evidence before signing. No such real attestation service or key is configured.
Current tool-based delivery CI inspection is reported as delivery evidence and
does not provision this future runtime CI trust service.

The E17 scoped workflow and focused tests are bounded CPU/synthetic/metadata work.
No new production job, GPU discovery, model fitting, held-out inference or dataset
generation step is introduced. Any original readiness workflow's outcome must be
reported for the exact head actually tested, with failures, cancellations, skips
and warnings preserved rather than conflated with a smaller scoped run.

## Required audit evidence

The delivery record must provide exact main, branch/head, run/job IDs, actual
pass/fail/skip/warning counts, independent review disposition, and any unavailable
trust dependency. Baseline runs40184290052 and40184289910 belong to PR #40's final
head, not the new E17 head. Only observed terminal conclusions may be called
successful. See [verification](../results/B2_E17_VERIFICATION.md).
