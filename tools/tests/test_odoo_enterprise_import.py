# SPDX-FileCopyrightText: 2026 NuoBiT Solutions, S.L.
# SPDX-License-Identifier: Apache-2.0

"""Command-line tests of tools/odoo-enterprise-import.

Run from the repository root with the system Python and the git command;
PyYAML is the only Python dependency beyond the standard library:

    python3 -m unittest discover -s tools/tests
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "odoo-enterprise-import"
# Git runs without the user's configuration (no hooks, templates or commit signing)
# and with a fixed identity for the commits of the tests and of --apply.
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def write_module(path: Path, *, manifest_license: str = "LGPL-3") -> None:
    (path / "models").mkdir(parents=True)
    (path / "__manifest__.py").write_text(
        f'{{"name": "{path.name}", "license": "{manifest_license}"}}\n', encoding="utf-8"
    )
    (path / "__init__.py").write_text("from . import models\n", encoding="utf-8")
    (path / "models" / "__init__.py").write_text(f"# {path.name} models\n", encoding="utf-8")


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
        env=GIT_ENV,
    )
    return result.stdout.strip()


def git_commit(path: Path, message: str) -> str:
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", message)
    return git(path, "rev-parse", "HEAD")


def write_lock(path: Path, revision: str) -> None:
    path.write_text(f"./odoo:\n  merges:\n    - odoo {revision}\n", encoding="utf-8")


class EnterpriseImportTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.community = self.tmp / "workspace" / "odoo"
        self.download = self.tmp / "download" / "odoo-18.0+e.20260930"

        # An Odoo Community clone keeps base in odoo/addons and the other modules in addons.
        write_module(self.community / "odoo" / "addons" / "base")
        write_module(self.community / "addons" / "sale")
        git(self.community, "init", "-q", "-b", "main")
        self.community_head = git_commit(self.community, "Community")

        # The source bundle carries the same Community modules plus the Enterprise ones.
        write_module(self.download / "odoo" / "addons" / "base")
        write_module(self.download / "odoo" / "addons" / "sale")
        write_module(self.download / "odoo" / "addons" / "account_accountant", manifest_license="OEEL-1")
        write_module(self.download / "odoo" / "addons" / "web_studio", manifest_license="OEEL-1")

    def run_tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOL), *args],
            check=False,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        )

    def make_bundle(self) -> Path:
        bundle = self.tmp / "odoo_18.0+e.20260930.tar.gz"
        with tarfile.open(bundle, "w:gz") as archive:
            archive.add(self.download, arcname=self.download.name)
        return bundle

    def make_mirror(self) -> Path:
        """Private Enterprise mirror: web_studio outdated, gone_module no longer in the bundle."""
        mirror = self.tmp / "mirror"
        write_module(mirror / "web_studio", manifest_license="OEEL-1")
        (mirror / "web_studio" / "models" / "__init__.py").write_text("# web_studio models, old\n", encoding="utf-8")
        write_module(mirror / "gone_module", manifest_license="OEEL-1")
        (mirror / "README.md").write_text("# Odoo Enterprise Source\n", encoding="utf-8")
        git(mirror, "init", "-q", "-b", "main")
        git_commit(mirror, "Mirror")
        return mirror

    def commit_community_fix_after_the_bundle(self) -> str:
        """Make the bundle's sale copy match the Community commit before a newer fix; return the new HEAD."""
        bundle_file = self.download / "odoo" / "addons" / "sale" / "models" / "__init__.py"
        os.utime(bundle_file, (1577836800, 1577836800))  # 2020-01-01, before both commits
        (self.community / "addons" / "sale" / "models" / "__init__.py").write_text(
            "# sale models, fixed\n", encoding="utf-8"
        )
        return git_commit(self.community, "Fix sale")

    # Mirror flow: dry-run and --apply.

    def test_dry_run_requires_repos_lock(self):
        result = self.run_tool(
            "--download-src", str(self.download),
            "--community-src", str(self.community),
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("error: the following arguments are required: --repos-lock\n", result.stderr)
        self.assertNotIn("[--repos-lock", result.stderr)

    def test_dry_run_reports_the_enterprise_modules(self):
        lock = self.tmp / "repos.lock.yaml"
        write_lock(lock, self.community_head)
        report_path = self.tmp / "report.json"

        result = self.run_tool(
            "--download-src", str(self.download),
            "--community-src", str(self.community),
            "--repos-lock", str(lock),
            "--report-json", str(report_path),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Enterprise import dry-run summary\n", result.stdout)
        self.assertIn("Warnings: none\n", result.stdout)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["mode"], "dry-run")
        self.assertEqual(report["community_dest"], "./odoo")
        self.assertEqual(report["community_lock_revision"], self.community_head)
        self.assertEqual(report["enterprise_modules"], ["account_accountant", "web_studio"])

    def test_dry_run_fails_on_a_community_head_mismatch_and_says_so_in_the_summary(self):
        lock = self.tmp / "repos.lock.yaml"
        write_lock(lock, "0" * 40)

        result = self.run_tool(
            "--download-src", str(self.download),
            "--community-src", str(self.community),
            "--repos-lock", str(lock),
        )

        self.assertEqual(result.returncode, 4)
        self.assertIn("  - Community checkout HEAD differs from repos.lock.yaml revision\n", result.stdout)
        self.assertIn(
            "ERROR: Community worktree HEAD differs from repos.lock.yaml revision. "
            "Use --allow-community-head-mismatch only after review.\n",
            result.stderr,
        )

    def test_dry_run_fails_when_the_download_lacks_a_community_module(self):
        write_module(self.community / "addons" / "crm")
        lock = self.tmp / "repos.lock.yaml"
        write_lock(lock, self.community_head)

        result = self.run_tool(
            "--download-src", str(self.download),
            "--community-src", str(self.community),
            "--repos-lock", str(lock),
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "ERROR: Enterprise download is not an exhaustive superset of the pinned official Community source. "
            "Refresh the Enterprise source bundle and/or run lock-repos --refresh ./odoo, then retry.\n",
            result.stderr,
        )

    def test_dry_run_drift_diagnosis_names_the_pinned_community_and_the_mirror(self):
        fixed_head = self.commit_community_fix_after_the_bundle()
        lock = self.tmp / "repos.lock.yaml"
        write_lock(lock, fixed_head)

        result = self.run_tool(
            "--download-src", str(self.download),
            "--community-src", str(self.community),
            "--repos-lock", str(lock),
        )

        self.assertEqual(result.returncode, 3)
        self.assertIn("differ from the freshly\npinned official Odoo Community source.\n", result.stderr)
        self.assertIn("  diagnosis: source_bundle_lag_confirmed\n", result.stderr)
        self.assertIn("\n  pinned official Community:\n    current commit: ", result.stderr)
        self.assertIn("\n    drifted module will not be imported into the Enterprise mirror.\n", result.stderr)

    def test_apply_commits_one_change_per_module(self):
        mirror = self.make_mirror()
        bundle = self.make_bundle()
        lock = self.tmp / "repos.lock.yaml"
        write_lock(lock, self.community_head)

        result = self.run_tool(
            "--source-bundle", str(bundle),
            "--community-src", str(self.community),
            "--repos-lock", str(lock),
            "--current-src", str(mirror),
            "--apply",
            "--apply-removals",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        subjects = git(mirror, "log", "--reverse", "--format=%s").splitlines()
        self.assertEqual(len(subjects), 5)
        self.assertEqual(subjects[0], "Mirror")
        self.assertRegex(subjects[1], r"^\[ADD\] account_accountant: import from Odoo Enterprise \d{4}-\d{2}-\d{2}$")
        self.assertRegex(subjects[2], r"^\[IMP\] web_studio: update from Odoo Enterprise \d{4}-\d{2}-\d{2}$")
        self.assertRegex(subjects[3], r"^\[REM\] gone_module: remove from Odoo Enterprise \d{4}-\d{2}-\d{2}$")
        self.assertEqual(subjects[4], "[DOC] README: update source bundle identity")
        self.assertEqual(
            sorted(path.name for path in mirror.iterdir()),
            [".git", "README.md", "account_accountant", "web_studio"],
        )
        self.assertEqual(
            (mirror / "web_studio" / "models" / "__init__.py").read_text(encoding="utf-8"),
            "# web_studio models\n",
        )
        self.assertEqual(git(mirror, "status", "--porcelain"), "")

    def test_apply_stops_before_any_commit_on_a_missing_community_module(self):
        mirror = self.make_mirror()
        mirror_head = git(mirror, "rev-parse", "HEAD")
        write_module(self.community / "addons" / "crm")
        lock = self.tmp / "repos.lock.yaml"
        write_lock(lock, self.community_head)

        result = self.run_tool(
            "--download-src", str(self.download),
            "--community-src", str(self.community),
            "--repos-lock", str(lock),
            "--current-src", str(mirror),
            "--apply",
            "--apply-removals",
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("ERROR: Enterprise download is not an exhaustive superset", result.stderr)
        self.assertEqual(git(mirror, "rev-parse", "HEAD"), mirror_head)
        self.assertEqual(git(mirror, "status", "--porcelain"), "")

    def test_apply_stops_before_any_commit_on_drift(self):
        mirror = self.make_mirror()
        mirror_head = git(mirror, "rev-parse", "HEAD")
        (self.download / "odoo" / "addons" / "sale" / "models" / "__init__.py").write_text(
            "# sale models, patched\n", encoding="utf-8"
        )
        lock = self.tmp / "repos.lock.yaml"
        write_lock(lock, self.community_head)

        result = self.run_tool(
            "--download-src", str(self.download),
            "--community-src", str(self.community),
            "--repos-lock", str(lock),
            "--current-src", str(mirror),
            "--apply",
            "--apply-removals",
        )

        self.assertEqual(result.returncode, 3)
        self.assertIn("ERROR: Enterprise source bundle drift detected.", result.stderr)
        self.assertEqual(git(mirror, "rev-parse", "HEAD"), mirror_head)
        self.assertEqual(git(mirror, "status", "--porcelain"), "")

    def test_apply_stops_before_any_commit_on_a_community_head_mismatch(self):
        mirror = self.make_mirror()
        mirror_head = git(mirror, "rev-parse", "HEAD")
        lock = self.tmp / "repos.lock.yaml"
        write_lock(lock, "0" * 40)

        result = self.run_tool(
            "--download-src", str(self.download),
            "--community-src", str(self.community),
            "--repos-lock", str(lock),
            "--current-src", str(mirror),
            "--apply",
            "--apply-removals",
        )

        self.assertEqual(result.returncode, 4)
        self.assertIn("ERROR: Community worktree HEAD differs from repos.lock.yaml revision.", result.stderr)
        self.assertEqual(git(mirror, "rev-parse", "HEAD"), mirror_head)
        self.assertEqual(git(mirror, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
