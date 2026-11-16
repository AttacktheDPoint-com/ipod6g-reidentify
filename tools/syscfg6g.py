"""iPod Classic 6G SysCFG tool: decode, back up, patch to 2.0.2-2.0.4 compatible, revert.

Reproduces the "Turn into 2.0.2-2.0.4 compatible iPod" preset of Olsro's
iPod SysCFG Editor v1.2. See docs/spec-automation.md.
"""
import argparse
import re
import datetime
import os
import shutil
import struct
import sys
import zlib
from pathlib import Path

SIZE = 0xCC
HEADER = 0x18
ENTRY = 20
MAGIC = b"gfCS"
REQUIRED_TAGS = {"SrNm", "FwId", "HwId", "HwVr", "Codc", "SwVr", "MLBN", "Mod#", "Regn"}

ORIGINALS = Path(__file__).resolve().parent.parent / "originals"

# serial suffix -> (model, model number, color), from iPodModelsBySNEndingModelNumber
MODELS = {
    "YMV": ("Classic 6th Gen (Black, 80GB)", "MB147", "black"),
    "Y5N": ("Classic 6th Gen (White, 80GB)", "MB029", "white"),
    "YMX": ("Classic 6th Gen (Black, 160GB)", "MB150", "black"),
    "YMU": ("Classic 6th Gen (White, 160GB)", "MB145", "white"),
    "2C7": ("Classic 6.5th Gen (Black, 120GB)", "MB565", "black"),
    "2C5": ("Classic 6.5th Gen (White, 120GB)", "MB562", "white"),
    "9ZU": ("Classic 7th Gen (Black, 160GB)", "MC297", "black"),
    "9ZS": ("Classic 7th Gen (White, 160GB)", "MC293", "white"),
}
SEVENTH_GEN = {"black": ("9ZU", "MC297"), "white": ("9ZS", "MC293")}

# Preset values as displayed by the editor (little-endian 32-bit words).
PRESET_FWID_WORD = "21414D71"
PRESET_HWVR = "130200"
PRESET_SWVR = "2.0.2"
PRESET_REGN = "00020001 00210020"


class SysCfg:
    def __init__(self, data: bytes):
        if len(data) != SIZE or data[:4] != MAGIC:
            raise ValueError(f"not a 6G SysCFG dump (len={len(data)}, magic={data[:4]!r})")
        if struct.unpack_from("<I", data, 4)[0] != SIZE:
            raise ValueError("unexpected SysCFG header size")
        count = struct.unpack_from("<I", data, 0x14)[0]
        if HEADER + count * ENTRY != SIZE:
            raise ValueError(f"unexpected entry count {count}")
        self.data = bytearray(data)
        self.offsets = {}
        for i in range(count):
            off = HEADER + i * ENTRY
            tag = data[off:off + 4][::-1].decode("ascii")
            if tag in self.offsets:
                raise ValueError(f"duplicate tag {tag}")
            self.offsets[tag] = off + 4
        missing = REQUIRED_TAGS - self.offsets.keys()
        if missing:
            raise ValueError(f"missing fields {sorted(missing)}")
        if not re.fullmatch(r"[A-Z0-9]{8,12}", self.serial):
            raise ValueError(f"implausible serial {self.serial!r}")

    def raw(self, tag) -> bytes:
        off = self.offsets[tag]
        return bytes(self.data[off:off + 16])

    def set_raw(self, tag, value: bytes):
        if len(value) != 16:
            raise ValueError("SysCFG values must be exactly 16 bytes")
        off = self.offsets[tag]
        self.data[off:off + 16] = value

    def text(self, tag) -> str:
        return self.raw(tag).split(b"\0", 1)[0].decode("ascii")

    def set_text(self, tag, s: str):
        b = s.encode("ascii")
        if len(b) > 15:
            raise ValueError(f"{tag} too long: {s}")
        self.set_raw(tag, b.ljust(16, b"\0"))

    def words(self, tag, n) -> list:
        return [f"{w:08X}" for w in struct.unpack_from(f"<{n}I", self.raw(tag))]

    def set_words(self, tag, words: list):
        raw = bytearray(self.raw(tag))
        struct.pack_into(f"<{len(words)}I", raw, 0, *(int(w, 16) for w in words))
        self.set_raw(tag, bytes(raw))

    @property
    def serial(self):
        return self.text("SrNm")

    def model(self):
        return MODELS.get(self.serial[-3:])

    def summary(self) -> dict:
        hwvr = int(self.words("HwVr", 2)[1], 16)
        return {
            "Serial number": self.serial,
            "Model": (self.model() or ("Unknown",))[0],
            "Firmware ID": " ".join(self.words("FwId", 3)),
            "Hardware version": f"{hwvr:X}",
            "Software version": self.text("SwVr"),
            "Model number": self.text("Mod#"),
            "Sales region": " ".join(self.words("Regn", 2)),
            "Logic board SN": self.text("MLBN"),
        }


