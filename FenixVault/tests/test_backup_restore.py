"""End-to-end: scan, copy, and put it all back.

These build a miniature version of a real shop PC in a temp folder, back it up,
delete the originals, and check that what comes back is byte-for-byte what went
in -- with the folder tree intact.
"""

import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fenixvault import catalog, manifest  # noqa: E402
from fenixvault.backup import BackupOptions, run_backup  # noqa: E402
from fenixvault.restore import (CONFLICT_KEEP_BOTH,  # noqa: E402
                                CONFLICT_OVERWRITE, CONFLICT_SKIP,
                                RestoreOptions, read_plan, run_restore,
                                suggest_profile_remap)
from fenixvault.scanner import scan  # noqa: E402
from fenixvault.selection import ExcludeRules, FolderSelection  # noqa: E402

# path -> contents. Mirrors the shape of a real vinyl shop's drive.
FIXTURE = {
    "Desktop/Cut Files/fenix-logo.ai": "illustrator master artwork",
    "Desktop/Cut Files/door-decal.plt": "plotter path data",
    "Desktop/Cut Files/window.studio3": "silhouette project",
    "Desktop/Cut Files/vendor.zzq": "format we have never heard of",
    "Documents/Invoices/2026-001.pdf": "invoice",
    "Documents/Invoices/ledger.xlsx": "the books",
    "Documents/Quotes/big job.docx": "quote with a space in the name",
    "Pictures/Jobs/truck-wrap.jpg": "photo bytes",
    "Pictures/Jobs/shoot.cr2": "raw bytes",
    "Pictures/Jobs/timelapse.mp4": "big video nobody asked for",
    # Should never be copied: junk and system noise.
    "Documents/node_modules/pkg/icon.png": "dependency junk",
    "AppData/Local/BrowserCo/Cache/blob.jpg": "cache junk",
    "Documents/Thumbs.db": "explorer junk",
}

# The entries above that the exclude policy drops regardless of their extension.
JUNK = {
    "Documents/node_modules/pkg/icon.png",
    "AppData/Local/BrowserCo/Cache/blob.jpg",
    "Documents/Thumbs.db",
}


class BackupRestoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tempfile.mkdtemp(prefix="fenixvault-test-")
        self.source = os.path.join(self.root, "PC")
        self.usb = os.path.join(self.root, "USB")
        os.makedirs(self.usb)
        for relative, text in FIXTURE.items():
            path = os.path.join(self.source, *relative.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        self.selection = FolderSelection()
        self.selection.set(self.source, True)
        self.excludes = ExcludeRules(skip_hidden=False)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    # -- helpers ------------------------------------------------------

    def source_path(self, relative: str) -> str:
        return os.path.join(self.source, *relative.split("/"))

    def do_backup(self, extensions=None, backup_dir=None, **kwargs):
        extensions = extensions or catalog.default_extensions()
        backup_dir = backup_dir or os.path.join(self.usb, "Backup")
        result = run_backup(self.selection, self.excludes, extensions,
                            backup_dir, BackupOptions(**kwargs))
        return backup_dir, result

    def read(self, path: str) -> str:
        with open(path, encoding="utf-8") as handle:
            return handle.read()


class TestScan(BackupRestoreCase):
    def test_scan_counts_by_extension_and_skips_junk(self):
        result = scan(self.selection, self.excludes)
        self.assertEqual(result.ext_counts.get(".ai"), 1)
        self.assertEqual(result.ext_counts.get(".plt"), 1)
        self.assertEqual(result.ext_counts.get(".zzq"), 1)
        # node_modules and the browser cache never got walked...
        self.assertIsNone(result.ext_counts.get(".png"))
        # ...and Thumbs.db is filtered by name.
        self.assertIsNone(result.ext_counts.get(".db"))

    def test_files_for_sums_only_the_chosen_types(self):
        result = scan(self.selection, self.excludes)
        count, size = result.files_for({".ai", ".plt"})
        self.assertEqual(count, 2)
        self.assertEqual(size, len(FIXTURE["Desktop/Cut Files/fenix-logo.ai"])
                         + len(FIXTURE["Desktop/Cut Files/door-decal.plt"]))

    def test_unticking_a_subfolder_removes_it_from_the_scan(self):
        self.selection.set(os.path.join(self.source, "Pictures"), False)
        result = scan(self.selection, self.excludes)
        self.assertIsNone(result.ext_counts.get(".jpg"))
        self.assertEqual(result.ext_counts.get(".ai"), 1)

    def test_a_chosen_folder_under_appdata_local_is_still_scanned(self):
        # A folder the user picked must be scanned even when it sits below a
        # path the default policy would prune. Windows temp folders live under
        # AppData\Local, which is how this was found: the program reported
        # success having copied nothing at all.
        nested = os.path.join(self.root, "AppData", "Local", "Temp", "ShopPC")
        os.makedirs(os.path.join(nested, "Artwork"))
        with open(os.path.join(nested, "Artwork", "logo.ai"), "w",
                  encoding="utf-8") as handle:
            handle.write("artwork")

        selection = FolderSelection()
        selection.set(nested, True)
        result = scan(selection, ExcludeRules())
        self.assertEqual(result.ext_counts.get(".ai"), 1)

    def test_appdata_local_is_still_pruned_when_walking_from_above(self):
        profile = os.path.join(self.root, "Profile")
        cache = os.path.join(profile, "AppData", "Local", "VendorCache")
        os.makedirs(cache)
        with open(os.path.join(cache, "junk.ai"), "w", encoding="utf-8") as handle:
            handle.write("cache junk")

        selection = FolderSelection()
        selection.set(profile, True)
        result = scan(selection, ExcludeRules())
        self.assertIsNone(result.ext_counts.get(".ai"))

    def test_cancelling_stops_the_scan(self):
        cancel = threading.Event()
        cancel.set()
        result = scan(self.selection, self.excludes, cancel=cancel)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.total_files, 0)


