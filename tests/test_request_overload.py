"""Overload aliases must retry the same bytes without accepting invalid requests."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from memorybenchmark.agent_sessions import InfrastructureError
from memorybenchmark.request_recovery import RecoveringGatewayModel,RequestFailure


class Response:
    status=200
    def __init__(self,event):self.line=('data: '+json.dumps(event)+'\n').encode()
    def getheaders(self):return []
    def getheader(self,name,default=''):return default
    def readline(self,limit):return self.line


class RequestOverloadTests(unittest.TestCase):
    def test_exact_observed_sse_overload_retries_identical_request(self):
        with tempfile.TemporaryDirectory() as directory:
            model=RecoveringGatewayModel('https://example.test','fixture','gpt-5.6-luna',None,
                sleep=lambda _:None,jitter=lambda a,b:0)
            model.output=Path(directory)
            payload={'input':[{'role':'user','content':'unchanged memory'}], 'reasoning':{'effort':'high'}}
            overloaded={'type':'error','error':{'type':'service_unavailable_error',
                'code':'server_is_overloaded','headers':{'retry-after':'6','retry-after-ms':'6000'},
                'message':'Our servers are currently overloaded. Please try again later.','param':None}}
            complete={'type':'response.completed','response':{'usage':{'input_tokens':7,'output_tokens':3}}}
            with patch('memorybenchmark.request_recovery._RoutedHTTPS') as connection:
                connection.return_value.getresponse.side_effect=[Response(overloaded),Response(complete)]
                result=model(payload)
            bodies=[c.kwargs['body'] for c in connection.return_value.request.call_args_list]
            self.assertEqual(bodies,[model._body(payload)]*2)
            self.assertIsNotNone(result['lines'])
            events=[json.loads(s) for s in (model.output/'transport-attempts.jsonl').read_text().splitlines()]
            failed=next(x for x in events if x['kind']=='request_failed')
            self.assertTrue(failed['retryable'])
            self.assertIsNone(failed['reported_usage'])
            self.assertEqual([x['kind'] for x in events],['request_started','request_failed','network_retry','request_started','request_completed'])
            self.assertEqual(len({x['request_sha256'] for x in events}),1)

    def test_invalid_and_unknown_sse_errors_still_require_attention(self):
        for code in ('context_length_exceeded','max_output_tokens','invalid_api_key','invalid_request_error','unknown_error',''):
            with self.subTest(code=code):
                with tempfile.TemporaryDirectory() as directory:
                    model=RecoveringGatewayModel('https://example.test','fixture','fixture',None)
                    model.output=Path(directory)
                    event={'type':'error','error':{'code':code}}
                    with patch('memorybenchmark.request_recovery._RoutedHTTPS') as connection:
                        connection.return_value.getresponse.return_value=Response(event)
                        with self.assertRaises(RequestFailure) as caught:model._attempt(b'fixed bytes')
                    self.assertFalse(caught.exception.retryable)

    def test_exhausted_worker_cannot_retry_even_known_overload(self):
        model=RecoveringGatewayModel('https://example.test','fixture','fixture',None)
        model.alive=lambda:False
        with patch('memorybenchmark.request_recovery._RoutedHTTPS') as connection:
            with self.assertRaisesRegex(InfrastructureError,'native_worker_died'):
                model({'input':[]})
        connection.assert_not_called()


if __name__=='__main__':unittest.main()