def is_original(cfg: SysCfg) -> bool:
    """A known 6G/6.5G identity that has not been patched."""
    return (cfg.model() is not None
            and cfg.serial[-3:] not in ("9ZU", "9ZS")
            and cfg.words("FwId", 3)[1] != PRESET_FWID_WORD)


def patch(cfg: SysCfg) -> SysCfg:
    if not is_original(cfg):
        raise ValueError(f"not an unpatched 6G/6.5G identity (serial {cfg.serial}); refusing to patch")
    model = cfg.model()
    suffix, modnum = SEVENTH_GEN[model[2]]
    out = SysCfg(bytes(cfg.data))
    out.set_text("SrNm", cfg.serial[:-3] + suffix)
    fwid = out.words("FwId", 3)
    fwid[1] = PRESET_FWID_WORD
    out.set_words("FwId", fwid)
    hw = out.words("HwVr", 2)
    hw[1] = f"{int(PRESET_HWVR, 16):08X}"
    out.set_words("HwVr", hw)
    out.set_text("SwVr", PRESET_SWVR)
    out.set_text("Mod#", modnum + out.text("Mod#")[5:])
    out.set_words("Regn", PRESET_REGN.split())
    return out


def load(path) -> SysCfg:
    """Load a 204-byte SysCFG, or the SysCFG at the start of a 32KB NOR dump."""
    data = Path(path).read_bytes()
    if len(data) == 0x8000:
        data = data[:SIZE]
    return SysCfg(data)


