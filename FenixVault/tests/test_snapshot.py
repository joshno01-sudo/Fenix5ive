"""The PNG encoder, the rebuild report, and the snapshot's place in a backup."""

import os
import shutil
import struct
import sys
import tempfile
import unittest
import zlib
from binascii import crc32

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fenixvault import catalog, manifest, report, sysinfo  # noqa: E402
from fenixvault.backup import BackupOptions, run_backup  # noqa: E402
from fenixvault.pngwrite import (PNG_SIGNATURE, bgra_to_rgb,  # noqa: E402
                                 encode_png, write_png)
from fenixvault.selection import ExcludeRules, FolderSelection  # noqa: E402
from fenixvault.sysinfo import Section, SysSnapshot  # noqa: E402


def parse_png(data: bytes) -> dict:
    """Minimal PNG reader, so the encoder is checked against the spec."""
    assert data[:8] == PNG_SIGNATURE, "bad signature"
    chunks = {}
    order = []
    offset = 8
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset:offset + 4])
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        (stored_crc,) = struct.unpack(
            ">I", data[offset + 8 + length:offset + 12 + length])
        assert stored_crc == crc32(kind + body) & 0xFFFFFFFF, f"bad CRC on {kind}"
        chunks[kind] = chunks.get(kind, b"") + body
        order.append(kind)
        offset += 12 + length
    width, height, depth, colour, _comp, _filt, _inter = struct.unpack(
        ">IIBBBBB", chunks[b"IHDR"])
    return {"width": width, "height": height, "depth": depth,
            "colour": colour, "order": order,
            "pixels": zlib.decompress(chunks[b"IDAT"])}


class TestPngWriter(unittest.TestCase):
    def test_encodes_a_readable_png(self):
        pixels = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255])
        parsed = parse_png(encode_png(2, 2, pixels))
        self.assertEqual((parsed["width"], parsed["height"]), (2, 2))
        self.assertEqual(parsed["depth"], 8)
        self.assertEqual(parsed["colour"], 2)          # RGB
        self.assertEqual(parsed["order"][0], b"IHDR")
        self.assertEqual(parsed["order"][-1], b"IEND")

    def test_pixels_survive_the_round_trip(self):
        pixels = bytes(range(0, 36))                   # 3x4 RGB
        parsed = parse_png(encode_png(3, 4, pixels))
        # Every scanline is prefixed with its filter byte (0 = none).
        recovered = bytearray()
        stride = 3 * 3
        for row in range(4):
            start = row * (stride + 1)
            self.assertEqual(parsed["pixels"][start], 0)
            recovered += parsed["pixels"][start + 1:start + 1 + stride]
        self.assertEqual(bytes(recovered), pixels)

    def test_rgba_is_supported(self):
        parsed = parse_png(encode_png(1, 1, bytes([1, 2, 3, 4]), channels=4))
        self.assertEqual(parsed["colour"], 6)

    def test_mismatched_pixel_data_is_rejected(self):
        with self.assertRaises(ValueError):
            encode_png(4, 4, b"\x00" * 10)
        with self.assertRaises(ValueError):
            encode_png(0, 4, b"")
        with self.assertRaises(ValueError):
            encode_png(2, 2, b"\x00" * 12, channels=2)

    def test_bgra_to_rgb_reorders_and_drops_alpha(self):
        # Windows hands back blue, green, red, alpha per pixel.
        bgra = bytes([10, 20, 30, 255,   40, 50, 60, 128])
        self.assertEqual(bgra_to_rgb(bgra), bytes([30, 20, 10, 60, 50, 40]))

    def test_write_png_produces_a_file(self):
        folder = tempfile.mkdtemp()
        try:
            path = os.path.join(folder, "shot.png")
            write_png(path, 2, 1, bytes([1, 2, 3, 4, 5, 6]))
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(8), PNG_SIGNATURE)
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class TestReport(unittest.TestCase):
    def _snapshot(self) -> SysSnapshot:
        snapshot = SysSnapshot()
        snapshot.add(Section("printers", "Printers and cutters",
                             body="HP Latex 360 on 192.168.1.42"))
        snapshot.add(Section("tasks", "Scheduled tasks",
                             error="Access is denied."))
        return snapshot

    def test_report_contains_the_collected_detail(self):
        html = report.build_html(self._snapshot(), computer="SHOP-FRONT")
        self.assertIn("SHOP-FRONT", html)
        self.assertIn("Printers and cutters", html)
        self.assertIn("HP Latex 360 on 192.168.1.42", html)
        self.assertTrue(html.lstrip().startswith("<!doctype html>"))

    def test_a_section_that_failed_says_so_rather_than_vanishing(self):
        html = report.build_html(self._snapshot())
        self.assertIn("Scheduled tasks", html)
        self.assertIn("Access is denied.", html)

    def test_the_password_warning_only_appears_when_there_are_passwords(self):
        plain = report.build_html(self._snapshot())
        self.assertNotIn("contains passwords", plain)

        secret = self._snapshot()
        secret.add(Section("wifi", "Wi-Fi", body="hunter2", sensitive=True))
        loud = report.build_html(secret)
        self.assertIn("contains passwords", loud)
        self.assertIn("CONTAINS SECRETS", loud)

    def test_content_is_escaped_so_a_machine_name_cannot_break_the_page(self):
        snapshot = SysSnapshot()
        snapshot.add(Section("odd", "Odd", body="<script>alert(1)</script>"))
        html = report.build_html(snapshot, computer="<b>PC</b>")
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;b&gt;PC&lt;/b&gt;", html)

    def test_screenshots_are_referenced_relative_to_the_backup(self):
        snapshot = SysSnapshot()
        snapshot.screenshots = [os.path.join("any", "where", "desktop-all.png")]
        html = report.build_html(snapshot)
        self.assertIn("SystemSnapshot/Screenshots/desktop-all.png", html)


