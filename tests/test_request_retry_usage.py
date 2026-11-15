import json
from pathlib import Path
import tempfile
import unittest
from scripts.report_request_retries import request_retry_usage


class RetryUsageTests(unittest.TestCase):
    def test_only_extra_failed_requests_are_added_and_missing_usage_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            events=[{'kind':'request_started'},
                {'kind':'request_failed','reason':'gateway_http_502'},
                {'kind':'request_started'},
                {'kind':'request_failed','reason':'model_response_failed','reported_usage':
                    {'input_tokens':7,'output_tokens':3,'output_tokens_details':{'reasoning_tokens':2}}},
                {'kind':'request_started'},
                {'kind':'request_completed','reported_usage':{'input_tokens':100,'output_tokens':50}}]
            (path/'transport-attempts.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events),encoding='utf-8')
            result=request_retry_usage(path)
        self.assertEqual(result['failed_physical_requests'],2)
        self.assertEqual(result['failed_requests_without_reported_usage'],1)
        self.assertEqual(result['reported_failed_request_tokens'],{'input_tokens':7,'output_tokens':3,'reasoning_tokens':2})

    def test_legacy_sessions_have_no_extra_request_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(request_retry_usage(directory)['failed_physical_requests'],0)
