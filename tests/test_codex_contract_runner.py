"""Exercise the direct runner with recorded task events, without model calls."""
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
    def run_case(self, *, credentials=False, task_exit=0, trace=None, answer='Use the Web reference.', verifier_response=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / 'workspace'
            workspace.mkdir()
            run_dir = root / 'run'
            (run_dir / 'case-results').mkdir(parents=True)
            case_path = root / 'case.yaml'
            case_path.write_text('setup:\n  env_vars_required: ' + ('[AGORA_APP_ID, AGORA_APP_CERTIFICATE]' if credentials else '[]') + '\nassert:\n  required: []\n')
            cases = [{'case_id': 'contract-test', 'path': str(case_path), 'user_prompt': 'Explain only.'}]
            if trace is None:
                trace = '\n'.join([json.dumps({'type': 'item.completed', 'item': {
                    'type': 'command_execution', 'command': 'cat .agents/skills/agora/references/rtc/web.md',
                    'status': 'completed', 'exit_code': 0, 'aggregated_output': 'AGORA_APP_CERTIFICATE=dummy-cert'}}),
                    json.dumps({'type': 'turn.completed'})])
            real_read = Path.read_text
            prompts, environments = [], []

            def read(path, *args, **kwargs):
                if str(path) == '/tmp/codex-eval-cases.json':
                    return json.dumps(cases)
                return real_read(path, *args, **kwargs)

            def command(args, **kwargs):
                if args[0] == 'find':
                    return subprocess.CompletedProcess(args, 0, '', '')
                self.assertEqual(args[0], 'codex')
                prompts.append(kwargs['input'])
                environments.append(kwargs['env'])
                output = Path(args[args.index('--output-last-message') + 1])
                if len(prompts) == 1:
                    output.write_text(answer)
                    return subprocess.CompletedProcess(args, task_exit, trace, '')
                saved_trace = run_dir / 'case-artifacts/contract-test/task-agent-raw.jsonl'
                self.assertIn(str(saved_trace), kwargs['input'])
                if trace:
                    self.assertIn('cat .agents/skills/agora/references/rtc/web.md', saved_trace.read_text())
                self.assertNotIn('dummy-cert', saved_trace.read_text())
                output.write_text(verifier_response if verifier_response is not None else json.dumps({'status': 'pass', 'assertions': [], 'notes': []}))
                return subprocess.CompletedProcess(args, 0, '', '')

            with patch.dict(os.environ, {'RUN_DIR': str(run_dir), 'AGORA_APP_ID': 'dummy-id', 'AGORA_APP_CERTIFICATE': 'dummy-cert'}), \
                 patch.dict('sys.modules', {'eval_runtime_helpers': helpers}), \
                 patch.object(Path, 'read_text', read), \
                 patch.object(helpers, 'create_case_workspace', return_value=(str(workspace), True)), \
                 patch.object(helpers, 'seed_agora_credentials', return_value=workspace / '.agora-ci-credentials.env') as seed, \
                 patch.object(helpers, 'snapshot_quickstart_env_files', return_value={}), \
                 patch.object(helpers, 'start_nextjs_verification_server', return_value=(None, {})) as server, \
                 patch.object(helpers, 'collect_web_runtime_diagnostics', return_value=({}, {})) as diagnostics, \
                 patch.object(subprocess, 'run', side_effect=command):
                runpy.run_path(str(ROOT / 'scripts/run_codex_eval.py'))
            result = json.loads((run_dir / 'case-results/contract-test.json').read_text())
            return result, prompts, environments, seed.call_count, server.call_count, diagnostics.call_count

    def test_recorded_passed_judgment_is_canonicalized(self):
        response = (ROOT / 'tests/fixtures/rtc-quickstart-verifier-passed.json').read_text()
        result, *_ = self.run_case(verifier_response=response)
        self.assertEqual(result['status'], 'pass')
        self.assertIsNone(result['blocked_reason'])
        self.assertTrue(all(a['status'] == 'pass' for a in result['assertions']))
        self.assertEqual(result['assertions'][0]['evidence'], json.loads(response)['assertions'][0]['evidence'])

    def test_failure_alias_and_unknown_status_cannot_become_pass(self):
        for status, assertion, expected, reason in (
            ('failed', 'failed', 'fail', None),
            (' Passed ', 'PASSED', 'pass', None),
            ('success', 'pass', 'blocked', 'evaluator-parse-error'),
            ('pass', 'unknown', 'blocked', 'evaluator-parse-error'),
            ('blocked', 'blocked', 'blocked', 'insufficient-evidence'),
            ('pass', 'failed', 'fail', None),
            ('pass', 'blocked', 'blocked', 'insufficient-evidence'),
        ):
            with self.subTest(status=status, assertion=assertion):
                response = json.dumps({'status': status, 'assertions': [{'status': assertion}], 'notes': []})
                result, *_ = self.run_case(verifier_response=response)
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['blocked_reason'], reason)

    def test_contract_case_has_trace_but_no_credentials_or_web_side_effects(self):
        result, prompts, environments, *calls = self.run_case()
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(calls, [0, 0, 0])
        self.assertNotIn('CI credentials', prompts[0])
        for env in environments:
            self.assertNotIn('AGORA_APP_ID', env)
            self.assertNotIn('AGORA_APP_CERTIFICATE', env)

    def test_credential_case_retains_existing_e2e_setup(self):
        result, prompts, environments, *calls = self.run_case(credentials=True)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(calls, [1, 1, 1])
        self.assertIn('CI credentials', prompts[0])
        self.assertEqual(environments[0]['AGORA_APP_ID'], 'dummy-id')

    def test_verifier_cannot_pass_failed_or_incomplete_task(self):
        for changes in ({'task_exit': 1}, {'trace': ''}, {'trace': json.dumps({'type': 'item.completed', 'item': {'command': 'cat .agents/skills/agora/references/rtc/web.md'}})}, {'answer': ''}):
            with self.subTest(changes=changes):
                result, *_ = self.run_case(**changes)
                self.assertEqual(result['status'], 'blocked')
                self.assertEqual(result['blocked_reason'], 'insufficient-evidence')
                self.assertEqual(result['assertions'], [])


if __name__ == '__main__':
    unittest.main()
