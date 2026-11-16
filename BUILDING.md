# Rebuilding the binaries

All binaries were built on Linux from Rockbox commit `3f9b8fc`, with arm-none-eabi gcc 8.3 (symlinked as `arm-elf-eabi-*` on PATH) and mingw-w64 for the Windows tool.

## syscfgtool bootloader (`build/bl6g-syscfgtool-*.ipod`)

```
git clone https://git.rockbox.org/cgit/rockbox.git && cd rockbox && git checkout 3f9b8fc
python3 /path/to/rockbox-patches/apply_hook.py .            # add --dryrun for the no-write build
mkdir build-bl6g && cd build-bl6g
../tools/configure --target=ipod6g --type=b                  # standard Rockbox bootloader configure
make
```

Before re-applying the hook, run `git checkout -- bootloader/`.

Check every build. The real build must contain exactly one `bootflash_write` symbol, and the dry-run build must contain none:

```
arm-elf-eabi-nm bootloader.elf | grep -c bootflash_write
```

RAM-run image for read-only dumps (nothing is installed): `mks5lboot --mkdfu-raw bootloader.bin out.dfu`, then send it from DFU with `mks5lboot --dfusend out.dfu`.

## mks5lboot-202 (`vendor/mks5lboot-202/mks5lboot.exe`)

The same `utils/mks5lboot` from Rockbox, but with its embedded dual-boot installer (`dualboot.c`) regenerated from source. The checked-in blob at `3f9b8fc` was stale: its OF table only covered 1.1.2, 2.0.1, 2.0.4 and 2.0.5.

```
cd utils/mks5lboot/dualboot
make CONFIGDIR_ipod6g=<path-to-rockbox>/firmware/export CONFIGDIR_ipodnano3g=<path-to-rockbox>/firmware/export   # regenerates ../dualboot.c
cd .. && make CROSS=x86_64-w64-mingw32-
```

The regenerated `dualboot.c` used for the shipped exe is kept as `vendor/mks5lboot-202/dualboot-generated.c`.

## Host tests for the validator

```
python rockbox-patches/test/gen_fixtures.py fx > cases.txt
cd rockbox-patches/test && cc -std=c99 -Wall -Wextra -I.. test_syscfgvalid.c ../syscfgvalid.c -o t && ./t ../../fx $(cat ../../cases.txt)
```