class FakeProbes:
    """Stands in for the real probes while testing the collector.

    Without this the suite would run a genuine eighteen-probe system inventory
    on every Windows machine it is run on -- minutes of PowerShell per test,
    and results that differ from one PC to the next. What is being tested here
    is the collector's handling of probes, not the probes themselves.
    """

    def __init__(self, output: str = "some output", error: str = "") -> None:
        self.output = output
        self.error = error
        self.calls: list[str] = []
        self._patches: list = []

    def __enter__(self) -> "FakeProbes":
        from unittest import mock

        def fake_shell(script, timeout=0):
            self.calls.append(script)
            return self.output, self.error

        def fake_run(command, timeout=0):
            self.calls.append(" ".join(command))
            return self.output, self.error

        probes = [sysinfo.Probe("printers", "Printers and cutters", "noop"),
                  sysinfo.Probe("wifi_probe", "Something secret", "noop",
                                sensitive=True)]
        self._patches = [
            mock.patch.object(sysinfo, "PROBES", probes),
            mock.patch.object(sysinfo, "_powershell", fake_shell),
            mock.patch.object(sysinfo, "_run", fake_run),
            mock.patch.object(sysinfo.appdetect, "detect",
                              lambda: sysinfo.appdetect.Detection()),
        ]
        for patch in self._patches:
            patch.start()
        return self

    def __exit__(self, *_exc) -> None:
        for patch in self._patches:
            patch.stop()


