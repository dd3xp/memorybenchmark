"""Executed bytes stay authoritative when auditing newline-only packaging drift."""

from hashlib import sha256
import unittest

from memorybenchmark.support_integrity import verify_executed_support


class SupportIntegrityTests(unittest.TestCase):
    def test_newline_equivalence_is_explicit_and_keeps_both_hashes(self):
        frozen, executed = b"value = 1\n", b"value = 1\r\n"
        digest = sha256(executed).hexdigest()
        with self.assertRaisesRegex(AssertionError, "differs from frozen"):
            verify_executed_support(frozen, executed, [digest])
        result = verify_executed_support(
            frozen, executed, [digest, digest], newline_policy="crlf-equivalent"
        )
        self.assertEqual(result["executed_sha256"], digest)
        self.assertEqual(result["frozen_sha256"], sha256(frozen).hexdigest())
        self.assertEqual(result["session_receipts_verified"], 2)
        self.assertNotEqual(result["executed_sha256"], result["frozen_sha256"])

    def test_missing_or_conflicting_session_receipts_cannot_approve_a_difference(self):
        frozen, executed = b"value = 1\n", b"value = 1\r\n"
        digest = sha256(executed).hexdigest()
        for receipts in ([], [digest, None], [digest, "wrong"]):
            with self.subTest(receipts=receipts), self.assertRaises(AssertionError):
                verify_executed_support(
                    frozen, executed, receipts, newline_policy="crlf-equivalent"
                )

    def test_semantic_whitespace_and_bom_changes_still_fail(self):
        for executed in (
            b"value = 2\r\n",
            b"value  = 1\r\n",
            b"\xef\xbb\xbfvalue = 1\r\n",
        ):
            with self.subTest(executed=executed), self.assertRaisesRegex(
                AssertionError, "beyond CRLF/LF"
            ):
                verify_executed_support(
                    b"value = 1\n",
                    executed,
                    [sha256(executed).hexdigest()],
                    newline_policy="crlf-equivalent",
                )

    def test_exact_bytes_also_reject_a_conflicting_execution_receipt(self):
        with self.assertRaisesRegex(AssertionError, "session receipt"):
            verify_executed_support(b"value = 1\n", b"value = 1\n", ["wrong"])
