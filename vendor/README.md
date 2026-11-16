# vendor/

| File | What | sha256 |
|---|---|---|
| `mks5lboot-202/mks5lboot.exe` | Rockbox `utils/mks5lboot` (commit `3f9b8fc`), cross-built with mingw-w64, **with the dual-boot installer blob rebuilt from source** so that it accepts firmware 2.0.2. No libusb; it uses the Apple DFU driver that iTunes installs. | `94659f8156f098c67089ce5646e1782566d4b8143d48dcef8d3a09bd00198fcd` |
| `mks5lboot-202/dualboot-generated.c` | The regenerated blob compiled into the exe above. | `33d6c4573bdc9cd3f35c27024b4431c4ca8fcd01e88aa3dab40d90ea7ba083ac` |
| `ipodpatcher/bootloader-ipod6g.ipod` | Official Rockbox 6G bootloader, unmodified, from download.rockbox.org/bootloader/ipod/. | `d5a18e56b46ec8a509471720ffe0900328f60ab3dd9d5d7d0c38fe74ff712176` |

Why the rebuild matters: the dual-boot installer in stock `mks5lboot` and Rockbox Utility checks the iPod's NOR boot against a table of known Apple firmwares. That table predates 2.0.2 (decrypted sign `9C84ADA4…`, which *is* in the current source table). On a 2.0.2 iPod the stock installer plays one low tone and writes nothing. The rebuilt one installs with two beeps. It was hardware-verified on a re-identified unit running 2.0.2.

Both are GPLv2 (Rockbox). Source: https://git.rockbox.org/cgit/rockbox.git (`utils/mks5lboot`, `bootloader/`). See `../BUILDING.md`.