class TestSysinfo(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.mkdtemp(prefix="fenixvault-snap-")

    def tearDown(self) -> None:
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_collect_gathers_every_probe(self):
        with FakeProbes() as fake:
            snapshot = sysinfo.collect(self.folder, include_screenshots=False)
        self.assertTrue(fake.calls)
        self.assertIsNotNone(snapshot.section("printers"))
        self.assertIsNone(snapshot.section("nothing-like-this"))
        for section in snapshot.sections:
            self.assertTrue(section.title)

    def test_a_probe_that_fails_is_recorded_not_raised(self):
        with FakeProbes(output="", error="Access is denied."):
            snapshot = sysinfo.collect(self.folder, include_screenshots=False)
        printers = snapshot.section("printers")
        self.assertIsNotNone(printers)
        self.assertEqual(printers.error, "Access is denied.")
        self.assertFalse(printers.ok)
        self.assertTrue(snapshot.failed)

    def test_collecting_is_stopped_by_the_cancel_flag(self):
        import threading as _threading
        cancel = _threading.Event()
        cancel.set()
        with FakeProbes() as fake:
            sysinfo.collect(self.folder, include_screenshots=False,
                            cancel=cancel)
        self.assertEqual(fake.calls, [],
                         "a cancelled snapshot should not run any probe")

    def test_progress_is_reported(self):
        seen: list[str] = []
        with FakeProbes():
            sysinfo.collect(self.folder, include_screenshots=False,
                            progress=seen.append)
        self.assertTrue(seen)

    def test_the_real_probe_table_is_sane(self):
        # The probes themselves are not run here, but they should at least be
        # well-formed and unique.
        keys = [probe.key for probe in sysinfo.PROBES]
        self.assertEqual(len(keys), len(set(keys)), "duplicate probe key")
        for probe in sysinfo.PROBES:
            self.assertTrue(probe.title and probe.script)
            self.assertGreater(probe.timeout, 0)
        self.assertIn("bitlocker", keys)
        self.assertIn("printers", keys)

    def test_an_empty_section_is_not_counted_as_a_secret(self):
        snapshot = SysSnapshot()
        snapshot.add(Section("wifi", "Wi-Fi", error="no wireless card",
                             sensitive=True))
        self.assertFalse(snapshot.holds_secrets)
        snapshot.add(Section("key", "Key", body="ABC-123", sensitive=True))
        self.assertTrue(snapshot.holds_secrets)


class TestSnapshotInsideABackup(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tempfile.mkdtemp(prefix="fenixvault-test-")
        self.source = os.path.join(self.root, "PC", "Art")
        os.makedirs(self.source)
        with open(os.path.join(self.source, "logo.ai"), "w",
                  encoding="utf-8") as handle:
            handle.write("artwork")
        self.selection = FolderSelection()
        self.selection.set(os.path.join(self.root, "PC"), True)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _backup(self, probe_error: str = "", **kwargs) -> tuple[str, object]:
        backup_dir = os.path.join(self.root, "USB", "Backup")
        # Stubbed probes: a backup test must not depend on what this particular
        # machine happens to have installed, nor spend minutes finding out.
        with FakeProbes(output="" if probe_error else "ok", error=probe_error):
            result = run_backup(self.selection, ExcludeRules(),
                                catalog.default_extensions(), backup_dir,
                                BackupOptions(snapshot_screenshots=False,
                                              **kwargs))
        return backup_dir, result

    def test_the_report_is_written_beside_the_files(self):
        backup_dir, result = self._backup(capture_snapshot=True)
        self.assertTrue(os.path.isfile(
            os.path.join(backup_dir, report.REPORT_FILENAME)))
        self.assertTrue(os.path.isdir(
            os.path.join(backup_dir, "SystemSnapshot")))
        self.assertTrue(result.snapshot_report)
        self.assertTrue(manifest.read_info(backup_dir).has_snapshot)

    def test_the_snapshot_can_be_turned_off(self):
        backup_dir, result = self._backup(capture_snapshot=False)
        self.assertFalse(os.path.exists(
            os.path.join(backup_dir, report.REPORT_FILENAME)))
        self.assertIsNone(result.snapshot_report)
        self.assertFalse(manifest.read_info(backup_dir).has_snapshot)

    def test_files_are_still_copied_when_every_probe_fails(self):
        _backup_dir, result = self._backup(capture_snapshot=True,
                                           probe_error="Access is denied.")
        self.assertEqual(result.files_copied, 1)
        self.assertTrue(result.ok)
        self.assertEqual(result.files_failed, 0)

    def test_a_failed_probe_is_not_reported_as_a_skipped_file(self):
        # backup-report.txt is about files that did not get copied. Listing
        # "this PC has no BitLocker" there would send someone hunting for data
        # loss that never happened.
        _backup_dir, result = self._backup(capture_snapshot=True,
                                           probe_error="Access is denied.")
        self.assertGreater(result.snapshot_failed_sections, 0)
        self.assertNotIn("Access is denied.", " ".join(result.errors))
        self.assertIsNone(result.report_path)


if __name__ == "__main__":
    unittest.main()
