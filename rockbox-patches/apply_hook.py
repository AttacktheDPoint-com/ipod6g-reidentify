"""Install syscfgtool into a Rockbox checkout.

Usage: python3 apply_hook.py <rockbox-root> [--dryrun]

Copies syscfgtool.c, syscfgvalid.c and syscfgvalid.h (next to this script) into
bootloader/. Writes bootloader/syscfgtool_config.h (SYSCFGTOOL_DRYRUN if --dryrun),
adds the sources to bootloader/SOURCES for IPOD_6G, and hooks syscfgtool_run()
into bootloader/ipod-s5l87xx.c. All anchors are validated before anything is written.
"""
import argparse
import sys
from pathlib import Path

FILES = ("syscfgtool.c", "syscfgvalid.c", "syscfgvalid.h")
GUARD = "#if defined(IPOD_6G) && defined(HAVE_BOOTLOADER_USB_MODE)"
MAIN_ANCHOR = '    printf("Loading Rockbox...");\n    unsigned char *loadbuffer'
INC_ANCHOR = '#include "norboot-target.h"\n'
SRC_ANCHOR = "#elif defined(IPOD_6G) || defined(IPOD_NANO3G) || defined(IPOD_NANO4G)\nipod-s5l87xx.c\n"

HOOK = GUARD + '''
    /* syscfgtool: NOR dump / guarded SysCFG flash on request. Results land on the
     * disk; boot then continues into Rockbox, whose own USB mode exposes them.
     * (The bootloader USB mode never enumerated on Windows, so it is not used.) */
    syscfgtool_run();
#endif

'''
DECL = "\n" + GUARD + "\nbool syscfgtool_run(void);\n#endif\n"
SRC_LINES = "#if defined(IPOD_6G)\nsyscfgtool.c\nsyscfgvalid.c\n#endif\n"


def fail(msg):
    sys.exit(f"apply_hook: {msg}; nothing written")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--dryrun", action="store_true")
    a = ap.parse_args()  # unknown/misspelled options exit before anything is written
    dryrun = a.dryrun
    root = Path(a.root)
    here = Path(__file__).resolve().parent
    bl = root / "bootloader"
    main_c = bl / "ipod-s5l87xx.c"
    sources = bl / "SOURCES"

    copies = {}
    for name in FILES:
        data = (here / name).read_bytes()
        dst = bl / name
        if dst.exists() and dst.read_bytes() != data:
            fail(f"{dst} exists and differs (restore the checkout first)")
        copies[dst] = data
    config = ("#define SYSCFGTOOL_DRYRUN 1\n" if dryrun else "/* real build: NOR write enabled */\n").encode()

    t = main_c.read_text()
    if "syscfgtool_" in t and "syscfgtool_run" not in t:
        fail("checkout has an older syscfgtool hook; git checkout bootloader/ first")
    if "syscfgtool_run" not in t:
        if t.count(MAIN_ANCHOR) != 1:
            fail("main() anchor not found exactly once")
        if INC_ANCHOR not in t:
            fail("include anchor not found")
        t = t.replace(MAIN_ANCHOR, HOOK + MAIN_ANCHOR).replace(INC_ANCHOR, INC_ANCHOR + DECL, 1)

    u = sources.read_text()
    if "syscfgtool.c" in u and "syscfgvalid.c" not in u:
        fail("SOURCES has an older syscfgtool entry; git checkout bootloader/ first")
    if "syscfgtool.c" not in u:
        if SRC_ANCHOR not in u:
            fail("SOURCES anchor not found")
        u = u.replace(SRC_ANCHOR, SRC_ANCHOR + SRC_LINES, 1)

    # all validated: write
    for dst, data in copies.items():
        dst.write_bytes(data)
    (bl / "syscfgtool_config.h").write_bytes(config)
    main_c.write_text(t)
    sources.write_text(u)
    print(f"syscfgtool installed ({'DRYRUN' if dryrun else 'REAL'} build)")


if __name__ == "__main__":
    main()