def write_new(path: Path, data: bytes):
    """Write a file, refusing to overwrite."""
    with open(path, "xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def backup(cfg: SysCfg, dest_dir: Path = None) -> Path:
    dest_dir = dest_dir or ORIGINALS
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = dest_dir / f"{cfg.serial}_{stamp}"
    write_new(path, bytes(cfg.data))
    if path.read_bytes() != bytes(cfg.data):
        raise IOError(f"backup verify failed: {path}")
    return path


def find_backup(serial_prefix: str, dest_dir: Path = None) -> Path:
    """Earliest unpatched backup whose serial matches except the 3-char model suffix (changed by patch)."""
    if not re.fullmatch(r"[A-Z0-9]{8,12}", serial_prefix):
        raise ValueError(f"implausible serial {serial_prefix!r}")
    dest_dir = dest_dir or ORIGINALS
    candidates = []
    for p in sorted(dest_dir.iterdir()):
        try:
            c = load(p)
        except (ValueError, OSError):
            continue
        if c.serial[:-3] == serial_prefix[:-3] and is_original(c):
            candidates.append(p)
    if not candidates:
        raise FileNotFoundError(f"no original backup for serial {serial_prefix}")
    return min(candidates, key=lambda p: p.stat().st_mtime)


def print_summary(cfg: SysCfg, title=None):
    if title:
        print(f"== {title}")
    for k, v in cfg.summary().items():
        print(f"  {k:18} {v}")


def cmd_info(a):
    for f in a.files:
        print_summary(load(f), f)


def cmd_backup(a):
    print(f"backed up -> {backup(load(a.file))}")


def cmd_patch(a):
    out = patch(load(a.file))
    write_new(Path(a.output), bytes(out.data))
    print_summary(out, f"patched -> {a.output}")


def cmd_auto(a):
    src = Path(a.drive) / "syscfg"
    cfg = load(src)
    print_summary(cfg, f"dump {src}")
    patched = patch(cfg)  # validate before touching anything
    print(f"backed up -> {backup(cfg)}")
    archive = src.with_name(f"syscfg.dump-{datetime.datetime.now():%Y%m%d-%H%M%S}")
    write_new(archive, bytes(cfg.data))
    tmp = src.with_name("syscfg.new")
    write_new(tmp, bytes(patched.data))
    if archive.read_bytes() != bytes(cfg.data) or tmp.read_bytes() != bytes(patched.data):
        raise IOError("staging verify failed; syscfg left untouched")
    os.replace(tmp, src)
    if load(src).data != patched.data:
        raise IOError("write verify failed")
    print_summary(patched, f"patched -> {src}")
    print("\nNext: safely eject the iPod and wait until Windows says it is safe, then unplug, wall charger, Rockbox -> System -> Debug -> Flash SysCfg (from file to NOR).")


def cmd_revert(a):
    p = find_backup(a.serial)
    cfg = load(p)
    write_new(Path(a.output), bytes(cfg.data))
    print_summary(cfg, f"original {p} -> {a.output}")


# --- syscfgtool bootloader flow (docs/spec-automation.md, "Write stage spec") ---

NOR_DUMP_SIZE = 0x8000
SECTOR = 0x1000


def _stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _tool_dir(drive) -> Path:
    return Path(drive) / "syscfgtool"


def _read_nor(path: Path) -> bytes:
    nor = path.read_bytes()
    if len(nor) != NOR_DUMP_SIZE:
        raise ValueError(f"{path} is {len(nor)} bytes, expected {NOR_DUMP_SIZE}")
    return nor


def _backup_bytes(data: bytes, name: str, dest_dir: Path = None) -> Path:
    dest_dir = dest_dir or ORIGINALS
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / name
    write_new(path, data)
    if path.read_bytes() != data:
        raise IOError(f"backup verify failed: {path}")
    return path


def _set_aside(path: Path, suffix: str):
    """Rename an existing file out of the way (never delete)."""
    if path.exists():
        path.rename(path.with_name(f"{path.name}.{suffix}-{_stamp()}"))


def stage(drive, revert_from: Path = None) -> Path:
    d = _tool_dir(drive)
    if (d / "flash.req").exists():
        raise ValueError(f"{d / 'flash.req'} already exists; a request is pending")
    nor = _read_nor(d / "nor.bin")
    if any(b != 0xFF for b in nor[0xCC:SECTOR]):
        raise ValueError("nor.bin sector 0 tail is not blank; bootloader would refuse")
    cur = SysCfg(nor[:SIZE])
    if revert_from:
        target = load(revert_from)
        if target.serial[:-3] != cur.serial[:-3]:
            raise ValueError(f"revert source serial {target.serial} is not this unit ({cur.serial})")
    else:
        target = patch(cur)
    bk = _backup_bytes(nor, f"{cur.serial}_{_stamp()}_nor.bin")
    print(f"NOR backed up -> {bk}")

    src = d / "syscfg.flash"
    _set_aside(src, "old")
    write_new(src, bytes(target.data))
    req = f"{zlib.crc32(bytes(cur.data)):08X} {zlib.crc32(bytes(target.data)):08X}\n".encode()
    tmp = d / "flash.req.tmp"
    write_new(tmp, req)
    if src.read_bytes() != bytes(target.data) or tmp.read_bytes() != req:
        raise IOError("staging verify failed")
    os.replace(tmp, d / "flash.req")
    _set_aside(d / "dump.req", "done")
    print_summary(cur, "current NOR")
    print_summary(target, "staged target")
    return d / "flash.req"


def verify(drive) -> bool:
    d = _tool_dir(drive)
    log = (d / "flash.log").read_text(errors="replace").strip().splitlines() if (d / "flash.log").exists() else []
    last = [l for l in log if l.split(" ", 1)[0] in ("WRITTEN", "NOOP", "REFUSE", "FAILED", "DRYRUN")]
    print("flash.log:", *(f"  {l}" for l in log[-6:]), sep="\n")
    after = _read_nor(d / "nor-after.bin")
    target = (d / "syscfg.flash").read_bytes()
    result = last[-1].split(" ", 1)[0] if last else "NONE"
    tail_blank = all(b == 0xFF for b in after[0xCC:SECTOR])
    matches = after[:SIZE] == target
    print(f"result={result} nor-after==target={matches} tail_blank={tail_blank}")
    cfg = SysCfg(after[:SIZE])
    print_summary(cfg, "NOR now")
    if result in ("WRITTEN", "NOOP") and matches and tail_blank:
        bk = _backup_bytes(after, f"{cfg.serial}_{_stamp()}_nor-after.bin")
        print(f"NOR-after backed up -> {bk}")
        _set_aside(d / "nor.bin", "before")
        write_new(d / "nor.bin", after)
        print("nor.bin promoted from nor-after.bin. Next: DFU -> iTunes Shift+Restore 2.0.2" if not is_original(cfg)
              else "nor.bin promoted. NOR holds an original identity.")
        return True
    print("NOT verified; nothing promoted.")
    return False


def cmd_stage(a):
    stage(a.drive, Path(a.revert) if a.revert else None)
    print("\nNext: safely eject, unplug, (wall/USB power), reboot. Bootloader flashes, beeps, offers USB; then run verify.")


def cmd_verify(a):
    if not verify(a.drive):
        sys.exit(1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(required=True)
    s = sub.add_parser("info"); s.add_argument("files", nargs="+"); s.set_defaults(fn=cmd_info)
    s = sub.add_parser("backup"); s.add_argument("file"); s.set_defaults(fn=cmd_backup)
    s = sub.add_parser("patch"); s.add_argument("file"); s.add_argument("-o", "--output", required=True); s.set_defaults(fn=cmd_patch)
    s = sub.add_parser("auto", help="iPod drive root, e.g. E:/"); s.add_argument("drive"); s.set_defaults(fn=cmd_auto)
    s = sub.add_parser("revert"); s.add_argument("serial"); s.add_argument("-o", "--output", required=True); s.set_defaults(fn=cmd_revert)
    s = sub.add_parser("stage", help="stage a guarded bootloader flash from DRIVE/syscfgtool/nor.bin"); s.add_argument("drive"); s.add_argument("--revert", help="original SysCFG file to restore instead of patching"); s.set_defaults(fn=cmd_stage)
    s = sub.add_parser("verify", help="check a bootloader flash result"); s.add_argument("drive"); s.set_defaults(fn=cmd_verify)
    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except (ValueError, OSError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
