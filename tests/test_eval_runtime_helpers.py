import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.eval_runtime_helpers import (
    collect_web_runtime_diagnostics,
    redact_sensitive_text,
)


class EvalRuntimeHelpersTest(unittest.TestCase):
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
                    side_effect=[
                        {
                            "url": "http://localhost:3000/",
                            "status": 200,
                            "body_bytes": 512,
                            "error": None,
                        },
                        {
                            "url": "http://localhost:3000/api/generate-agora-token",
                            "status": None,
                            "body_bytes": 0,
                            "error": "timed out",
                        },
                    ],
                ),
            ):
                diagnostics, logs = collect_web_runtime_diagnostics(workspace)

        self.assertEqual(diagnostics["app_dir"], "agent-quickstart-nextjs")
        self.assertEqual(diagnostics["denied_build_scripts"], ["esbuild"])
        self.assertEqual(diagnostics["probes"][0]["body_bytes"], 512)
        self.assertEqual(diagnostics["probes"][1]["error"], "timed out")
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
