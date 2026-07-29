import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "tools" / "power_help.py"


class PowerHelpTests(unittest.TestCase):
    def test_json_contract_is_read_only_and_complete(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--json"], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        self.assertEqual(data["id"], "gwc")
        for key in ("what", "when", "how", "why", "gives", "doesNot", "offline", "exitCodes"):
            self.assertIn(key, data)

    def test_help_does_not_need_a_project(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, check=True)
        self.assertIn("read-only GWC", result.stdout)


if __name__ == "__main__":
    unittest.main()
