"""Read-only E17 Ed25519 SSHSIG verification with an external allowed-signer pin.

No signing API, private key, network lookup, repository write or authorization
transition exists here. ``policy_sha256`` must come from an independently reviewed
trust context, NEVER from the authorization document being verified. Supplying a
policy and its hash from the same untrusted author is not a trust bootstrap.
There is deliberately no configured real policy: omitted trust stays BLOCKED.

OpenSSH's cryptographic verifier exit status is used, not a ``Verified`` string.
Only temporary PUBLIC policy/signature files are created; payload bytes go through
stdin unchanged. The fixed system binary/OS belongs to the future host/tool lock;
its observed digest is reported, not mistaken for independently authenticated OS.
Namespace separation prevents replay between DR-04, revocation and CI evidence.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import struct
import subprocess
import tempfile

SCHEMA = "B2-E17-allowed-signers/1"
REPORT_SCHEMA = "B2-E17-signature-verification/1"
NAMESPACES = frozenset({"b2-dr04", "b2-revocation", "b2-ci"})
VERIFIER = "/usr/bin/ssh-keygen"
MAX_PAYLOAD_BYTES = 4 * 1024 * 1024
MAX_SIGNATURE_BYTES = 16384
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PRINCIPAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,79}\Z")


class SignatureError(ValueError):
    """Malformed metadata or evidence; cannot establish cryptographic trust."""


def _plain(value):
    stack, count = [(value, 0)], 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > 100000 or depth > 40:
            raise SignatureError("metadata exceeds node/depth bound")
        if type(item) in (str, bool, int) or item is None:
            continue
        if type(item) is float:
            if not math.isfinite(item):
                raise SignatureError("nonfinite JSON")
        elif type(item) is dict:
            if len(item) > 100000 or any(type(key) is not str for key in item):
                raise SignatureError("JSON keys must be strings")
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            if len(item) > 100000:
                raise SignatureError("metadata exceeds node bound")
            stack.extend((child, depth + 1) for child in item)
        else:
            raise SignatureError("non-JSON metadata type")


def canonical(value):
    """Plain, bounded, finite JSON with deterministic key ordering; returns str."""
    _plain(value)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise SignatureError("JSON exceeds four MiB")
    return raw


def strict_json(raw):
    """Read one JSON object; duplicates, nonfinite/overflow values are refused."""
    if not isinstance(raw, (bytes, str)):
        raise SignatureError("JSON bytes or text required")
    if len(raw.encode("utf-8") if isinstance(raw, str) else raw) > MAX_PAYLOAD_BYTES:
        raise SignatureError("JSON exceeds four MiB")
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise SignatureError("duplicate JSON key")
            result[key] = item
        return result
    def nonfinite(_):
        raise SignatureError("nonfinite JSON")
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            nonfinite(value)
        return result
    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite, parse_float=number)
        if type(result) is not dict:
            raise SignatureError("JSON object required")
        canonical(result)
        return result
    except (ValueError, UnicodeError, RecursionError, TypeError) as error:
        raise SignatureError("invalid strict JSON") from error


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _public_key(value):
    """Accept exactly one plain Ed25519 key, no options, comments or algorithms."""
    if type(value) is not str or len(value) > 256:
        raise SignatureError("plain Ed25519 public key required")
    words = value.split(" ")
    if len(words) != 2 or words[0] != "ssh-ed25519":
        raise SignatureError("plain Ed25519 public key required")
    try:
        key = base64.b64decode(words[1], validate=True)
    except (ValueError, TypeError) as error:
        raise SignatureError("invalid public key base64") from error
    expected = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32)
    if len(key) != len(expected) + 32 or not key.startswith(expected) or base64.b64encode(key).decode() != words[1]:
        raise SignatureError("invalid Ed25519 wire encoding")
    return value


def _policy(policy, expected):
    copied = strict_json(canonical(policy))
    if set(copied) != {"schema", "signers"} or copied["schema"] != SCHEMA:
        raise SignatureError("unknown signer-policy fields/schema")
    if type(expected) is not str or not HEX64.fullmatch(expected) or _hash(canonical(copied).encode()) != expected:
        raise SignatureError("independent signer-policy pin mismatch")
    if type(copied["signers"]) is not list or len(copied["signers"]) > 16:
        raise SignatureError("bounded signer list required")
    principals, keys = set(), set()
    for signer in copied["signers"]:
        if type(signer) is not dict or set(signer) != {"principal", "public_key", "namespaces"}:
            raise SignatureError("unknown signer fields")
        identity, namespaces = signer["principal"], signer["namespaces"]
        if type(identity) is not str or not PRINCIPAL.fullmatch(identity) or identity in principals:
            raise SignatureError("exact unique signer principal required")
        key = _public_key(signer["public_key"])
        if key in keys:
            raise SignatureError("one key cannot impersonate several principals")
        if (type(namespaces) is not list or not namespaces or any(type(n) is not str or n not in NAMESPACES for n in namespaces)
                or len(set(namespaces)) != len(namespaces)):
            raise SignatureError("explicit unique purpose namespaces required")
        principals.add(identity)
        keys.add(key)
    return copied


def verify_signature(payload: bytes, signature: bytes, *, policy=None, policy_sha256=None,
                     principal: str, namespace: str):
    """Verify exact payload bytes against a separately pinned allowed-signer policy.

    A verified signature authenticates bytes under that trust context only. Caller
    must bind/validate the canonical record, design digest, reviewed Git identity,
    freshness, revocation and scope; this function cannot create those facts.
    ``None`` is the production default until a real independently reviewed root is
    configured. Tests alone supply fabricated, temporary-key trust roots.
    """
    report = {"schema": REPORT_SCHEMA, "ok": False, "status": "DENIED",
              "payload_sha256": _hash(payload) if type(payload) is bytes and len(payload) <= MAX_PAYLOAD_BYTES else None,
              "policy_sha256": policy_sha256 if type(policy_sha256) is str and HEX64.fullmatch(policy_sha256) else None,
              "verified_principal": None, "namespace": namespace if type(namespace) is str and namespace in NAMESPACES else None,
              "verifier_sha256": None, "execution_permitted": False, "authorizes_nothing": True}
    if policy is None or policy_sha256 is None:
        report["status"] = "BLOCKED_TRUST_ROOT_MISSING"
        return report
    try:
        allowed = _policy(policy, policy_sha256)
        if not allowed["signers"]:
            report["status"] = "BLOCKED_TRUST_ROOT_MISSING"
            return report
        if (type(payload) is not bytes or not 0 < len(payload) <= MAX_PAYLOAD_BYTES
                or type(signature) is not bytes or not 0 < len(signature) <= MAX_SIGNATURE_BYTES):
            raise SignatureError("bounded payload/signature bytes required")
        if type(principal) is not str or not PRINCIPAL.fullmatch(principal) or namespace not in NAMESPACES:
            raise SignatureError("invalid principal or purpose namespace")
        signer = next((s for s in allowed["signers"] if s["principal"] == principal and namespace in s["namespaces"]), None)
        if signer is None:
            raise SignatureError("signer is not allowed for this purpose")
        tool = Path(VERIFIER)
        info = tool.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022:
            raise SignatureError("fixed cryptographic verifier must be a non-writable regular system file")
        report["verifier_sha256"] = _hash(tool.read_bytes())
        # Do not let an untrusted TMPDIR redirect public scratch writes into a
        # source checkout. This POSIX adapter uses the separate /tmp workspace.
        with tempfile.TemporaryDirectory(prefix="b2-e17-public-verification-", dir="/tmp") as directory:
            root = Path(directory)
            key_file, sig_file = root / "allowed_signers", root / "detached.sig"
            key_file.write_text(f'{principal} namespaces="{namespace}" {signer["public_key"]}\n', encoding="ascii")
            sig_file.write_bytes(signature)
            # No shell, agent, HOME lookup, user configuration, signing operation,
            # generator callback or network facility. Only a PUBLIC verifier.
            result = subprocess.run([VERIFIER, "-Y", "verify", "-f", str(key_file), "-I", principal,
                                     "-n", namespace, "-s", str(sig_file)], input=payload,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                                    timeout=10, cwd=root, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
        after = tool.lstat()
        stable = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if stable(info) != stable(after) or _hash(tool.read_bytes()) != report["verifier_sha256"]:
            raise SignatureError("cryptographic verifier changed during verification")
        if result.returncode == 0:
            report.update(ok=True, status="SIGNATURE_VERIFIED", verified_principal=principal)
    except (SignatureError, OSError, ValueError, TypeError, RecursionError, subprocess.SubprocessError):
        pass
    canonical(report)
    return report
