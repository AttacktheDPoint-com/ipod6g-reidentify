# fixtures/

These are synthetic test images, not real devices. They were made from real SysCFG dumps with every per-unit field replaced: the serial stem, Firmware ID word 1 and the logic-board serial (MLBN). Everything else (layout, HwId, Codc, model and region fields) is the stock 6G layout.

- `syscfg_2original`: "unit A" as shipped (6G, MB147, firmware 1.0 fields).
- `syscfg_2`: unit A after the SysCFG Editor v1.2 7G preset. `syscfg6g.patch(syscfg_2original)` reproduces it byte for byte.
- `syscfg_1`: "unit B", a different 6G, used for wrong-unit refusals.
- `nor0-32k.bin`: unit A's SysCFG followed by blank NOR (0xFF), the shape of a 32KB `nor.bin` dump.

Do not use these to restore a real iPod. Every iPod's Firmware ID is unique; use the backup the tool made of *your* unit.
