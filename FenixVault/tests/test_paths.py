"""Archive path mapping, the catalog, and formatting helpers."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fenixvault import catalog  # noqa: E402
from fenixvault.platformutil import (IS_WINDOWS, POSIX_BUCKET,  # noqa: E402
                                     archive_relpath, buckets_in, human_bytes,
                                     restore_abspath)
from fenixvault.scanner import split_ext  # noqa: E402


class TestArchivePaths(unittest.TestCase):
    def test_windows_drive_becomes_a_bucket(self):
        self.assertEqual(archive_relpath("C:\\Users\\Josh\\logo.ai"),
                         "C/Users/Josh/logo.ai")
        self.assertEqual(archive_relpath("d:\\Art\\job.plt"), "D/Art/job.plt")

    def test_round_trip_through_the_archive_and_back(self):
        if IS_WINDOWS:
            original = "C:\\Users\\Josh\\Documents\\logo.ai"
        else:
            original = "/home/josh/documents/logo.ai"
        rel = archive_relpath(original)
        self.assertEqual(os.path.normcase(restore_abspath(rel)),
                         os.path.normcase(original))

    def test_posix_paths_use_the_root_bucket(self):
        if IS_WINDOWS:
            self.skipTest("POSIX-only mapping")
        self.assertEqual(archive_relpath("/home/josh/logo.ai"),
                         f"{POSIX_BUCKET}/home/josh/logo.ai")

    def test_drive_map_redirects_a_bucket(self):
        target = "D:\\Recovered" if IS_WINDOWS else "/mnt/recovered"
        result = restore_abspath("C/Users/Josh/logo.ai", {"C": target})
        self.assertEqual(result, os.path.join(target, "Users", "Josh", "logo.ai"))

    def test_bucket_with_no_tail_maps_to_the_root_itself(self):
        target = "D:\\Recovered" if IS_WINDOWS else "/mnt/recovered"
        self.assertEqual(restore_abspath("C", {"C": target}), target)

    def test_empty_archive_path_is_rejected(self):
        with self.assertRaises(ValueError):
            restore_abspath("")

    def test_buckets_in_lists_distinct_roots_in_order(self):
        self.assertEqual(
            buckets_in(["C/a", "C/b", "D/c", "_root/e"]), ["C", "D", "_root"])


class TestCatalog(unittest.TestCase):
    def test_every_extension_belongs_to_exactly_one_category(self):
        seen: dict[str, str] = {}
        for category in catalog.CATEGORIES:
            for file_type in category.types:
                self.assertNotIn(
                    file_type.ext, seen,
                    f"{file_type.ext} is in both {seen.get(file_type.ext)} "
                    f"and {category.key}")
                seen[file_type.ext] = category.key

    def test_extensions_are_lowercase_and_dotted(self):
        for category in catalog.CATEGORIES:
            for file_type in category.types:
                self.assertTrue(file_type.ext.startswith("."), file_type.ext)
                self.assertEqual(file_type.ext, file_type.ext.lower())

    def test_the_shop_critical_types_are_on_by_default(self):
        defaults = catalog.default_extensions()
        for ext in (".ai", ".eps", ".svg", ".psd", ".cdr",   # artwork
                    ".plt", ".studio3", ".fcm", ".gsd",      # cutters
                    ".pdf", ".xlsx", ".qbw",                 # paperwork
                    ".jpg", ".ttf", ".dst"):                 # media, fonts, stitch
            self.assertIn(ext, defaults, f"{ext} should be on by default")

    def test_bulky_media_is_off_by_default(self):
        defaults = catalog.default_extensions()
        for ext in (".mp4", ".mov", ".mp3"):
            self.assertNotIn(ext, defaults)

    def test_category_lookup(self):
        self.assertEqual(catalog.category_of(".AI"), "design")
        self.assertEqual(catalog.category_of(".plt"), "vinyl")
        self.assertIsNone(catalog.category_of(".zzq"))
        self.assertEqual(catalog.label_of(".ai"), "Adobe Illustrator artwork")

    def test_installed_programs_switch_on_their_categories(self):
        hits = catalog.categories_for_programs(
            ["Adobe Illustrator 2026", "Silhouette Studio", "QuickBooks Desktop"])
        self.assertIn("design", hits)
        self.assertIn("vinyl", hits)
        self.assertIn("spreadsheets", hits)

    def test_normalise_ext_accepts_what_people_actually_type(self):
        for raw in ("ai", ".ai", "AI", " .Ai ", "*.ai"):
            self.assertEqual(catalog.normalise_ext(raw), ".ai")
        for bad in ("", "   ", ".", "a/b", "a b"):
            self.assertIsNone(catalog.normalise_ext(bad))


class TestOutputPlumbing(unittest.TestCase):
    """The packaged build is a windowed exe, so printing needs a safety net."""

    def setUp(self) -> None:
        self._stdout, self._stderr = sys.stdout, sys.stderr

    def tearDown(self) -> None:
        sys.stdout, sys.stderr = self._stdout, self._stderr

    def test_a_working_stream_is_left_alone(self):
        from io import StringIO

        from fenixvault import cli
        captured = StringIO()
        sys.stdout = captured
        cli.ensure_output()
        self.assertIs(sys.stdout, captured,
                      "a usable stdout must not be swapped out from under a "
                      "scheduler or CI that is capturing it")

    def test_a_missing_stream_never_crashes_a_backup(self):
        from fenixvault import cli
        sys.stdout = None       # what a windowed exe can hand us
        sys.stderr = None
        cli.ensure_output()
        sys.stdout.write("this must not raise")
        sys.stdout.flush()
        sys.stderr.write("nor this")

    def test_a_broken_stream_is_replaced(self):
        from fenixvault import cli

        class Broken:
            def write(self, _text):
                raise OSError("the handle is closed")

            def flush(self):
                raise OSError("the handle is closed")

        sys.stdout = Broken()
        cli.ensure_output()
        sys.stdout.write("safe now")


class TestHelpers(unittest.TestCase):
    def test_split_ext(self):
        self.assertEqual(split_ext("logo.AI"), ".ai")
        self.assertEqual(split_ext("archive.tar.gz"), ".gz")
        self.assertEqual(split_ext("README"), "")
        self.assertEqual(split_ext(".gitignore"), "")   # dotfile, not a type
        self.assertEqual(split_ext("trailing."), "")

    def test_human_bytes(self):
        self.assertEqual(human_bytes(0), "0 B")
        self.assertEqual(human_bytes(1536), "1.5 KB")
        self.assertEqual(human_bytes(5 * 1024 ** 3), "5.0 GB")


if __name__ == "__main__":
    unittest.main()
