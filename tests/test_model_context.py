import json
from pathlib import Path
import tempfile
import unittest

from memorybenchmark.model_context import context_configuration


class ContextPolicyTests(unittest.TestCase):
    def test_four_verified_models_and_route_bounds(self):
        for model, window in [('gpt-5.6-luna',272000),('gpt-5.6-terra',272000),
                              ('gemini-3.5-flash-lite',250000),('gemini-3.1-flash-lite',250000)]:
            with self.subTest(model=model):
                selected=context_configuration(model)
                self.assertEqual(selected['model_context_length'],window)
                self.assertEqual(len(selected['registry_sha256']),64)

    def test_unknown_model_cannot_silently_use_small_window(self):
        with self.assertRaisesRegex(ValueError,'no verified context'):
            context_configuration('unverified-model')

    def test_invalid_route_allowance_refuses_start(self):
        policy=json.loads(Path('config/model-gateways.json').read_text())
        policy['models']['gpt-5.6-luna']['hermes_context_tokens']=1050000
        with tempfile.TemporaryDirectory() as folder:
            registry=Path(folder)/'registry.json';registry.write_text(json.dumps(policy))
            with self.assertRaisesRegex(ValueError,'verified route allowance'):
                context_configuration('gpt-5.6-luna',registry)

    def test_worker_and_receipt_use_same_resolved_value(self):
        worker=Path('memorybenchmark/hermes_worker.py').read_text(encoding='utf-8')
        self.assertNotIn('64000',worker)
        self.assertIn('native_context_configuration=context_config',worker)
        self.assertIn('"context_length": context_config[\'model_context_length\']',worker)
