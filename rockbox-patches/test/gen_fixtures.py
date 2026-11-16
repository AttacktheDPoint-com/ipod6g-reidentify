"""Generate fixtures for test_syscfgvalid.c from the synthetic NOR dump in fixtures/. Usage: python gen_fixtures.py <outdir>

Prints the case names, one per line.
"""
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent.parent
sys.path.insert(0, str(PROJ / "tools"))
import syscfg6g as s  # noqa: E402

DUMP = PROJ / "fixtures" / "nor0-32k.bin"  # synthetic
OTHER = PROJ / "fixtures" / "syscfg_1"  # a different unit


def req(cur: bytes, new: bytes) -> bytes:
    return f"{zlib.crc32(cur):08X} {zlib.crc32(new):08X}\n".encode()


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True)  # refuses an existing dir; use a fresh path each run
    sector = DUMP.read_bytes()[:0x1000]
    cur = sector[:0xCC]
    patched = bytes(s.patch(s.SysCfg(cur)).data)
    other = s.patch(s.load(OTHER))

    cases = {}

    def case(name, expect, sec=sector, target=patched, request=None):
        cases[name] = (sec, target, request if request is not None else req(sec[:0xCC], target), expect)

    case("good_patch", "WRITE")
    case("noop_same", "NOOP", target=cur)
    # revert: NOR holds patched, target is original
    pat_sector = patched + sector[0xCC:]
    case("good_revert", "WRITE", sec=pat_sector, target=cur)
    case("stale_req", "REFUSE", request=req(patched, patched))
    case("bad_new_crc", "REFUSE", request=f"{zlib.crc32(cur):08X} DEADBEEF\n".encode())
    case("req_garbage", "REFUSE", request=b"hello world 12345")
    case("req_lowercase_ok", "WRITE", request=req(cur, patched).lower())
    case("wrong_unit", "REFUSE", target=bytes(other.data))
    t = s.SysCfg(patched); t.set_text("MLBN", "XXXXXXXXXXXX"); case("mlbn_changed", "REFUSE", target=bytes(t.data))
    t = s.SysCfg(patched); t.set_text("SrNm", "AB1234CE9ZU"); case("serial_stem_changed", "REFUSE", target=bytes(t.data))
    t = bytearray(patched); t[0x10] ^= 1; case("header_changed", "REFUSE", target=bytes(t))
    case("short_target", "REFUSE", target=patched[:200])
    dirty = bytearray(sector); dirty[0x800] = 0x00; case("tail_not_blank", "REFUSE", sec=bytes(dirty))
    blank = b"\xff" * 0x1000; case("blank_nor", "REFUSE", sec=blank, request=req(blank[:0xCC], patched))
    hwid = None
    t = bytearray(patched)
    c = s.SysCfg(patched); off = c.offsets["HwId"]; t[off] ^= 0xFF; case("hwid_changed", "REFUSE", target=bytes(t))

    # replay: NOR already holds B, request was A->B -> NOOP
    case("replay_after_success", "NOOP", sec=pat_sector, target=patched, request=req(cur, patched))
    # duplicated tag in NOR (Codc entry overwritten with a second HwId tag)
    dup = bytearray(sector); co = s.SysCfg(cur).offsets["Codc"] - 4; dup[co:co + 4] = b"dIwH"
    case("dup_tag", "REFUSE", sec=bytes(dup), request=req(bytes(dup[:0xCC]), patched))
    for name, (sec, target, request, expect) in cases.items():
        d = out / name
        d.mkdir()
        (d / "sector.bin").write_bytes(sec)
        (d / "target.bin").write_bytes(target)
        (d / "flash.req").write_bytes(request)
        (d / "expect.txt").write_text(expect)
        print(name)


if __name__ == "__main__":
    main()
