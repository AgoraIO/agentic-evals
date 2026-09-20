import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ReportTest(unittest.TestCase):
    def test_report_accepts_both_assertion_schemas_without_losing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "case-results").mkdir()
            (run / "case-results" / "case.json").write_text(json.dumps({
                "case_id": "case", "status": "fail", "assertions": [
                    {"status": "fail", "description": "Credentials configured", "notes": "Write not established"},
                    {"status": "pass", "summary": "Official clone", "evidence": ["Clone observed"]},
                ],
            }))
            subprocess.run([sys.executable, "scripts/generate_report.py"],
                           env={**os.environ, "RUN_DIR": directory}, check=True, capture_output=True)
            report = (run / "report.md").read_text()
            self.assertIn("[fail] Credentials configured", report)
            self.assertIn("Write not established", report)
            self.assertIn("[pass] Official clone", report)
            self.assertIn("Clone observed", report)
            self.assertIn("0 pass, 1 fail, 0 blocked", report)
