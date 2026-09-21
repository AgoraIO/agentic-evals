"""Exercise the original runner flow with recorded task/verifier responses."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import eval_runtime_helpers as helpers

ROOT = Path(__file__).resolve().parents[1]


class CodexContractRunnerTest(unittest.TestCase):
    def run_case(self, *, credentials=False, with_app=False, verifier_response=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / 'workspace'
            workspace.mkdir()
            if with_app:
                (workspace / 'package.json').write_text('{"name":"convoai-quickstart-web-nextjs"}')
            run_dir = root / 'run'
            (run_dir / 'case-results').mkdir(parents=True)
            case_path = root / 'case.yaml'
            case_path.write_text('setup:\n  env_vars_required: ' + ('[AGORA_APP_ID, AGORA_APP_CERTIFICATE]' if credentials else '[]') + '\nassert:\n  required: []\n')
            cases = [{'case_id': 'contract-test', 'path': str(case_path), 'user_prompt': 'Explain only.'}]
            trace = '\n'.join([json.dumps({'type': 'item.completed', 'item': {
                'type': 'command_execution', 'command': 'cat .agents/skills/agora/references/rtc/web.md',
                'status': 'completed', 'exit_code': 0, 'aggregated_output': 'AGORA_APP_CERTIFICATE=dummy-cert'}}),
                json.dumps({'type': 'turn.completed'})])
            real_read = Path.read_text
            prompts = []

            def read(path, *args, **kwargs):
                if str(path) == '/tmp/codex-eval-cases.json':
                    return json.dumps(cases)
                return real_read(path, *args, **kwargs)

            def command(args, **kwargs):
                if args[0] in ('find', 'lsof'):
                    return subprocess.CompletedProcess(args, 0, '', '')
                self.assertEqual(args[0], 'codex')
                self.assertNotIn('env', kwargs)  # Preserve the original inherited environment.
                prompts.append(kwargs['input'])
                output = Path(args[args.index('--output-last-message') + 1])
                if len(prompts) == 1:
                    output.write_text('Use the Web reference.')
                    return subprocess.CompletedProcess(args, 0, trace, '')
                saved_trace = run_dir / 'case-artifacts/contract-test/task-agent-raw.jsonl'
                self.assertIn(str(saved_trace), kwargs['input'])
                self.assertIn('cat .agents/skills/agora/references/rtc/web.md', saved_trace.read_text())
                self.assertNotIn('dummy-cert', saved_trace.read_text())
                output.write_text(verifier_response if verifier_response is not None else json.dumps({'status': 'pass', 'assertions': [], 'notes': []}))
                return subprocess.CompletedProcess(args, 0, '', '')

            with patch.dict(os.environ, {'RUN_DIR': str(run_dir), 'AGORA_APP_ID': 'dummy-id', 'AGORA_APP_CERTIFICATE': 'dummy-cert'}), \
                 patch.dict('sys.modules', {'eval_runtime_helpers': helpers}), \
                 patch.object(Path, 'read_text', read), \
                 patch.object(helpers, 'create_case_workspace', return_value=(str(workspace), True)), \
                 patch.object(helpers, 'probe_http_endpoint', return_value={'status': 200, 'body_bytes': 10, 'error': None}) as probe, \
                 patch.object(subprocess, 'Popen') as start_process, \
                 patch.object(subprocess, 'run', side_effect=command):
                # Use real credential, app-discovery, server and diagnostic helpers.
                runpy.run_path(str(ROOT / 'scripts/run_codex_eval.py'))
                self.assertTrue((workspace / '.agora-ci-credentials.env').exists())
                start_process.assert_not_called()
            result = json.loads((run_dir / 'case-results/contract-test.json').read_text())
            evidence = json.loads((run_dir / 'case-artifacts/contract-test/accepted-session.json').read_text())
            return result, prompts, evidence, probe.call_count

    def test_recorded_passed_judgment_is_canonicalized(self):
        response = (ROOT / 'tests/fixtures/rtc-quickstart-verifier-passed.json').read_text()
        result, *_ = self.run_case(verifier_response=response)
        self.assertEqual(result['status'], 'pass')
        self.assertIsNone(result['blocked_reason'])
        self.assertTrue(all(a['status'] == 'pass' for a in result['assertions']))
        self.assertEqual(result['assertions'][0]['evidence'], json.loads(response)['assertions'][0]['evidence'])

    def test_failure_alias_and_unknown_overall_status(self):
        for status, expected in (('failed', 'fail'), (' Passed ', 'pass'), ('success', 'blocked'), ('blocked', 'blocked')):
            with self.subTest(status=status):
                response = json.dumps({'status': status, 'assertions': [{'status': status}], 'notes': []})
                result, *_ = self.run_case(verifier_response=response)
                self.assertEqual(result['status'], expected)
                if status.strip().lower() in ('passed', 'failed'):
                    self.assertEqual(result['assertions'][0]['status'], expected)

    def test_no_app_continues_to_verifier_without_web_requests_or_startup(self):
        for credentials in (False, True):
            with self.subTest(credentials=credentials):
                result, prompts, evidence, probes = self.run_case(credentials=credentials)
                self.assertEqual(result['status'], 'pass')
                self.assertIn('CI credentials', prompts[0])
                self.assertEqual(len(prompts), 2)
                self.assertEqual(probes, 0)
                self.assertEqual(evidence['verification_server']['reason'], 'quickstart app not found')
                self.assertEqual(evidence['runtime_diagnostics']['error'], 'quickstart app not found')

    def test_existing_convoai_app_keeps_web_diagnostics_independent_of_credentials_field(self):
        for credentials in (False, True):
            with self.subTest(credentials=credentials):
                result, _, evidence, probes = self.run_case(credentials=credentials, with_app=True)
                self.assertEqual(result['status'], 'pass')
                self.assertGreater(probes, 0)
                self.assertEqual(evidence['verification_server']['reason'], 'task server remained available')
                self.assertTrue(evidence['runtime_diagnostics']['page_ready'])


if __name__ == '__main__':
    unittest.main()
