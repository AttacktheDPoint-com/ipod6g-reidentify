"""Re-add Rockbox to an iPod Classic 6G after an iTunes restore.

  python tools/add_rockbox.py --serial AB1234CD9ZU                 # official bootloader
  python tools/add_rockbox.py --serial AB1234CD9ZU --bootloader syscfgtool
  python tools/add_rockbox.py --skip-copy                          # disk already prepared

1. Finds the iPod's FAT32 volume (by disk FriendlyName), copies .rockbox/ from
   Olsro's zip and verifies every file. Refuses if .rockbox already exists.
   Writes the unit's ORIGINAL SysCFG (from originals/, matched by serial) plus a
   warning README to "ORIGINAL SYSCFG - DO NOT DELETE/" on the drive.
2. Asks you to eject and enter DFU, waits for the DFU device.
3. Installs the bootloader with mks5lboot --bl-inst.
"""
import argparse
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import syscfg6g  # noqa: E402

PROJ = Path(__file__).resolve().parent.parent
ZIP = PROJ / "ipodclassic6g-rockbox-full-with-flashtools.zip"
MKS5L = PROJ / "vendor" / "mks5lboot-202" / "mks5lboot.exe"  # dualboot blob rebuilt: knows 2.0.2 (vendor/README.md)
BOOTLOADERS = {
    "official": PROJ / "vendor" / "ipodpatcher" / "bootloader-ipod6g.ipod",
    "syscfgtool": PROJ / "build" / "bl6g-syscfgtool-real.ipod",
}


def ps(cmd: str) -> str:
    return subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                          capture_output=True, text=True).stdout.strip()


def find_ipod_volume():
    out = ps("Get-Disk | ? FriendlyName -like '*iPod*' | % { Get-Partition -DiskNumber $_.Number } "
             "| ? DriveLetter | ? { (Get-Volume -Partition $_).FileSystem -eq 'FAT32' } | % { $_.DriveLetter }")
    letters = [l.strip() for l in out.splitlines() if l.strip()]
    if len(letters) != 1:
        return None, letters
    return Path(f"{letters[0]}:/"), letters


def _rockbox_members(z):
    members = [m for m in z.infolist() if m.filename.startswith(".rockbox/")]
    if not members:
        sys.exit(f"{ZIP} has no .rockbox/ entries")
    for m in members:
        parts = m.filename.split("/")
        if ("\\" in m.filename or ":" in m.filename or m.filename.startswith("/")
                or any(p in ("..", ".") for p in parts[1:])):
            sys.exit(f"unsafe path in {ZIP.name}: {m.filename!r}")
    return members


def rockbox_mismatches(root: Path, prefix_dir: str = ".rockbox") -> list:
    """Files under root/prefix_dir that are missing or differ from the zip's .rockbox/."""
    bad = []
    with zipfile.ZipFile(ZIP) as z:
        for m in _rockbox_members(z):
            if m.is_dir():
                continue
            p = root / prefix_dir / m.filename[len(".rockbox/"):]
            if not p.is_file() or p.stat().st_size != m.file_size or p.read_bytes() != z.read(m):
                bad.append(m.filename)
    return bad


def ensure_rockbox(drive: Path):
    """Make sure drive/.rockbox matches the zip. Copies via a staging dir + rename; never overwrites."""
    dest = drive / ".rockbox"
    if dest.exists():
        bad = rockbox_mismatches(drive)
        if bad:
            sys.exit(f"{dest} exists but {len(bad)} files are missing/different (e.g. {bad[:2]}), "
                     "probably an interrupted copy. Rename or move that folder aside yourself, then re-run.")
        print(f"{dest} already present and verified against the zip")
        return
    stage = drive / ".rockbox.partial"
    if stage.exists():
        sys.exit(f"{stage} exists from an interrupted copy; rename or move it aside yourself, then re-run.")
    with zipfile.ZipFile(ZIP) as z:
        members = _rockbox_members(z)
        stage.mkdir()
        for m in members:
            rel = m.filename[len(".rockbox/"):]
            if not rel:
                continue
            out = stage / rel
            if m.is_dir():
                out.mkdir(parents=True, exist_ok=True)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(m) as src, open(out, "xb") as dst:
                dst.write(src.read())
                dst.flush()
                os.fsync(dst.fileno())
    bad = rockbox_mismatches(drive, ".rockbox.partial")
    if bad:
        sys.exit(f"verify FAILED for {len(bad)} files in {stage}, e.g. {bad[:3]}")
    stage.rename(dest)
    print(f"copied and verified {sum(not m.is_dir() for m in members)} files -> {dest}")


