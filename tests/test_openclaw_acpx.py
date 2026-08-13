import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.openclaw_acpx import AcpxClient, AcpxCommandError


class AcpxClientTest(unittest.TestCase):
    def test_all_commands_use_the_workspace_cwd(self):
        workspace = Path("/tmp/openclaw-attempt")
        completed = subprocess.CompletedProcess([], 0, stdout="response", stderr="")

        with patch("scripts.openclaw_acpx.subprocess.run", return_value=completed) as run:
            client = AcpxClient(workspace)
            client.new_session()
            client.ensure_session()
            client.set_elevated()
            output, returncode = client.prompt("build the demo")

        self.assertEqual(output, "response")
        self.assertEqual(returncode, 0)
        self.assertEqual(run.call_count, 4)
        for call in run.call_args_list:
            self.assertEqual(call.kwargs["cwd"], workspace)

    def test_setup_failure_includes_stderr(self):
        completed = subprocess.CompletedProcess(
            [], 4, stdout="", stderr="No acpx session found"
        )

        with patch("scripts.openclaw_acpx.subprocess.run", return_value=completed):
            client = AcpxClient(Path("/tmp/openclaw-attempt"))
            with self.assertRaisesRegex(
                AcpxCommandError, "No acpx session found"
            ):
                client.ensure_session()


if __name__ == "__main__":
    unittest.main()
