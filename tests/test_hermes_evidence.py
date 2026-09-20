import json
import os
import subprocess
import unittest
from unittest.mock import patch

from scripts.eval_runtime_helpers import collect_hermes_session_evidence


class HermesEvidenceTest(unittest.TestCase):
    session_id = '20260920_121526_490f3a'

    def export(self, session_id=None):
        return json.dumps({'id': session_id or self.session_id, 'messages': [
            {'role': 'user', 'content': 'Do the task'},
            {'role': 'assistant', 'content': 'Done'},
            {'role': 'assistant', 'tool_calls': [{'id': 'call-1', 'type': 'function',
                'function': {'name': 'terminal', 'arguments': json.dumps({
                    'command': 'printf NEXT_AGORA_APP_CERTIFICATE=test-secret > app/.env.local'})}}]},
            {'role': 'tool', 'tool_call_id': 'call-1', 'content': '{"exit_code":0}'},
        ]})

    def test_exports_exact_session_and_keeps_redacted_call_result_pairs(self):
        with patch('scripts.eval_runtime_helpers.subprocess.run') as run, patch.dict(
            os.environ, {'AGORA_APP_CERTIFICATE': 'test-secret'}
        ):
            run.return_value = subprocess.CompletedProcess([], 0, self.export(), '')
            evidence = collect_hermes_session_evidence('session_id: ' + self.session_id)
        self.assertEqual(evidence['status'], 'available')
        self.assertEqual(len(evidence['tool_messages']), 2)
        self.assertEqual(run.call_args.args[0], ['hermes', 'sessions', 'export', '-',
            '--session-id', self.session_id, '--format', 'jsonl', '--redact'])
        self.assertNotIn('test-secret', json.dumps(evidence))
        self.assertIn('app/.env.local', json.dumps(evidence))
        self.assertEqual(evidence['tool_messages'][1]['tool_call_id'], 'call-1')

    def test_missing_or_ambiguous_session_never_exports_latest_session(self):
        for stderr in ['', 'session_id: one\nsession_id: two']:
            with self.subTest(stderr=stderr), patch('scripts.eval_runtime_helpers.subprocess.run') as run:
                self.assertEqual(collect_hermes_session_evidence(stderr)['status'], 'unavailable')
                run.assert_not_called()

    def test_wrong_session_invalid_export_and_missing_tool_results_are_unavailable(self):
        cases = [self.export('another-session'), 'invalid', '{}',
                 json.dumps({'id': self.session_id, 'messages': [{'role':'assistant','content':'I cloned it'}]}),
                 json.dumps({'id': self.session_id, 'messages': [{'role':'assistant','tool_calls':[
                     {'id':'pending','function':{'name':'terminal','arguments':'{}'}}]}]})]
        for output in cases:
            with self.subTest(output=output), patch('scripts.eval_runtime_helpers.subprocess.run') as run:
                run.return_value = subprocess.CompletedProcess([], 0, output, '')
                self.assertEqual(collect_hermes_session_evidence('session_id: '+self.session_id)['status'], 'unavailable')

    def test_export_failure_and_timeout_do_not_disclose_raw_output(self):
        for error in [subprocess.TimeoutExpired('hermes', 30), OSError('sensitive detail')]:
            with patch('scripts.eval_runtime_helpers.subprocess.run', side_effect=error):
                evidence = collect_hermes_session_evidence('session_id: '+self.session_id)
                self.assertEqual(evidence['status'], 'unavailable')
                self.assertNotIn('sensitive detail', json.dumps(evidence))
        with patch('scripts.eval_runtime_helpers.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 1, 'secret', 'secret')
            evidence = collect_hermes_session_evidence('session_id: '+self.session_id)
            self.assertEqual(evidence['status'], 'unavailable')
            self.assertNotIn('secret', json.dumps(evidence))