def copy_rockbox(drive: Path):
    """Fresh copy only (kept for the CLI): refuse if .rockbox exists."""
    if (drive / ".rockbox").exists():
        sys.exit(f"{drive / '.rockbox'} already exists; use --skip-copy, or move it aside yourself first")
    ensure_rockbox(drive)


ORIG_DIR = "ORIGINAL SYSCFG - DO NOT DELETE"
README = """ORIGINAL SYSCFG FOR THIS iPOD -- DO NOT DELETE, DO NOT LOSE THIS FILE
=====================================================================

This iPod's factory identity (SysCFG, stored in its NOR flash) was changed so it
can run iPod firmware 2.0.2 and use large storage. The file 'syscfg' in this
folder is the ORIGINAL, unmodified SysCFG.

  Original serial : {serial}
  Original model  : {model}
  Modified to     : 7th-gen identity, firmware 2.0.2

DO NOT UPDATE TO 2.0.4 (or 2.0.5). Stay on 2.0.2.

DO NOT LOSE THIS FILE. Without it the iPod cannot be returned to its original
identity (the Firmware ID is unique per unit; generic values will not match).
Keep a copy somewhere other than this iPod: an iTunes restore erases this disk.

To revert: boot Olsro's Rockbox build, copy this 'syscfg' to the root of the
iPod, then System > Debug (Keep Out!) > Flash SysCfg (from file to NOR), on a
wall charger. Then DFU + iTunes restore 1.1.2 (6G) / 2.0.1 (6.5G).
"""


def write_original(drive: Path, serial: str):
    src = syscfg6g.find_backup(serial)
    cfg = syscfg6g.load(src)
    if not syscfg6g.is_original(cfg):
        sys.exit(f"{src} is not an original identity; refusing")
    d = drive / ORIG_DIR
    d.mkdir(exist_ok=True)
    data = bytes(cfg.data)
    model = (cfg.model() or ("unknown",))[0]
    for name, content in (("syscfg", data),
                          ("README.txt", README.format(serial=cfg.serial, model=model).encode())):
        p = d / name
        if p.exists():
            if p.read_bytes() == content:
                continue
            sys.exit(f"{p} exists and differs; not overwriting")
        syscfg6g.write_new(p, content)
        if p.read_bytes() != content:
            sys.exit(f"verify failed: {p}")
    print(f"original SysCFG ({cfg.serial}, from {src.name}) -> {d}")


def itunes_running():
    out = subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower()
    return [p for p in ("itunes.exe", "ituneshelper.exe") if p in out]


def wait_dfu(timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = subprocess.run([str(MKS5L), "--dfuscan"], capture_output=True, text=True)
        if "DFU device state" in r.stdout + r.stderr:
            return True
        time.sleep(1)
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bootloader", choices=sorted(BOOTLOADERS), default="official")
    ap.add_argument("--skip-copy", action="store_true")
    ap.add_argument("--serial", help="this unit's serial (original or patched); required unless --skip-copy")
    a = ap.parse_args()
    if not a.skip_copy and not a.serial:
        ap.error("--serial is required so the original SysCFG can be written to the drive")
    bl = BOOTLOADERS[a.bootloader]
    for f in (MKS5L, bl) + (() if a.skip_copy else (ZIP,)):
        if not f.exists():
            sys.exit(f"missing {f}")

    if not a.skip_copy:
        drive, letters = find_ipod_volume()
        if drive is None:
            sys.exit(f"need exactly one mounted iPod volume, found {letters or 'none'} "
                     "(iTunes: enable disk use, or run with --skip-copy)")
        print(f"iPod volume: {drive}")
        write_original(drive, a.serial)
        copy_rockbox(drive)
        input("\nEject the iPod safely in Windows, then press Enter... ")

    running = itunes_running()
    if running:
        print(f"WARNING: {', '.join(running)} running; close them or the DFU install may fail.")
    print("Put the iPod in DFU: hold SELECT+MENU ~12 s until the screen stays black. Waiting...")
    if not wait_dfu():
        sys.exit("no DFU device within 180 s")
    print(f"DFU found. Installing {a.bootloader} bootloader ({bl.name})...")
    r = subprocess.run([str(MKS5L), "--bl-inst", str(bl)], capture_output=True, text=True)
    output = (r.stdout + r.stderr).strip()
    if output:
        print(output.splitlines()[-1])
    if r.returncode != 0 or "sent successfully" not in output:
        sys.exit(f"bootloader send failed (exit code {r.returncode})")
    print("Listen: dual beep = installed, then it boots Rockbox. Single low tone = failed (device unchanged).")


if __name__ == "__main__":
    main()
