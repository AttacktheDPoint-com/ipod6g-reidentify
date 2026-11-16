import tempfile
import zlib
import unittest
from pathlib import Path

import syscfg6g as s

ORIG = Path(__file__).resolve().parent.parent / "fixtures"  # synthetic, anonymized SysCFGs (fixtures/README.md)
DEFAULT_ORIGINALS = s.ORIGINALS


class PatchTests(unittest.TestCase):
    def test_matches_gui_preset(self):
        out = s.patch(s.load(ORIG / "syscfg_2original"))
        self.assertEqual(bytes(out.data), (ORIG / "syscfg_2").read_bytes())

    def test_patch_unit1_black_7g(self):
        out = s.patch(s.load(ORIG / "syscfg_1"))
        self.assertEqual(out.serial[-3:], "9ZU")
        self.assertEqual(out.text("Mod#"), "MC297")
        self.assertEqual(out.text("MLBN"), s.load(ORIG / "syscfg_1").text("MLBN"))
        self.assertEqual(s.SysCfg(bytes(out.data)).summary()["Hardware version"], "130200")

    def test_refuses_double_patch(self):
        with self.assertRaises(ValueError):
            s.patch(s.load(ORIG / "syscfg_2"))

    def test_refuses_garbage(self):
        with self.assertRaises(ValueError):
            s.SysCfg(b"\0" * s.SIZE)

    def test_refuses_missing_field(self):
        data = bytearray((ORIG / "syscfg_1").read_bytes())
        i = data.index(b"mNrS")
        data[i:i + 4] = b"XXXX"
        with self.assertRaises(ValueError):
            s.SysCfg(bytes(data))

    def test_refuses_path_serial(self):
        data = bytearray((ORIG / "syscfg_1").read_bytes())
        i = data.index(b"mNrS") + 4
        data[i:i + 16] = b"..\\escapeYMV".ljust(16, b"\0")
        with self.assertRaises(ValueError):
            s.SysCfg(bytes(data))

    def test_backup_search_skips_patched_fwid(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            bad = s.load(ORIG / "syscfg_2original")
            fw = bad.words("FwId", 3); fw[1] = s.PRESET_FWID_WORD; bad.set_words("FwId", fw)
            (d / "a_bad").write_bytes(bytes(bad.data))
            (d / "b_good").write_bytes((ORIG / "syscfg_2original").read_bytes())
            self.assertEqual(s.find_backup("AB1234CD9ZU", d).name, "b_good")

    def test_refuses_bad_header_size(self):
        data = bytearray((ORIG / "syscfg_1").read_bytes())
        data[4:8] = bytes(4)
        with self.assertRaises(ValueError):
            s.SysCfg(bytes(data))

    def test_backup_search_uses_full_serial_stem(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            def with_serial(serial):
                c = s.load(ORIG / "syscfg_2original")
                c.set_text("SrNm", serial)
                return bytes(c.data)
            (d / "a_other").write_bytes(with_serial("ABCDEFGHAYMV"))
            (d / "b_mine").write_bytes(with_serial("ABCDEFGHBYMV"))
            self.assertEqual(s.find_backup("ABCDEFGHB9ZU", d).name, "b_mine")

    def test_refuses_missing_hwid(self):
        data = bytearray((ORIG / "syscfg_1").read_bytes())
        i = data.index(b"dIwH")
        data[i:i + 4] = b"XXXX"
        with self.assertRaises(ValueError):
            s.SysCfg(bytes(data))

    def test_load_accepts_32k_dump(self):
        self.assertEqual(bytes(s.load(DUMP).data), (ORIG / "syscfg_2original").read_bytes())

    def test_display_matches_editor(self):
        sm = s.load(ORIG / "syscfg_2").summary()
        self.assertEqual(sm["Firmware ID"].split()[1], "21414D71")
        self.assertEqual(sm["Sales region"], "00020001 00210020")


class BackupTests(unittest.TestCase):
    def test_backup_auto_and_revert(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            drive, store = d / "ipod", d / "orig"
            drive.mkdir()
            original = (ORIG / "syscfg_2original").read_bytes()
            (drive / "syscfg").write_bytes(original)
            s.ORIGINALS = store
            try:
                s.cmd_auto(type("A", (), {"drive": str(drive)}))
                self.assertEqual((drive / "syscfg").read_bytes(), (ORIG / "syscfg_2").read_bytes())
                backups = list(store.iterdir())
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_bytes(), original)
                self.assertEqual(len(list(drive.glob("syscfg.dump-*"))), 1)
                # revert by the patched serial finds the original
                found = s.find_backup(s.load(drive / "syscfg").serial, store)
                self.assertEqual(found.read_bytes(), original)
                # second auto on patched file refuses and leaves drive untouched
                with self.assertRaises(ValueError):
                    s.cmd_auto(type("A", (), {"drive": str(drive)}))
                self.assertEqual(len(list(store.iterdir())), 1)
            finally:
                s.ORIGINALS = DEFAULT_ORIGINALS


DUMP = ORIG / "nor0-32k.bin"


class StageVerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.drive, self.store = root / "ipod", root / "orig"
        (self.drive / "syscfgtool").mkdir(parents=True)
        self.nor = DUMP.read_bytes()
        (self.drive / "syscfgtool" / "nor.bin").write_bytes(self.nor)
        (self.drive / "syscfgtool" / "dump.req").write_bytes(b"")
        s.ORIGINALS = self.store

    def tearDown(self):
        s.ORIGINALS = DEFAULT_ORIGINALS
        self.tmp.cleanup()

    def _device_writes(self, result="WRITTEN"):
        d = self.drive / "syscfgtool"
        target = (d / "syscfg.flash").read_bytes()
        after = target + self.nor[len(target):]
        (d / "nor-after.bin").write_bytes(after)
        (d / "flash.log").write_text(f"flash requested\n{result} verified\n")
        (d / "flash.req").rename(d / "flash.done")

    def test_stage_patch_then_verify(self):
        d = self.drive / "syscfgtool"
        s.stage(self.drive)
        cur, new = (d / "flash.req").read_text().split()
        self.assertEqual(int(cur, 16), zlib.crc32(self.nor[:s.SIZE]))
        target = (d / "syscfg.flash").read_bytes()
        self.assertEqual(target, (ORIG / "syscfg_2").read_bytes())
        self.assertEqual(int(new, 16), zlib.crc32(target))
        self.assertFalse((d / "dump.req").exists())
        self.assertEqual(len(list(self.store.glob("*_nor.bin"))), 1)
        self._device_writes()
        self.assertTrue(s.verify(self.drive))
        self.assertEqual((d / "nor.bin").read_bytes()[:s.SIZE], target)
        self.assertEqual(len(list(d.glob("nor.bin.before-*"))), 1)

    def test_stage_refuses_pending(self):
        s.stage(self.drive)
        with self.assertRaises(ValueError):
            s.stage(self.drive)

    def test_revert_refuses_other_unit(self):
        with self.assertRaises(ValueError):
            s.stage(self.drive, revert_from=ORIG / "syscfg_1")

    def test_patch_then_revert_roundtrip(self):
        d = self.drive / "syscfgtool"
        s.stage(self.drive)
        self._device_writes()
        self.assertTrue(s.verify(self.drive))
        s.stage(self.drive, revert_from=ORIG / "syscfg_2original")
        cur, _ = (d / "flash.req").read_text().split()
        self.assertEqual(int(cur, 16), zlib.crc32((ORIG / "syscfg_2").read_bytes()))
        self.assertEqual((d / "syscfg.flash").read_bytes(), (ORIG / "syscfg_2original").read_bytes())

    def test_revert_from_stage_backup(self):
        s.stage(self.drive)
        self._device_writes()
        self.assertTrue(s.verify(self.drive))
        bk = next(self.store.glob("*_nor.bin"))
        s.stage(self.drive, revert_from=bk)
        d = self.drive / "syscfgtool"
        self.assertEqual((d / "syscfg.flash").read_bytes(), (ORIG / "syscfg_2original").read_bytes())

    def test_verify_fails_on_refuse(self):
        s.stage(self.drive)
        d = self.drive / "syscfgtool"
        (d / "nor-after.bin").write_bytes(self.nor)
        (d / "flash.log").write_text("REFUSE power\n")
        self.assertFalse(s.verify(self.drive))
        self.assertFalse(list(d.glob("nor.bin.before-*")))


if __name__ == "__main__":
    unittest.main()
