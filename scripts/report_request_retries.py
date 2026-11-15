"""Additional physical-request usage; successful logical responses are excluded."""
from collections import Counter
import json
from pathlib import Path


def request_retry_usage(folder):
    tokens=dict.fromkeys(('input_tokens','output_tokens','reasoning_tokens'),0)
    errors=Counter();failures=known=started=0
    path=Path(folder)/'transport-attempts.jsonl'
    if path.is_file():
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                event=json.loads(line)
                started+=event['kind']=='request_started'
                if event['kind']!='request_failed':continue
                failures+=1;errors[event.get('reason','unknown')]+=1
                usage=event.get('reported_usage')
                if not isinstance(usage,dict) or not all(isinstance(usage.get(k),int) for k in ('input_tokens','output_tokens')):
                    continue
                known+=1
                tokens['input_tokens']+=usage['input_tokens']
                tokens['output_tokens']+=usage['output_tokens']
                tokens['reasoning_tokens']+=usage.get('output_tokens_details',{}).get('reasoning_tokens',0)
    return {'observed_physical_starts':started,'failed_physical_requests':failures,
            'failed_requests_with_reported_usage':known,'failed_requests_without_reported_usage':failures-known,
            'reported_failed_request_tokens':tokens,'errors':dict(errors),
            'successful_requests_excluded_to_avoid_double_counting':True}
