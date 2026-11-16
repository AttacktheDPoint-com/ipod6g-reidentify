# Spec: iPod 6G re-identify automation



Design notes and lab log, kept as written during development. Paths under `originals/` and `dumps/` refer to private per-device files that are not in this repo; the tests use the synthetic copies in `fixtures/`.



## Goal



Per iPod, the only manual actions are: put it in DFU mode, then Shift+Restore with `iPod_35.2.0.2.ipsw` in iTunes. Everything else is scripted or runs unattended on the device.



## Current flow (manual)



1. Install the Rockbox bootloader with Rockbox Utility. This needs an existing Apple firmware partition, so a blank disk needs an iTunes 1.1.2 restore first.

2. Copy `.rockbox/` (Olsro's build with the flash tools) to the iPod.

3. On the iPod: Debug â†’ dump SysCFG (NOR â†’ file `syscfg` on disk).

4. On the PC: back up the dump, then apply the editor preset and save as `syscfg` on the iPod.

5. On the iPod, on a wall charger: Debug â†’ flash SysCFG (file â†’ NOR).

6. Enter DFU mode, then Shift+Restore 2.0.2 in iTunes. iTunes repartitions and reformats the disk at whatever size it is.



## Target flow



| # | Where | What | Step |

|---|---|---|---|

| A | PC | Write the golden disk image (MBR, firmware partition with the Rockbox bootloader, FAT32 containing `.rockbox/`), then grow FAT32 | 2 |

| B | iPod | Dump â†’ patch â†’ flash â†’ read back and verify, unattended | 3 |

| C | PC | `syscfg6g.py auto <drive>`: back up by serial, verify the patch | 1 |

| D | User | DFU, then iTunes Shift+Restore | â€” |



Until step 3 exists, B is manual: menu presses for the dump and the flash, with C in between.



## Step 1: `tools/syscfg6g.py`



A Python script that uses only the standard library.



### SysCFG format (verified against `originals/` and the editor jar)

- 204 bytes. The header is 0x18 bytes: magic `gfCS`, size, â€¦, entry count at 0x14 (= 9).

- Each entry is 20 bytes: a 4-byte tag stored reversed (`mNrS` = SrNm), then 16 bytes of data.

- Text fields (SrNm, SwVr, MLBN, Mod#) are NUL-padded ASCII.

- Numeric fields (FwId, HwVr, Regn) are shown in the editor as little-endian 32-bit words. For example, the editor shows `21414D71` and the stored bytes are `71 4D 41 21`.



### Preset "Turn into 2.0.2â€“2.0.4 compatible" (from `MainController.class`, editor v1.2)

- SrNm: the last 3 characters become the 7th-gen code of the same colour. Black â†’ `9ZU`, white â†’ `9ZS`.

- FwId: middle word â†’ `21414D71` (first and third words unchanged; shown as `01000000 â€¦ 000A2700`).

- HwVr: `130200`

- SwVr: `2.0.2`

- Mod#: the first 5 characters become `MC297` (black) or `MC293` (white).

- Regn: `00020001 00210020`



The colour comes from the serial suffix, using the editor's table: YMV/YMX/2C7 = black, Y5N/YMU/2C5 = white.



### Commands

- `info FILE`: decodes the file and prints the model.

- `backup FILE`: copies it to `originals/<serial>_<YYYYMMDD-HHMMSS>` and refuses to overwrite.

- `patch FILE -o OUT`: applies the preset. Refuses unknown models and already-patched input.

- `auto DRIVE`: reads `DRIVE/syscfg`, backs it up, patches it, and writes `DRIVE/syscfg`.

- `revert SERIAL -o OUT`: writes the earliest backup for that serial.



### Acceptance

- `patch originals/syscfg_2original` is byte-identical to `originals/syscfg_2`. That dump was produced by the GUI preset.

- `patch originals/syscfg_1` succeeds and decodes as a black 7G.

- Patching an already-patched file is refused.



## Step 2: bootloader + disk prep (revised 2026-10-19)



**The golden disk image idea is dropped.** On the 6G, the Rockbox bootloader lives in **NOR**, not on the disk. It's installed over **DFU** by `mks5lboot` (Rockbox `utils/mks5lboot`, the code Rockbox Utility uses). `ipodpatcher` has no 6G support: the 2010 prebuilt is v5.0, and current source has no 6G mentions. The dual bootloader survives disk swaps. An iTunes restore rewrites NOR, which removes it.



Revised per-iPod flow:

1. PC: partition the disk with MBR and one FAT32 partition of any size (a "winpod"), then copy `.rockbox/`. No Apple partition is needed to boot Rockbox (unverified for a fresh disk).

2. DFU, then `mks5lboot --bl-inst bootloader-ipod6g.ipod`. Scriptable. Needs a DFU driver (iTunes' driver works), and iTunesHelper must be stopped.

3. Rockbox: dump, then `syscfg6g.py auto`, then flash.

4. DFU, then iTunes Shift+Restore 2.0.2.



Tooling status:

- `vendor/ipodpatcher/`: the 2010 `ipodpatcher.exe`, which has no 6G support, and the official `bootloader-ipod6g.ipod` (sha256 `d5a18e56…`).

- `mks5lboot.exe`: cross-built on a Linux host (see `vendor/README.md`). **Verified 2026-10-19:** `--dfuscan` finds the iPod over Apple's driver (state 2), and `--bl-inst` installed the bootloader (dual beep, booted into Rockbox). Step 2 of the per-iPod flow is automated.

- FAT32 on large disks: Windows `format` stops at 32GB. Use `fat32format` (in `utils/ipodpatcher/fat32format.c`) or similar. The iPod reports **4096-byte logical sectors**.



Observed on disk 2 (500GB, iPod 1.1.2, before the bootloader install): MBR with partition 2 = firmware (LBA 63, 192MiB) and partition 1 = FAT32 (15.7GB at byte 201842688). The rest of the disk is unpartitioned.



## Step 3: unattended NOR flash (not started, high risk)



- **Option 0 (most promising):** `mks5lboot --mkdfu-raw` runs arbitrary code from DFU at 0x2200030c, and `dualboot.c` already contains NOR read/write code. A DFU payload could patch SysCFG directly, with no disk or Rockbox needed. The flow would become: DFU, run the payload, DFU again, iTunes.



- Option 1: freemyipod emCORE, which would read and write NOR from the PC over USB. Unverified.

- Option 2: rebuild Olsro's Rockbox with an autorun dump/patch/flash and a read-back check. Needs his source.

- Option 3: Rockbox reboots straight into DFU after the flash. Unverified.



### Code findings (2026-10-19, Rockbox `3f9b8fc`)

- NOR layout (`dualboot/dualboot.c`): **SysCFG at offset 0**, the encrypted Apple NOR boot at 32KB, Rockbox's dual-boot layout above that, and the `flsh` directory at 1MB-0x200.

- `norboot-s5l8702.c` has `bootflash_read/write/compare/erase`, `syscfg_read()` and the SysCFG structs and tags. The DFU installer already writes NOR with these and verifies via `bootflash_compare`.

- **Trap:** `bootflash_write()` erases the whole 4KB sector it touches, then writes only the requested range. Writing just the 204 SysCFG bytes would wipe whatever else is in 0x0CC–0xFFF, and those contents are unknown. Any SysCFG write must read the full 4KB sector, patch it, then write and verify it.

- A DFU payload has no channel back to the PC. It can't hand the original SysCFG to the PC for backup.

- The Rockbox bootloader has a USB mass-storage mode (`HAVE_BOOTLOADER_USB_MODE`) and a "Show SysCfg" menu.



### Hardware result: read-only dump (2026-10-19, iPod #2)

- The custom bootloader was installed over DFU (dual beep). The trigger caused a dump (second dual beep), and `nor.bin` was 32768 bytes. It's saved in `dumps/AB1234CD9ZU_nor0-32k_20261019.bin`.

- **NOR 0x0000–0x00CC is SysCFG, and 0x00CC–0x8000 is all 0xFF.** The rest of sector 0 is empty, so a full-sector rewrite only has to preserve the SysCFG bytes.

- NOR SysCFG is byte-identical to `originals/syscfg_2original`. **This unit was never actually flashed.** The patched `syscfg` on its disk was only staged. The backup `originals/AB1234CD9ZU_20261019-232256` is that staged patched file, not a NOR dump.

- **Bootloader USB mode did not mount on the PC.** The device rebooted and booted normally on unplug. This needs investigating; the multiplier and USB init timing are suspects.



### Design options

- **A. Custom Rockbox bootloader** (installed by `mks5lboot`, already proven): at boot it dumps NOR sector 0 to disk, then enters USB mass-storage mode. The PC runs `syscfg6g.py`, which backs up, patches and writes `syscfg.flash`. On eject, the bootloader patches and writes the 4KB sector, verifies it, beeps and reboots. User actions: DFU, wait, DFU, Restore. The PC keeps the backup. It can be built read-only first, as a dump-only version.

- **B. Pure DFU payload:** patches on the device, and the backup can only be kept in NOR spare space. There's no PC backup and no way to inspect the result first. Fewer user actions, but irreversible blind writes.



Any code that writes NOR must verify by reading back, and must refuse to run on battery.



### Write stage spec (option A, stage 2): DRAFT 2026-10-19, needs approval before hardware

**Contract:** the bootloader writes NOR sector 0 only when the PC has staged a request that is consistent with the NOR's *current* contents, and that the PC has backed up. Otherwise it refuses, without writing.

#### Files on the iPod's FAT volume (`/syscfgtool/`)
| File | Written by | Meaning |
|---|---|---|
| `dump.req` | PC | Request a dump (stage 1, existing) |
| `nor.bin` | bootloader | NOR 0–32KB at dump time (stage 1, existing) |
| `syscfg.flash` | PC | The new 204-byte SysCFG |
| `flash.req` | PC | One ASCII line: `<crc32 of current NOR SysCFG> <crc32 of syscfg.flash>`, 8 hex digits each |
| `flash.log` | bootloader | Result text, appended each attempt |
| `nor-after.bin` | bootloader | NOR 0–32KB re-read after the write |
| `flash.done` | bootloader | `flash.req` renamed after any attempt, success or failure, so it never re-runs |

#### PC: `syscfg6g.py stage DRIVE`
1. Read `nor.bin` and validate the SysCFG in its first 204 bytes.
2. Back it up to `originals/<serial>_<ts>_nor.bin` (full 32KB, never overwrites) and verify the copy.
3. Patch, as `patch()` does today, or use `--revert <backup>`.
4. Write `syscfg.flash` and `flash.req` (CRCs of the current SysCFG and the new one), and remove `dump.req` so the next boot doesn't re-dump. Removal means renaming it to `dump.done`.
5. Print: "eject; the iPod will flash on next boot".

`syscfg6g.py verify DRIVE` (after the flash): checks `flash.log`, confirms `nor-after.bin[:204] == syscfg.flash`, and confirms that bytes 204 to 4096 are 0xFF. It then backs up `nor-after.bin` to `originals/` and **promotes it to `nor.bin`**: the old `nor.bin` is renamed to `nor-before-<ts>.bin`. That way the next `stage` (for example a revert) uses the CRC of the current NOR.

#### Bootloader: `syscfgtool_flash()`, run after mount and before the dump check
It refuses (logs, plays the sad tone, renames `flash.req`, **no write**) unless every check passes:
1. `flash.req` and `syscfg.flash` exist, `syscfg.flash` is exactly 204 bytes, and `flash.req` parses.
2. **Power:** `power_input_status() != POWER_INPUT_NONE` (external power present) **and** `_battery_voltage() >= battery_level_disksafe + 200` mV. This is the margin the stock `battery_trap()` uses; `battery_level()` isn't usable because powermgmt isn't running in the bootloader at this point.
3. Read NOR sector 0 (4KB). Its SysCFG has a valid header (magic, size 0xCC, 9 entries), **and NOR bytes 204 to 4096 are all 0xFF**. That's true on the dumped unit; if anything else is ever found, refuse.
4. `crc32(NOR[0:204]) == flash.req.current`, which proves the PC staged this request against exactly this NOR (and therefore backed it up).
5. `crc32(syscfg.flash) == flash.req.new`, which proves the file arrived intact.
6. **Field allowlist:** `syscfg.flash` keeps the same 0x18-byte header, the same tag sequence, and identical HwId, Codc and MLBN entries. The first 8 characters of SrNm must match. Only the SrNm suffix, FwId, HwVr, SwVr, Mod# and Regn may differ. This covers both patch and revert, and blocks writing another unit's SysCFG or garbage.
7. If `syscfg.flash == NOR[0:204]`, it's already done: log a no-op and play the happy tone.

Then it writes:
- Build a 4KB buffer: `syscfg.flash` followed by 0xFF.
- `bootflash_write(0, buf, 0x1000)`, then `bootflash_compare`.
- If the compare fails, retry up to 2 more times. If it still fails, write the original sector back (from the 4KB read in check 3) and compare, then log `RESTORED` or `CORRUPT`.
- Re-read 0–32KB into `nor-after.bin`, log the result, rename `flash.req` to `flash.done`, and play the tone.
- Then enter USB mode, the same as the dump does.

**Tones:** happy = written and verified (or a no-op). Sad (single) = refused, nothing written. Fatal (triple) = write failed. If the restore succeeded, the original SysCFG is back. If not, see the manual recovery under Failure analysis.

#### Hardware result: dry run (2026-10-19, iPod #2)
- Staged patch (crc `1AA1A41C` → `5DB30597`), then installed `bl6g-syscfgtool-dryrun.ipod` over DFU. Dual beep both times.
- `flash.log`: `DRYRUN would write sector 0 (crc 1AA1A41C -> 5DB30597)`. The power check passed on USB power. `nor-after.bin` is byte-identical to the original dump, so NOR is unchanged. The request was retired to `flash.done`. Evidence is in `dumps/dryrun-20261019/`.
- Codex review round 2 fixes: `apply_hook` rejects misspelled flags (argparse); replaying an applied request gives NOOP; every tag must appear exactly once (C); HwId and Codc are required (Py); `load()` accepts 32KB backups for `--revert`. 17 C cases and 19 Py tests pass.

#### Hardware result: first real write (2026-10-19, iPod #2)
- Re-staged (crc `1AA1A41C` → `5DB30597`), then installed `bl6g-syscfgtool-real.ipod` (sha256 `1f8f475e…`). Dual beep twice.
- `flash.log`: `WRITTEN verified`. `verify` result: nor-after == target, tail blank. **NOR SysCFG is byte-identical to `originals/syscfg_2` (the GUI preset output).** Evidence is in `dumps/realwrite-20261019/`. The backup is `originals/AB1234CD9ZU_20261019-235753_nor-after.bin`.
- The disk later enumerated as "Apple iPod" at 137GB (2^28 sectors, the LBA28 cap) where it was 500GB before. Unexplained (C); see the bootloader `lba48` check.
- Remaining: iTunes Shift+Restore 2.0.2, which proves end to end.

#### Failure analysis
- **Power loss between erase and write:** sector 0 is left blank, so there's no SysCFG. **v1 has no automated recovery for this.** Normal validation rejects a blank or corrupt sector (no valid header), so this tool can't fix it. Recovery is manual: boot Rockbox (the bootloader is at 32KB, so it should still load; unverified), put the backup on the disk as `syscfg`, and use Olsro's System → Debug → Flash SysCfg (file to NOR), which does no validation. A dedicated blank-sector recovery branch, with its own backup selection and gating, can come later. The power check makes this case unlikely.
- **Wrong unit:** the CRC and serial checks refuse it.
- **Half-copied `syscfg.flash`:** the CRC check refuses it.
- **Request never renamed (rename fails):** the next boot sees NOR == target and does a no-op. It's idempotent.
- **Apple OF or iTunes behaviour:** this is unchanged from Olsro's flow. Only SysCFG changes.

#### Test ladder (each rung gated on the previous one)
1. **Host tests:** compile the validator (checks 3–7, with the I/O mocked) for the PC on a Linux host. Cover: good patch, good revert, wrong serial, changed MLBN, bad CRC, non-0xFF tail, no-op.
2. **Dry-run build** (`SYSCFGTOOL_DRYRUN`): does everything except `bootflash_write`, and logs what it would have written. Run on iPod #2.
3. **No-op on hardware:** stage `syscfg.flash` = the current NOR. This exercises the whole path with zero writes.
4. **First real write:** patch iPod #2, whose original is in `originals/syscfg_2original` and `dumps/`. Verify with `nor-after.bin`. Then do the iTunes 2.0.2 restore. That's the end-to-end proof.
5. **Revert test** (optional): stage the original back onto #2.

Prerequisite (independent): fix bootloader USB mode not mounting, otherwise `verify` needs a full Rockbox boot. That's acceptable meanwhile.

## Step 4: iTunes-free cloning (research, started 2026-10-20)

**Restore result:** iPod #2 restored to 2.0.2 through iTunes (DFU, then accept the download, wait, then Shift+Restore). The FAT32 volume is 500GB, so 2.0.2 sees the whole disk. A Shift+Restore from normal mode gives "firmware not compatible"; the DFU sequence is mandatory.

**Finding: the mks5lboot dual-boot installer refuses on 2.0.2** (single low tone, nothing written). Its OF table doesn't recognise the NOR boot that `iPod_35.2.0.2` installs. **So the guide's final "install Rockbox bootloader" stage currently fails on re-identified units.** **RESOLVED 2026-10-20:** the cause was a stale pre-built dual-boot blob in mks5lboot (its OF table only had 1.1.2, 2.0.1, 2.0.4 and 2.0.5). The decrypted sign read on-device (`9C84ADA4…`, `dumps/ipod2-202/norboot-id.txt`) **is** in the source table. Rebuilding the blob from source (`vendor/mks5lboot-202/`) fixed it: the official bootloader installed on iPod #2 at 2.0.2, with a dual beep, and it boots Rockbox. A fix needs the decrypted `data_sign` of this NOR boot added to `of_sha[]` in a custom mks5lboot build. That value can only be computed on the device (UKEY).

**Finding: RAM-run works on the 6G.** `mks5lboot --mkdfu-raw bootloader.bin` + `--dfusend` runs our bootloader from RAM with nothing installed. The dry-run image (`build/bl6g-syscfgtool-dryrun-RAM.dfu`) dumped NOR this way. This means dumps, and potentially the guarded flash, need **no bootloader install at all**.

**NOR map, iPod #2 on 2.0.2** (`dumps/ipod2-202/nor-full.bin`, sha256 `b17f9e52…`):
- 0x000000–0x001000: SysCFG (== `originals/syscfg_2`), with the rest 0xFF
- 0x008000–0x03E000: Apple NOR boot, IM3 (`8702` `1.0`), 216KB
- 0x042000–0x100000: flsh files (all ver 0x00015000) — disk 210KB, diag 172KB, appl 4KB, lbat 7KB, bdsw 12KB, bdhw 8KB, chrg 8KB; directory at 1MB-0x200

Next: the same full dump from iPod #1 (also 2.0.2). Any difference outside SysCFG is device-specific (UKEY-signed). Also capture the firmware partition from both disks as admin.

Windows assigns a drive letter to the 192MB firmware partition and offers to format it. **Never format it**; it holds the Apple OS.

### iPod #2 complete (2026-10-20)
Re-identified (syscfgtool real write), iTunes 2.0.2 restore (500GB visible), official Rockbox dual-boot via `mks5lboot-202`. Holding MENU boots Apple 2.0.2; anything else boots Rockbox. The disk has `ORIGINAL SYSCFG - DO NOT DELETE/` (syscfg == `originals/syscfg_2original`, README, INSTALL-COMPLETE.txt). Research leftovers in `syscfgtool/` remain on its disk.

### NOR comparison: iPod #1 vs #2, both on 2.0.2 (2026-10-20)
Dumps: `dumps/ipod1-202/`, `dumps/ipod2-202/` (RAM-run dry-run image, read-only).
- **Apple NOR boot (0x8000):** the **decrypted** sign is identical on both (`9C84ADA4…`, the same plaintext 2.0.2 bootloader). The stored bytes differ in about 218KB of 216KB+, i.e. essentially everything. **It is encrypted per device (UKEY).**
- **flsh files (disk, diag, appl, lbat, bdsw, bdhw, chrg):** directory entries are identical (same offsets, lengths, versions), but **all file data differs**. They are also per-device encrypted.
- **SysCFG:** 11 bytes differ (serial, FwId, MLBN …), as expected.
- **Conclusion:** NOR can't be cloned byte for byte. An iTunes-free NOR install would have to decrypt on the reference unit and re-encrypt/sign on each target with its own UKEY, which is what dualboot.c already does for the NOR boot (`im3_crypt`/`im3_sign`). The flsh files use a different header (keyidx/sha at 0x8/0x1c/0x1d4) and their crypto path is unexplored. The disk firmware partition is still uncompared; it needs an admin capture of both disks.

## Findings



- The FwId in the guide's revert table (`132A1448`) matches neither real 6G original: they hold `13038883` and `13156CEA`. FwId appears to vary per unit. **Revert using the unit's own backup, not the table.**

- The editor jar maps the white 80GB to `MB029`, the black 160GB to `MB150`, and the white 160GB to `MB145`. The guide uses `MB147` for every 6G.

