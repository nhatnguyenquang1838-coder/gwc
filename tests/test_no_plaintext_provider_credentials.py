import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTINUE_CONFIG_ROOT = REPO_ROOT / ".continue"
CREDENTIAL_LINE = re.compile(
    r"^\s*(apiKey|api_key|accessToken|access_token|token|secret)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
SECRET_REFERENCE = re.compile(r"^\$\{\{\s*secrets\.[A-Z][A-Z0-9_]*\s*\}\}$")


class NoPlaintextProviderCredentialsTest(unittest.TestCase):
    def test_continue_credentials_use_secret_references(self):
        config_files = sorted(CONTINUE_CONFIG_ROOT.rglob("*.yaml"))
        config_files.extend(sorted(CONTINUE_CONFIG_ROOT.rglob("*.yml")))
        self.assertTrue(config_files, "expected at least one Continue YAML configuration")

        findings: list[str] = []
        for path in config_files:
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                match = CREDENTIAL_LINE.match(line)
                if not match:
                    continue
                value = match.group(2).split(" #", 1)[0].strip().strip('"').strip("'")
                if not SECRET_REFERENCE.fullmatch(value):
                    findings.append(
                        f"{path.relative_to(REPO_ROOT)}:{line_number}: "
                        f"{match.group(1)} must use a ${{{{ secrets.NAME }}}} reference"
                    )

        self.assertEqual(findings, [], "plaintext provider credential fields found:\n" + "\n".join(findings))

    def test_alibaba_example_has_one_models_mapping(self):
        config = CONTINUE_CONFIG_ROOT / "agents" / "new-config.yaml"
        text = config.read_text(encoding="utf-8")
        top_level_models = [line for line in text.splitlines() if line == "models:"]
        self.assertEqual(len(top_level_models), 1)


if __name__ == "__main__":
    unittest.main()