class TestBackup(BackupRestoreCase):
    def test_backup_mirrors_the_tree(self):
        backup_dir, result = self.do_backup()
        self.assertEqual(result.files_failed, 0)
        self.assertFalse(result.cancelled)

        data = manifest.data_dir(backup_dir)
        for relative in ("Desktop/Cut Files/fenix-logo.ai",
                         "Documents/Invoices/ledger.xlsx",
                         "Documents/Quotes/big job.docx",
                         "Pictures/Jobs/shoot.cr2"):
            copied = self._in_backup(data, relative)
            self.assertTrue(os.path.isfile(copied), f"missing {relative}")
            self.assertEqual(self.read(copied), FIXTURE[relative])

    def _in_backup(self, data_root: str, relative: str) -> str:
        from fenixvault.platformutil import archive_relpath
        rel = archive_relpath(self.source_path(relative))
        return os.path.join(data_root, *rel.split("/"))

    def test_unselected_types_are_not_copied(self):
        backup_dir, _ = self.do_backup()
        data = manifest.data_dir(backup_dir)
        # Video is off by default; the unknown vendor format was never ticked.
        self.assertFalse(os.path.isfile(
            self._in_backup(data, "Pictures/Jobs/timelapse.mp4")))
        self.assertFalse(os.path.isfile(
            self._in_backup(data, "Desktop/Cut Files/vendor.zzq")))

    def test_an_explicitly_added_type_is_copied(self):
        extensions = catalog.default_extensions() | {".zzq"}
        backup_dir, _ = self.do_backup(extensions=extensions)
        data = manifest.data_dir(backup_dir)
        self.assertTrue(os.path.isfile(
            self._in_backup(data, "Desktop/Cut Files/vendor.zzq")))

    def test_manifest_records_every_copied_file_with_a_fingerprint(self):
        backup_dir, result = self.do_backup()
        entries = list(manifest.read_entries(backup_dir))
        self.assertEqual(len(entries), result.files_copied)
        for entry in entries:
            self.assertEqual(len(entry.sha256), 64)
            self.assertTrue(entry.src)
            self.assertTrue(entry.rel)
            self.assertGreater(entry.size, 0)

    def test_info_header_is_sealed_as_complete(self):
        backup_dir, result = self.do_backup()
        info = manifest.read_info(backup_dir)
        self.assertTrue(info.complete)
        self.assertEqual(info.total_files, result.files_copied)
        self.assertTrue(info.verified)

    def test_the_restore_tool_and_instructions_ship_with_the_backup(self):
        backup_dir, _ = self.do_backup()
        self.assertTrue(os.path.isfile(
            os.path.join(backup_dir, manifest.README_FILENAME)))
        launcher = os.path.join(backup_dir, "RESTORE.bat")
        self.assertTrue(os.path.isfile(launcher))
        self.assertTrue(os.path.isdir(
            os.path.join(backup_dir, "_RestoreTool", "fenixvault")))

    def test_a_backup_folder_is_recognised_as_one(self):
        backup_dir, _ = self.do_backup()
        self.assertTrue(manifest.is_backup_folder(backup_dir))
        self.assertEqual(manifest.find_backup_root(
            manifest.data_dir(backup_dir)), backup_dir)
        self.assertFalse(manifest.is_backup_folder(self.source))

    def test_second_run_reuses_unchanged_files(self):
        backup_dir, first = self.do_backup()
        self.assertGreater(first.files_copied, 0)
        _, second = self.do_backup(backup_dir=backup_dir)
        self.assertEqual(second.files_copied, 0)
        self.assertEqual(second.files_reused, first.files_copied)

    def test_second_run_picks_up_an_edited_file(self):
        backup_dir, _ = self.do_backup()
        target = self.source_path("Documents/Invoices/ledger.xlsx")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("the books, revised")
        os.utime(target, (0, 0))  # force a different mtime
        _, second = self.do_backup(backup_dir=backup_dir)
        self.assertEqual(second.files_copied, 1)
        data = manifest.data_dir(backup_dir)
        self.assertEqual(
            self.read(self._in_backup(data, "Documents/Invoices/ledger.xlsx")),
            "the books, revised")

    def test_backup_does_not_copy_itself(self):
        # Destination sits inside the folder being backed up: without a guard
        # this is an infinite regress.
        inside = os.path.join(self.source, "Documents", "Backup")
        backup_dir, result = self.do_backup(backup_dir=inside)
        self.assertEqual(result.files_failed, 0)
        for entry in manifest.read_entries(backup_dir):
            self.assertNotIn(os.path.join("Documents", "Backup"), entry.src)

    def test_cancelling_leaves_a_readable_backup(self):
        cancel = threading.Event()
        cancel.set()
        backup_dir = os.path.join(self.usb, "Partial")
        result = run_backup(self.selection, self.excludes,
                            catalog.default_extensions(), backup_dir,
                            BackupOptions(), cancel=cancel)
        self.assertTrue(result.cancelled)
        info = manifest.read_info(backup_dir)
        self.assertFalse(info.complete)


