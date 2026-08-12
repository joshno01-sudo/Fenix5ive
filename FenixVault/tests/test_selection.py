"""Tri-state folder selection and the exclude policy."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fenixvault.platformutil import IS_WINDOWS  # noqa: E402
from fenixvault.selection import (OFF, ON, PARTIAL, ExcludeRules,  # noqa: E402
                                  FolderSelection)


def p(*parts: str) -> str:
    """Build an absolute path that is valid on the running platform."""
    if IS_WINDOWS:
        return "C:\\" + "\\".join(parts)
    return "/" + "/".join(parts)


class TestFolderSelection(unittest.TestCase):
    def setUp(self) -> None:
        self.selection = FolderSelection()

    def test_nothing_selected_by_default(self):
        self.assertEqual(self.selection.state(p("users", "josh")), OFF)
        self.assertFalse(self.selection.effective(p("users", "josh")))
        self.assertTrue(self.selection.is_empty())

    def test_selecting_a_folder_includes_its_children(self):
        self.selection.set(p("users", "josh"), True)
        self.assertEqual(self.selection.state(p("users", "josh")), ON)
        self.assertTrue(self.selection.effective(p("users", "josh", "docs")))
        self.assertTrue(self.selection.effective(
            p("users", "josh", "docs", "deep", "deeper")))

    def test_ancestor_of_a_selection_is_partial(self):
        self.selection.set(p("users", "josh"), True)
        self.assertEqual(self.selection.state(p("users")), PARTIAL)

    def test_excluding_a_child_makes_the_parent_partial(self):
        self.selection.set(p("users", "josh"), True)
        self.selection.set(p("users", "josh", "appdata"), False)
        self.assertEqual(self.selection.state(p("users", "josh")), PARTIAL)
        self.assertEqual(self.selection.state(p("users", "josh", "appdata")), OFF)
        self.assertTrue(self.selection.effective(p("users", "josh", "docs")))
        self.assertFalse(self.selection.effective(
            p("users", "josh", "appdata", "local")))

    def test_reselecting_a_parent_clears_rules_beneath_it(self):
        self.selection.set(p("users", "josh"), True)
        self.selection.set(p("users", "josh", "appdata"), False)
        self.selection.set(p("users"), True)
        self.assertEqual(self.selection.state(p("users")), ON)
        self.assertTrue(self.selection.effective(p("users", "josh", "appdata")))
        self.assertEqual(len(self.selection.rules()), 1)

    def test_redundant_rules_are_not_stored(self):
        self.selection.set(p("users"), True)
        self.selection.set(p("users", "josh"), True)  # already implied
        self.assertEqual(list(self.selection.rules()), [
            os.path.normcase(p("users")) if IS_WINDOWS else p("users")])

    def test_roots_returns_only_top_level_inclusions(self):
        self.selection.set(p("users", "josh", "docs"), True)
        self.selection.set(p("users", "josh", "pics"), True)
        self.assertEqual(len(self.selection.roots()), 2)
        self.selection.set(p("users", "josh"), True)
        self.assertEqual(len(self.selection.roots()), 1)

    def test_toggle_flips_state(self):
        path = p("users", "josh")
        self.assertTrue(self.selection.toggle(path))
        self.assertEqual(self.selection.state(path), ON)
        self.assertFalse(self.selection.toggle(path))
        self.assertEqual(self.selection.state(path), OFF)

    def test_toggling_a_partial_folder_turns_it_fully_on(self):
        self.selection.set(p("users", "josh"), True)
        self.selection.set(p("users", "josh", "appdata"), False)
        self.selection.toggle(p("users", "josh"))
        self.assertEqual(self.selection.state(p("users", "josh")), ON)
        self.assertTrue(self.selection.effective(p("users", "josh", "appdata")))

    def test_load_round_trips_rules(self):
        self.selection.set(p("users", "josh"), True)
        self.selection.set(p("users", "josh", "appdata"), False)
        saved = self.selection.rules()
        restored = FolderSelection()
        restored.load(saved)
        self.assertEqual(restored.state(p("users", "josh")), PARTIAL)
        self.assertFalse(restored.effective(p("users", "josh", "appdata")))


class TestExcludeRules(unittest.TestCase):
    def test_junk_folders_are_skipped(self):
        rules = ExcludeRules()
        self.assertTrue(rules.should_skip_dir(p("proj"), "node_modules"))
        self.assertTrue(rules.should_skip_dir(p("proj"), "__pycache__"))
        self.assertTrue(rules.should_skip_dir(p("users"), "Temp"))
        self.assertTrue(rules.should_skip_dir(p("users"), "GPUCache"))

    def test_recycle_bin_is_always_skipped(self):
        rules = ExcludeRules(skip_system=False, skip_junk=False,
                             skip_hidden=False)
        self.assertTrue(rules.should_skip_dir(p(), "$Recycle.Bin"))
        self.assertTrue(rules.should_skip_dir(p(), "System Volume Information"))

    def test_program_folders_are_skipped_when_asked(self):
        rules = ExcludeRules(skip_system=True)
        self.assertTrue(rules.should_skip_dir(p(), "Program Files"))
        self.assertTrue(rules.should_skip_dir(p(), "Windows"))
        loose = ExcludeRules(skip_system=False, skip_hidden=False)
        self.assertFalse(loose.should_skip_dir(p(), "Program Files"))

    def test_a_user_folder_named_like_a_system_one_is_kept(self):
        # "Recovery" at a drive root is Windows'; inside Documents it is theirs.
        rules = ExcludeRules(skip_system=True, skip_hidden=False)
        self.assertFalse(
            rules.should_skip_dir(p("users", "josh", "documents"), "Recovery"))

    def test_normal_folders_survive(self):
        rules = ExcludeRules()
        for name in ("Documents", "Cut Files", "Customer Artwork", "2026 Jobs"):
            self.assertFalse(rules.should_skip_dir(p("users", "josh"), name),
                             f"{name} should not be skipped")

    def test_junk_files_are_skipped(self):
        rules = ExcludeRules()
        self.assertTrue(rules.should_skip_file("Thumbs.db"))
        self.assertTrue(rules.should_skip_file("desktop.ini"))
        self.assertTrue(rules.should_skip_file("pagefile.sys"))
        self.assertFalse(rules.should_skip_file("logo.ai"))

    def test_outlook_survives_the_appdata_cull(self):
        rules = ExcludeRules(skip_appdata_local=True, skip_hidden=False,
                             skip_junk=False)
        base = p("users", "josh", "AppData", "Local", "Microsoft")
        self.assertFalse(rules.should_skip_dir(base, "Outlook"))
        # ...while the rest of AppData\Local still goes.
        self.assertTrue(rules.should_skip_dir(
            p("users", "josh", "AppData", "Local"), "SomeVendorCache"))


if __name__ == "__main__":
    unittest.main()
