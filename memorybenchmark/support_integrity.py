"""Verify executed support bytes without rewriting historical evidence."""

from hashlib import sha256


def verify_executed_support(frozen, executed, receipts, *, newline_policy="raw"):
    """Permit explicit CRLF/LF equivalence only with every session's raw hash."""
    if newline_policy not in ("raw", "crlf-equivalent"):
        raise ValueError("Unknown executed-support newline policy")
    frozen_digest = sha256(frozen).hexdigest()
    executed_digest = sha256(executed).hexdigest()
    observed = [value for value in receipts if value is not None]
    if any(value != executed_digest for value in observed):
        raise AssertionError("Executed support differs from a session receipt")
    comparison = "exact_bytes"
    if frozen_digest != executed_digest:
        if newline_policy != "crlf-equivalent":
            raise AssertionError("executed support differs from frozen source")
        # Python's source reader normalizes CRLF; no whitespace, BOM, or other
        # transformation is accepted. Keep both original byte hashes in output.
        frozen.decode("utf-8")
        executed.decode("utf-8")
        if frozen.replace(b"\r\n", b"\n") != executed.replace(b"\r\n", b"\n"):
            raise AssertionError("executed support differs beyond CRLF/LF")
        if not receipts or len(observed) != len(receipts):
            raise AssertionError("CRLF/LF equivalence requires every session receipt")
        comparison = "crlf_lf_equivalent_with_session_receipts"
    return {
        "frozen_sha256": frozen_digest,
        "executed_sha256": executed_digest,
        "comparison": comparison,
        "session_receipts_verified": len(observed),
    }