class TestRestore(BackupRestoreCase):
    def test_full_round_trip_after_deleting_the_originals(self):
        backup_dir, backup = self.do_backup()
        originals = {
            relative: self.read(self.source_path(relative))
            for relative in FIXTURE
            if relative not in JUNK
            and os.path.splitext(relative)[1] in catalog.default_extensions()
        }
        self.assertEqual(len(originals), backup.files_copied)
        shutil.rmtree(os.path.join(self.source, "Desktop"))
        shutil.rmtree(os.path.join(self.source, "Documents"))
        shutil.rmtree(os.path.join(self.source, "Pictures"))

        result = run_restore(backup_dir, RestoreOptions(conflict=CONFLICT_SKIP))
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.files_restored, backup.files_copied)
        self.assertEqual(result.files_corrupt, 0)

        for relative, text in originals.items():
            path = self.source_path(relative)
            self.assertTrue(os.path.isfile(path), f"{relative} was not restored")
            self.assertEqual(self.read(path), text)

    def test_restore_recreates_missing_folders(self):
        backup_dir, _ = self.do_backup()
        shutil.rmtree(os.path.join(self.source, "Desktop"))
        run_restore(backup_dir, RestoreOptions())
        self.assertTrue(os.path.isdir(
            os.path.join(self.source, "Desktop", "Cut Files")))

    def test_skip_leaves_existing_files_untouched(self):
        backup_dir, _ = self.do_backup()
        target = self.source_path("Documents/Invoices/ledger.xlsx")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("newer local copy")
        result = run_restore(backup_dir, RestoreOptions(conflict=CONFLICT_SKIP))
        self.assertGreater(result.files_skipped, 0)
        self.assertEqual(self.read(target), "newer local copy")

    def test_overwrite_replaces_existing_files(self):
        backup_dir, _ = self.do_backup()
        target = self.source_path("Documents/Invoices/ledger.xlsx")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("newer local copy")
        run_restore(backup_dir, RestoreOptions(conflict=CONFLICT_OVERWRITE))
        self.assertEqual(self.read(target), FIXTURE["Documents/Invoices/ledger.xlsx"])

    def test_keep_both_writes_alongside(self):
        backup_dir, _ = self.do_backup()
        target = self.source_path("Documents/Invoices/ledger.xlsx")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("newer local copy")
        run_restore(backup_dir, RestoreOptions(conflict=CONFLICT_KEEP_BOTH))
        self.assertEqual(self.read(target), "newer local copy")
        beside = self.source_path("Documents/Invoices/ledger (restored).xlsx")
        self.assertTrue(os.path.isfile(beside))
        self.assertEqual(self.read(beside),
                         FIXTURE["Documents/Invoices/ledger.xlsx"])

    def test_sandbox_restore_touches_nothing_outside_it(self):
        backup_dir, backup = self.do_backup()
        before = self.read(self.source_path("Documents/Invoices/ledger.xlsx"))
        sandbox = os.path.join(self.root, "Sandbox")
        result = run_restore(backup_dir, RestoreOptions(sandbox_root=sandbox))
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.files_restored, backup.files_copied)
        self.assertEqual(self.read(self.source_path(
            "Documents/Invoices/ledger.xlsx")), before)
        found = [name for _root, _dirs, files in os.walk(sandbox)
                 for name in files]
        self.assertIn("fenix-logo.ai", found)

    def test_profile_remap_sends_files_to_a_new_user_folder(self):
        backup_dir, backup = self.do_backup()
        info = manifest.read_info(backup_dir)
        # Pretend the backup came from this fixture as the user's profile.
        info.source_profile = self.source
        profile_from = self._archive_rel(self.source)
        new_home = os.path.join(self.root, "NewUser")
        result = run_restore(backup_dir, RestoreOptions(
            profile_from=profile_from, profile_to=new_home))
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.files_restored, backup.files_copied)
        self.assertEqual(
            self.read(os.path.join(new_home, "Desktop", "Cut Files",
                                   "fenix-logo.ai")),
            FIXTURE["Desktop/Cut Files/fenix-logo.ai"])

    def _archive_rel(self, path: str) -> str:
        from fenixvault.platformutil import archive_relpath
        return archive_relpath(path)

    def test_suggest_profile_remap_is_silent_when_the_user_matches(self):
        from fenixvault.platformutil import user_profile_dir
        info = manifest.BackupInfo(source_profile=user_profile_dir())
        self.assertEqual(suggest_profile_remap(info), ("", ""))

    def test_plan_summarises_without_writing_anything(self):
        backup_dir, backup = self.do_backup()
        plan = read_plan(backup_dir)
        self.assertEqual(plan.total_files, backup.files_copied)
        self.assertFalse(plan.format_too_new)
        self.assertIn(".ai", plan.by_extension)
        self.assertEqual(sum(count for count, _ in plan.buckets.values()),
                         backup.files_copied)

    def test_corruption_in_the_backup_is_detected(self):
        backup_dir, _ = self.do_backup()
        entry = next(e for e in manifest.read_entries(backup_dir)
                     if e.ext == ".ai")
        stored = os.path.join(manifest.data_dir(backup_dir),
                              *entry.rel.split("/"))
        with open(stored, "w", encoding="utf-8") as handle:
            handle.write("a passing cosmic ray flipped these bytes")
        os.remove(self.source_path("Desktop/Cut Files/fenix-logo.ai"))
        result = run_restore(backup_dir, RestoreOptions(verify=True))
        self.assertEqual(result.files_corrupt, 1)
        self.assertFalse(result.ok)

    def test_a_future_format_is_refused_rather_than_guessed_at(self):
        backup_dir, _ = self.do_backup()
        plan = read_plan(backup_dir)
        plan.format_too_new = True
        result = run_restore(backup_dir, RestoreOptions(), plan=plan)
        self.assertFalse(result.ok)
        self.assertIn("newer version", result.errors[0])


if __name__ == "__main__":
    unittest.main()
