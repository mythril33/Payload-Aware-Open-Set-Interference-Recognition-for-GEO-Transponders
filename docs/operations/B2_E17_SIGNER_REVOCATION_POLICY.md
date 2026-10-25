# B2 E17 — signer and revocation trust policy

Version 1, 2026-10-25. **DR-04 NO-GO — NO COMPUTE AUTHORIZED.**
This document configures no real key, principal, issuer, endpoint or approval.

## Independently anchored trust

The real researcher identity remains the identity ratified by the scientific
protocol. A production trust policy must be reviewed independently, identify
that principal's allowed public key and permitted purposes, and have its exact
digest pinned outside the untrusted approval record. An approval author's own
key, claimed Verified status or matching self-supplied digest cannot establish
this association. The repository has no authenticated real signer provisioning
or revocation service; the default remains blocked.

The narrow signature implementation verifies OpenSSH Ed25519 detached SSHSIG
with structured process arguments and no shell interpolation. Public verification
scratch data is temporary; product code neither creates private keys nor signs.
Unknown signer, key, purpose, malformed signature, modified bytes, wrong policy
pin or unavailable verification tool must fail closed. Temporary fabricated keys
in tests never become real allowed signers or researcher decisions.

Purpose separation is mandatory:

| Namespace | Signed material | Independent trust obligation |
|---|---|---|
| `b2-dr04` | Exact committed authorization record bytes, including design and reviewed-code identity | Researcher key bound by reviewed signer policy |
| `b2-revocation` | Explicit grant-status response and all source/request/freshness bindings | Designated revocation issuer key and policy |
| `b2-ci` | Reviewed CI evidence snapshot, exact repository/head/workflows and response validity | CI attestation issuer distinct from an approval author's unsupported assertion |

Canonical JSON rejects duplicate keys, malformed encodings, unsupported types
and nonfinite values. Signature verification must cover the exact bytes ultimately
parsed and compared, not a separately supplied summary or a normalized substitute
whose unsigned differences are ignored. A signed document still needs every E13
and E16 scope, gate, expiry, ceiling and provenance check.

The policy schema is `B2-E17-allowed-signers/1`: `schema` plus a bounded `signers`
list, each with exact `principal`, Ed25519 `public_key` and allowed `namespaces`.
The canonical policy digest is pinned independently. The E17 SSH operational
reference's `evidence_sha256` names that policy digest, not the detached signature
bytes. Exact committed record bytes are signed after the policy reference exists;
the detached signature is separate evidence. No signature/record self-hash cycle
is introduced and no record field is excluded from the signature.

The current public admission root is absent (`PINNED_TRUST_ROOT=None`). A future
reviewed root also pins the repository, required workflow paths and independent
revocation/CI principals. The configured-root test harness requires distinct
researcher, revocation and CI principals and distinct public keys; one key cannot
claim all three roles. These are cryptographic-role separations, not proof that
three independently administered organizations exist.

## Revocation evidence

The reader requires explicit independently authenticated status for the requested
grant. Absence of an entry is not an active grant. An unavailable source, missing
issuer policy, missing signature, malformed or stale response, or ambiguous clock
must remain blocked/denied.

Each accepted response must bind the grant/revocation identifier, authorization
record digest, approved design digest and approval/source identity. The response
must carry its issue/expiry times and satisfy the configured maximum age and
clock-skew rule. It must match the current request challenge and the externally
retained replay floor/anchor. A valid old response cannot be silently reused for
a new request, a different code head or a different grant.

Current signed snapshot schemas are `B2-E17-revocation-status/1` and
`B2-E17-ci-snapshot/1`. Validity is bounded to at most 300 seconds, the issue-time
clock-skew allowance is 5 seconds and expiry is exclusive. Sequence numbers must
meet the externally supplied monotonic floor and the signed challenge must match
the current 64-hex request challenge. Reusing the same floor/challenge is not
prevented by a stateless reader: one-use challenge custody and floor advancement
must be supplied outside it. Every report states `replay_state_updated=false`.

The adapter is a read-only consumer, not an authority. It creates no real grant
or revocation entry and does not advance a durable replay store on behalf of the
operator. A future integration must manage one-use challenges and monotonic replay
state in an independently controlled persistent service or ledger, re-check at
every stage boundary, and stop on expiry, revocation or loss of contact. Merely
storing a response in the working dataset volume is insufficient.

## Configuration and current state

| Requirement | Current state | Who must establish it |
|---|---|---|
| Real researcher public key / identity binding | MISSING — trust root not configured | Researcher and independent security reviewer |
| Independently reviewed allowed-signer policy digest | MISSING | Operator-controlled reviewed configuration |
| Real revocation issuer and authenticated source | MISSING / BLOCKED | Independent authority/operator |
| Trusted current time / permitted skew | External dependency | Designated host/operator policy |
| Request challenge custody and durable replay anchor | External dependency | Reviewed future runtime and external ledger/service |
| Genuine signed DR-04 record | NOT AUTHORIZED / absent | Researcher only |
| Host, backup and run ceilings | Not qualified / not approved | Researcher and host/storage operator |

No private material should be placed in a plan, test artifact, log or Git. Any
future public-key provisioning is a separately reviewed operation; this policy
does not invite generation or copying of real signing keys. A model-agent review
is not human release approval, signature identity proof or compute authorization.

See [trusted evidence contract](../plan/B2_E17_TRUSTED_RELEASE_EVIDENCE.md) and
[CI authority matrix](B2_E17_CI_AUTHORITY_MATRIX.md).
