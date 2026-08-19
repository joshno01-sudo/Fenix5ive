"""Online-only files must be left in the cloud, and said so out loud.

OneDrive Files On-Demand and Dropbox Smart Sync present files that look
completely ordinary but hold no data locally. Copying one downloads it first,
so a backup that treats them as normal files quietly turns into a re-download
of the entire cloud account.

These attributes cannot be set on a non-Windows filesystem, so the tests patch
the one function that reads them. That keeps the policy under test on every
platform, which matters because the policy is the part that goes wrong.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fenixvault import catalog, scanner  # noqa: E402
from fenixvault.backup import BackupOptions, run_backup  # noqa: E402
from fenixvault.platformutil import (  # noqa: E402
    FILE_ATTRIBUTE_OFFLINE, FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS,
    FILE_ATTRIBUTE_RECALL_ON_OPEN, is_cloud_placeholder)
from fenixvault.scanner import scan  # noqa: E402
from fenixvault.selection import ExcludeRules, FolderSelection  # noqa: E402


class TestAttributeCheck(unittest.TestCase):
    def test_each_placeholder_attribute_is_recognised(self):
        for attribute in (FILE_ATTRIBUTE_OFFLINE,
                          FILE_ATTRIBUTE_RECALL_ON_OPEN,
                          FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS):
            self.assertTrue(is_cloud_placeholder(attribute))
            # Real files carry other bits alongside; the check must still fire.
            self.assertTrue(is_cloud_placeholder(attribute | 0x20))

    def test_an_ordinary_file_is_not_a_placeholder(self):
        FILE_ATTRIBUTE_ARCHIVE = 0x20
        FILE_ATTRIBUTE_READONLY = 0x01
        self.assertFalse(is_cloud_placeholder(0))
        self.assertFalse(is_cloud_placeholder(FILE_ATTRIBUTE_ARCHIVE))
        self.assertFalse(is_cloud_placeholder(FILE_ATTRIBUTE_READONLY))

    def test_missing_attributes_read_as_zero_off_windows(self):
        from fenixvault.platformutil import file_attributes

        class NoAttributes:
            st_size = 10

        self.assertEqual(file_attributes(NoAttributes()), 0)


def pretend_cloud(*names: str):
    """Make the named files look like online-only placeholders."""
    wanted = set(names)

    def fake_attributes(stat_result):
        return (FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
                if getattr(stat_result, "_pretend_cloud", False) else 0)

    real_stat = os.stat_result

    def scandir_stat(entry_stat, entry_name):
        result = entry_stat
        if entry_name in wanted:
            object.__setattr__(result, "_pretend_cloud", True)
        return result

    del real_stat, scandir_stat      # documentation of intent only
    return wanted, fake_attributes


class CloudCase(unittest.TestCase):
    """Fixture with two ordinary files and two pretend cloud placeholders."""

    CLOUD = {"in-the-cloud.ai", "also-cloud.psd"}
    LOCAL = {"on-this-disk.ai", "also-local.pdf"}

    def setUp(self) -> None:
        self.root = tempfile.mkdtemp(prefix="fenixvault-cloud-")
        self.source = os.path.join(self.root, "PC", "Artwork")
        os.makedirs(self.source)
        for name in sorted(self.CLOUD | self.LOCAL):
            with open(os.path.join(self.source, name), "w",
                      encoding="utf-8") as handle:
                handle.write("x" * 32)
        self.selection = FolderSelection()
        self.selection.set(os.path.join(self.root, "PC"), True)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _patched_attributes(self):
        """Patch scanner.file_attributes to flag the CLOUD files by name.

        The scanner only has a stat result at that point, so the fixture is
        keyed on size: cloud files are made a different length to local ones.
        Simpler and more honest than faking os.stat_result internals.
        """
        cloud_sizes = set()
        for name in self.CLOUD:
            path = os.path.join(self.source, name)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("y" * 99)      # distinct size marks them
            cloud_sizes.add(os.path.getsize(path))

        def fake(stat_result):
            return (FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
                    if stat_result.st_size in cloud_sizes else 0)

        return mock.patch.object(scanner, "file_attributes", fake)


class TestScanSkipsPlaceholders(CloudCase):
    def test_online_only_files_are_left_out_and_counted(self):
        with self._patched_attributes():
            result = scan(self.selection, ExcludeRules())
        self.assertEqual(result.placeholders_skipped, len(self.CLOUD))
        self.assertGreater(result.placeholder_bytes, 0)
        self.assertEqual(result.total_files, len(self.LOCAL))
        # .psd is a design file, so its absence is a real decision, not a
        # side effect of the type filter.
        self.assertIsNone(result.ext_counts.get(".psd"))
        self.assertEqual(result.ext_counts.get(".ai"), 1)

    def test_turning_the_rule_off_includes_them_again(self):
        with self._patched_attributes():
            result = scan(self.selection,
                          ExcludeRules(skip_cloud_placeholders=False))
        self.assertEqual(result.placeholders_skipped, 0)
        self.assertEqual(result.total_files, len(self.CLOUD | self.LOCAL))
        self.assertEqual(result.ext_counts.get(".psd"), 1)

    def test_nothing_is_skipped_when_no_file_is_a_placeholder(self):
        result = scan(self.selection, ExcludeRules())
        self.assertEqual(result.placeholders_skipped, 0)
        self.assertEqual(result.total_files, len(self.CLOUD | self.LOCAL))


class TestBackupSkipsPlaceholders(CloudCase):
    def _run(self, **kwargs):
        backup_dir = os.path.join(self.root, "USB", "Backup")
        options = BackupOptions(capture_snapshot=False, **kwargs)
        with self._patched_attributes():
            result = run_backup(self.selection, ExcludeRules(),
                                catalog.default_extensions(), backup_dir,
                                options)
        return backup_dir, result

    def test_placeholders_are_not_copied(self):
        backup_dir, result = self._run()
        self.assertEqual(result.placeholders_skipped, len(self.CLOUD))
        self.assertEqual(result.files_copied, len(self.LOCAL))
        copied = [name for _root, _dirs, files in os.walk(backup_dir)
                  for name in files]
        for name in self.CLOUD:
            self.assertNotIn(name, copied)

    def test_what_was_left_behind_is_written_down(self):
        # Silently omitting a file is the worst outcome available here, so the
        # backup has to carry the list of what it did not take.
        backup_dir, result = self._run()
        self.assertTrue(result.cloud_list_path)
        listing = os.path.join(backup_dir, "cloud-only-files.txt")
        self.assertTrue(os.path.isfile(listing))
        with open(listing, encoding="utf-8") as handle:
            text = handle.read()
        for name in self.CLOUD:
            self.assertIn(name, text)
        self.assertIn("still exist in that cloud account", text)

    def test_the_summary_mentions_them(self):
        _backup_dir, result = self._run()
        self.assertIn("online-only", result.summary())

    def test_a_backup_with_no_placeholders_writes_no_list(self):
        backup_dir = os.path.join(self.root, "USB", "Clean")
        result = run_backup(self.selection, ExcludeRules(),
                            catalog.default_extensions(), backup_dir,
                            BackupOptions(capture_snapshot=False))
        self.assertIsNone(result.cloud_list_path)
        self.assertFalse(os.path.exists(
            os.path.join(backup_dir, "cloud-only-files.txt")))
        self.assertNotIn("online-only", result.summary())

    def test_the_skipped_files_do_not_count_as_failures(self):
        # They are a deliberate choice, not an error. Counting them as failures
        # would make every OneDrive user think their backup went wrong.
        _backup_dir, result = self._run()
        self.assertEqual(result.files_failed, 0)
        self.assertTrue(result.ok)
        self.assertIsNone(result.report_path)


if __name__ == "__main__":
    unittest.main()
