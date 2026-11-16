# iPod Classic 6G → 2.0.2 re-identify (for large flash mods)

An iPod Classic **6th gen** (2007, 80/160GB) tops out at firmware 1.1.2, which can't address flash mods larger than 128GB. Firmware **2.0.2** can. This project changes the iPod's factory identity (**SysCFG**, stored at offset 0 of its NOR flash) to a 7th-gen identity so iTunes will install 2.0.2. It then installs Rockbox dual-boot.

It automates [Olsro's manual method](https://github.com/Olsro/reddit-ipod-guides/blob/main/guides/ipod6g-flash-more-recent-firmwares.md). The new SysCFG is byte-identical to his SysCFG Editor v1.2 preset. The tool adds:

- **A guided, resumable console tool** (`run_guide.bat`). Plug in one iPod and follow the boxes. You can stop and re-run at any point, because it works out which stage the iPod is at.
- **A guarded NOR writer.** This is a small Rockbox bootloader addition (`syscfgtool`). It refuses to write unless the request's CRC matches what's currently in NOR, it only changes the fields the preset changes, the serial stem/HwId/MLBN are unchanged and the rest of sector 0 is blank. It then writes, verifies, retries, and restores the old sector if verification fails.
- **A rebuilt `mks5lboot.exe` that accepts 2.0.2.** The dual-boot installer shipped with Rockbox and Rockbox Utility predates 2.0.2. On a 2.0.2 iPod it plays one low tone and writes nothing, so the iPod keeps booting Apple's firmware.

> **Risk.** This writes to your iPod's NOR flash. The tool backs up the original SysCFG and the full NOR before writing, and DFU mode is in ROM, so a failed bootloader send can't brick the iPod. Still, you use this at your own risk. **Keep the `originals/` folder the tool creates.** Each iPod's Firmware ID is unique, and nothing else can restore it.

Tested end to end on one 6G (80GB board with a 500GB flash mod): re-identified, restored to 2.0.2 by iTunes with the full 500GB visible, and Rockbox dual-boot installed. A second unit was re-identified by hand with Olsro's method. The full guided flow hasn't yet been run start to finish on a fresh unit; reports are welcome.

## You need (Windows)

| What | Where | Put it |
|---|---|---|
| Python 3 | python.org | on PATH |
| iTunes **12.10.11.2** (provides the DFU driver) | [Apple: iTunes64Setup.exe](https://secure-appldnld.apple.com/itunes12/001-80053-20210422-E8A3B28C-A3B2-11EB-BE07-CE1B67FC6302/iTunes64Setup.exe) | install it |
| Firmware `iPod_35.2.0.2.ipsw` | [Apple](https://secure-appldnld.apple.com/iPod/SBML/osx/bundles/061-6797.20090909.3uTfE/iPod_35.2.0.2.ipsw) | this folder |
| Olsro's Rockbox build `ipodclassic6g-rockbox-full-with-flashtools.zip` | [Olsro's guide repo](https://github.com/Olsro/reddit-ipod-guides/raw/main/guides/ipod6g-flash-more-recent-firmwares/ipodclassic6g-rockbox-full-with-flashtools.zip) | this folder |

Everything else is in this repo: `vendor/mks5lboot-202/mks5lboot.exe`, the official Rockbox bootloader, and the `syscfgtool` bootloaders in `build/`.

## Run it

Double-click **`run_guide.bat`** (or `python tools\ipod6g_guide.py`). Each run is logged to `logs/`.

1. **Prepare:** copies Rockbox and a dump request to the iPod, then installs the syscfgtool bootloader over DFU.
2. **Dump:** on reboot, the bootloader reads SysCFG and the full NOR to the iPod's disk.
3. **Back up and stage:** the full NOR dump is copied to `originals/` on the PC. The new identity is staged on the iPod with a CRC request.
4. **Flash:** on reboot, the bootloader runs its checks, writes NOR sector 0, verifies it and beeps.
5. **Verify:** the PC checks the log and the read-back.
6. **iTunes restore to 2.0.2 (manual).** The order matters: DFU → let iTunes download what it wants → wait for the iPod to come back → **Shift+Restore** and pick `iPod_35.2.0.2.ipsw`. Shift+Restore from normal mode says "not compatible".
7. **Final:** re-adds Rockbox, writes `ORIGINAL SYSCFG - DO NOT DELETE/` to the iPod's disk, and installs the Rockbox dual-boot bootloader.

Options: `--bootloader syscfgtool` leaves the syscfgtool bootloader installed (it keeps the dump/revert path; the default is the official Rockbox bootloader). `--serial <serial>` skips the serial prompt.

**DFU mode:** hold SELECT + MENU about 12 seconds until the screen stays black. Close iTunes **and** iTunesHelper (Task Manager) before a bootloader install.

**Beeps after a bootloader install:** two beeps = installed. **One low tone = refused, nothing written.**

## Must-knows

- **Never update to 2.0.4 or 2.0.5.** Stay on 2.0.2.
- **Don't use Rockbox Utility to install the bootloader on a re-identified iPod.** Its installer doesn't know 2.0.2, so it plays one low tone, writes nothing, and the iPod keeps booting Apple's firmware. Use the guide, or run this from DFU mode:
  ```
  vendor\mks5lboot-202\mks5lboot.exe --bl-inst vendor\ipodpatcher\bootloader-ipod6g.ipod
  ```
- **An iTunes restore removes the Rockbox bootloader** (it rewrites NOR). Reinstall it afterwards.
- **Dual-boot:** hold MENU while it boots to get Apple 2.0.2. Otherwise it boots Rockbox.
- Windows gives the 192MB firmware partition a drive letter and offers to format it. **Never format it.**
- NOR can't be cloned between units. The NOR boot and flsh files are encrypted per device, so the iTunes restore stays in the flow.

## Repo layout

- `tools/syscfg6g.py`: SysCFG parse/patch/backup/revert, plus `stage`/`verify` for the bootloader flow. Run `python tools/syscfg6g.py -h`.
- `tools/ipod6g_guide.py`: the guide. `tools/add_rockbox.py`: copies Rockbox and installs the bootloader.
- `rockbox-patches/`: the `syscfgtool` bootloader addition (`apply_hook.py` installs it into a Rockbox checkout). `syscfgvalid.c` holds the pure validation logic and is host-tested.
- `build/`: prebuilt bootloaders. `-real` has the write path. `-dryrun` and `-dryrun-RAM.dfu` contain no write code (run them with `mks5lboot --dfusend` for a read-only NOR dump with nothing installed).
- `vendor/`: `mks5lboot-202` and the official Rockbox 6G bootloader (see `vendor/README.md`).
- `fixtures/`: synthetic, anonymized SysCFG/NOR images for the tests.
- `docs/spec-automation.md`: design, safety contract and the development lab log. `BUILDING.md`: how to rebuild the binaries.

## Tests

```
cd tools && python -m unittest test_syscfg6g        # 19 tests
python rockbox-patches/test/gen_fixtures.py <newdir> # C validator fixtures; build/run per the header of test_syscfgvalid.c
```

## Credits and license

- **Olsro**: the manual method, the SysCFG Editor and its 7G preset values, and the Rockbox build with flash tools.
- **The Rockbox project**: the bootloader, `mks5lboot` and the dual-boot installer.

GPLv2 (see `LICENSE`), the same as Rockbox, which the bootloader patches and binaries derive from. Not affiliated with Apple.
