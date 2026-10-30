"""Branding guard: the product is "Second Eye"; the old name must not reappear in user-facing files.

    python3 -m unittest engine.test_branding
"""
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD = "Second " + "Look"
PATHS = ["mobile/src", "mobile/public", "mobile/index.html", "engine", "backend/app", "README.md", "docs"]
SKIP = {"docs/TESTING.md", "engine/test_branding.py"}


class Branding(unittest.TestCase):
    def test_no_old_name(self):
        out = subprocess.run(["git", "grep", "-nI", "-i", OLD, "--"] + PATHS, cwd=ROOT,
                             capture_output=True, text=True).stdout
        hits = [l for l in out.splitlines() if l.split(":", 1)[0] not in SKIP]
        self.assertEqual(hits, [], "old product name found:\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
