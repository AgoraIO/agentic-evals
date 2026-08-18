import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.eval_runtime_helpers import (
    browser_verification_unavailable,
    classify_evaluator_failure,
    collect_web_runtime_diagnostics,
    downgrade_browser_infrastructure_failure,
    extract_openclaw_command_evidence,
    find_judgment_json,
    redact_sensitive_text,
)


class EvalRuntimeHelpersTest(unittest.TestCase):
    def test_extract_openclaw_command_evidence_requires_completion(self):
        raw = "\n".join([
            '{"params":{"update":{"sessionUpdate":"tool_call","toolCallId":"clone","rawInput":{"command":"git clone https://github.com/AgoraIO-Conversational-AI/agent-quickstart-nextjs.git agent-quickstart-nextjs"}}}}',
            '{"params":{"update":{"sessionUpdate":"tool_call_update","toolCallId":"clone","status":"completed"}}}',
            '{"params":{"update":{"sessionUpdate":"tool_call","toolCallId":"pending","rawInput":{"command":"pnpm dev"}}}}',
        ])

        self.assertEqual(
            extract_openclaw_command_evidence(raw),
            ["git clone https://github.com/AgoraIO-Conversational-AI/agent-quickstart-nextjs.git agent-quickstart-nextjs"],
        )

    def test_browser_infrastructure_failure_blocks_only_browser_assertion(self):
        judgment = {
            "status": "fail",
            "assertions": [
                {"summary": "The demo page loads successfully in a browser.", "status": "fail", "evidence": []},
                {"summary": "Credentials are configured.", "status": "pass", "evidence": []},
            ],
            "notes": [],
        }
        diagnostics = "agent-browser: Failed to connect: daemon may be busy or unresponsive"

        updated, changed = downgrade_browser_infrastructure_failure(judgment, diagnostics)

        self.assertTrue(browser_verification_unavailable(diagnostics))
        self.assertTrue(changed)
        self.assertEqual(updated["status"], "blocked")
        self.assertEqual(updated["assertions"][0]["status"], "blocked")
    def test_find_judgment_json_skips_unrelated_objects(self):
        output = (
            "checked {\"status\": \"running\"}\n"
            "prefix {\"status\": \"running\"}\n"
            "```json\n{\"case_id\": \"case\", \"status\": \"pass\", \"assertions\": []}\n```"
        )

        judgment = find_judgment_json(output)

        self.assertEqual(judgment["status"], "pass")

    def test_classify_evaluator_failure_distinguishes_execution_empty_and_parse(self):
        self.assertEqual(
            classify_evaluator_failure(1, "endpoint rejected request"),
            ("evaluator-execution-error", "Evaluator exited with code 1."),
        )
        self.assertEqual(
            classify_evaluator_failure(0, ""),
            ("evaluator-empty-output", "Evaluator completed without a final response."),
        )
        self.assertEqual(
            classify_evaluator_failure(0, "not json"),
            (
                "evaluator-parse-error",
                "Evaluator response did not contain a valid judgment JSON object.",
            ),
        )

    def test_find_judgment_json_accepts_a_single_unfenced_object(self):
        judgment = find_judgment_json(
            'prefix {"case_id": "case", "status": "fail", "assertions": []}'
        )

        self.assertEqual(judgment["status"], "fail")

    def test_redact_sensitive_text_removes_credentials_everywhere(self):
        env = {
            "AGORA_APP_ID": "test-app-id",
            "AGORA_APP_CERTIFICATE": "test-app-certificate",
        }
        text = (
            "NEXT_PUBLIC_AGORA_APP_ID=test-app-id\n"
            "NEXT_AGORA_APP_CERTIFICATE=test-app-certificate\n"
            "response included test-app-certificate"
        )

        with patch.dict(os.environ, env, clear=False):
            redacted = redact_sensitive_text(text)

        self.assertNotIn("test-app-id", redacted)
        self.assertNotIn("test-app-certificate", redacted)
        self.assertIn("NEXT_PUBLIC_AGORA_APP_ID=[REDACTED]", redacted)
        self.assertIn("NEXT_AGORA_APP_CERTIFICATE=[REDACTED]", redacted)

    def test_collect_web_runtime_diagnostics_captures_logs_and_probe_results(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app_dir = workspace / "agent-quickstart-nextjs"
            eval_dir = app_dir / ".eval"
            eval_dir.mkdir(parents=True)
            (app_dir / "package.json").write_text(
                '{"name":"convoai-quickstart-web-nextjs"}\n'
            )
            (app_dir / "pnpm-workspace.yaml").write_text(
                "allowBuilds:\n  esbuild: false\n  sharp: true\n"
            )
            (eval_dir / "install.log").write_text(
                "using certificate test-app-certificate\n"
            )
            (eval_dir / "dev-server.log").write_text("Ready on port 3000\n")

            with (
                patch.dict(
                    os.environ,
                    {"AGORA_APP_CERTIFICATE": "test-app-certificate"},
                    clear=False,
                ),
                patch(
                    "scripts.eval_runtime_helpers.probe_http_endpoint",
                    return_value={
                        "url": "http://localhost:3000/",
                        "status": 200,
                        "body_bytes": 512,
                        "error": None,
                    },
                ),
            ):
                diagnostics, logs = collect_web_runtime_diagnostics(workspace)

        self.assertEqual(diagnostics["app_dir"], "agent-quickstart-nextjs")
        self.assertEqual(diagnostics["denied_build_scripts"], ["esbuild"])
        self.assertEqual(diagnostics["probes"][0]["body_bytes"], 512)
        self.assertEqual(len(diagnostics["probes"]), 1)
        self.assertTrue(diagnostics["page_ready"])
        self.assertNotIn("test-app-certificate", logs["install.log"])
        self.assertIn("[REDACTED]", logs["install.log"])

    def test_collect_web_runtime_diagnostics_tolerates_missing_lsof(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app_dir = workspace / "agent-quickstart-nextjs"
            app_dir.mkdir()
            (app_dir / "package.json").write_text(
                '{"name":"convoai-quickstart-web-nextjs"}\n'
            )

            with (
                patch(
                    "scripts.eval_runtime_helpers.probe_http_endpoint",
                    return_value={
                        "url": "http://localhost:3000/",
                        "status": None,
                        "body_bytes": 0,
                        "error": "timed out",
                    },
                ),
                patch(
                    "scripts.eval_runtime_helpers.subprocess.run",
                    side_effect=FileNotFoundError("lsof not found"),
                ),
            ):
                diagnostics, _ = collect_web_runtime_diagnostics(workspace)

        self.assertFalse(diagnostics["page_ready"])
        self.assertEqual(diagnostics["port_3000_listener"], "")
        self.assertIn("FileNotFoundError", diagnostics["listener_error"])


if __name__ == "__main__":
    unittest.main()
