"""Verified per-route context settings; copied with the worker into its jail."""
from hashlib import sha256
import json
from pathlib import Path


def context_configuration(model, registry=None):
    registry = Path(registry) if registry is not None else Path(__file__).with_name('model-gateways.json')
    if not registry.is_file():
        registry = Path(__file__).resolve().parents[1] / 'config/model-gateways.json'
    body = registry.read_bytes()
    policy = json.loads(body)
    if policy.get('schema') != 'benchmark-model-gateways-1':
        raise ValueError('Unsupported model gateway policy')
    record = policy['models'].get(model)
    if record is None:
        raise ValueError('Model has no verified context configuration: ' + str(model))
    window = record['hermes_context_tokens']
    if type(window) is not int or window <= 0 or window > record['route_max_input_tokens']:
        raise ValueError('Context exceeds the verified route allowance')
    gateway = policy['gateways'][record['gateway']]
    return {'model_context_length': window, 'model': model,
            'gateway': record['gateway'], 'api_mode': gateway['api_mode'],
            'registry_sha256': sha256(body).hexdigest(),
            'verified_at_utc': policy['verified_at_utc'],
            'route_max_input_tokens': record['route_max_input_tokens']}
