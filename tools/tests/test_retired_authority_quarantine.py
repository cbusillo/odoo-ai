import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class RetiredAuthorityQuarantineTests(unittest.TestCase):
    def test_active_entrypoints_carry_retirement_notice(self) -> None:
        files = (
            "AGENTS.md",
            "docs/README.md",
            "docs/tooling/dokploy.md",
            "docs/tooling/platform-cli.md",
            "docs/tooling/platform-command-patterns.md",
            "platform/ARCHIVE.md",
            "platform/README.md",
            "platform/config/README.md",
        )

        for relative_path in files:
            with self.subTest(relative_path=relative_path):
                text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn("Launchplane", text)
                self.assertIn("odoo-devkit", text)
                self.assertRegex(text.lower(), r"retired|archival|archive")

    def test_archival_platform_snapshots_are_marked(self) -> None:
        for relative_path in ("platform/dokploy.toml", "platform/stack.toml"):
            with self.subTest(relative_path=relative_path):
                first_lines = "\n".join(
                    (REPO_ROOT / relative_path).read_text(encoding="utf-8").splitlines()[:4]
                )
                self.assertIn("ARCHIVAL SNAPSHOT ONLY", first_lines)
                self.assertIn("Launchplane", first_lines)

    def test_real_secrets_file_is_not_tracked(self) -> None:
        self.assertFalse((REPO_ROOT / "platform/secrets.toml").exists())
        self.assertTrue((REPO_ROOT / "platform/secrets.toml.example").exists())

    def test_archived_docs_do_not_claim_current_platform_authority(self) -> None:
        archived_docs = (
            "AGENTS.md",
            "docs/tooling/dokploy.md",
            "docs/tooling/platform-cli.md",
            "platform/README.md",
        )

        disallowed_phrases = (
            "canonical operator contract",
            "source of truth for remote",
            "source of truth for live",
            "current production guidance",
        )
        for relative_path in archived_docs:
            text = (REPO_ROOT / relative_path).read_text(encoding="utf-8").lower()
            for phrase in disallowed_phrases:
                with self.subTest(relative_path=relative_path, phrase=phrase):
                    self.assertNotIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
