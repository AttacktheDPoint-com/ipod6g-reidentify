"""Guided iPod Classic 6G re-identify: original -> 2.0.2-compatible, with Rockbox re-added.

  python tools\\ipod6g_guide.py                 # detect where this iPod is and continue
  python tools\\ipod6g_guide.py --bootloader syscfgtool   # final Rockbox bootloader choice

Run it, follow the boxes. It can be stopped and re-run at any point: it works out
the current stage from the files on the iPod and from its USB identity.
Every NOR write is done by the syscfgtool bootloader, which re-checks everything
itself (docs/spec-automation.md). A log of each run goes to logs/.
"""
import argparse
import datetime
import subprocess
import sys
import textwrap
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import syscfg6g  # noqa: E402
import add_rockbox  # noqa: E402

PROJ = HERE.parent
TOOL_BL = add_rockbox.BOOTLOADERS["syscfgtool"]
IPSW = PROJ / "iPod_35.2.0.2.ipsw"
PATCHED_FWID = syscfg6g.PRESET_FWID_WORD  # appears in the iPod's USB serial once patched
LOG = PROJ / "logs" / f"guide-{datetime.datetime.now():%Y%m%d-%H%M%S}.log"
WIDTH = 72
DONE_MARK = "INSTALL-COMPLETE.txt"  # written only after a confirmed final bootloader install


# ---------------------------------------------------------------- output

def log(msg: str):
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%H:%M:%S} {msg}\n")


def say(msg: str):
    print(msg)
    log(msg)


def box(title: str, what: str = "", you_do=(), listen: str = ""):
    inner = WIDTH - 4
    lines = []
    for para in what.split("\n") if what else []:
        lines += textwrap.wrap(para, inner) or [""]
    if you_do:
        lines += ["", "YOU DO:"]
        for i, step in enumerate(you_do, 1):
            wrapped = textwrap.wrap(step, inner - 4)
            lines += [f" {i}. {wrapped[0]}"] + [f"    {w}" for w in wrapped[1:]]
    if listen:
        lines += [""] + textwrap.wrap(f"LISTEN FOR: {listen}", inner)
    bar = "+" + "-" * (WIDTH - 2) + "+"
    out = ["", bar, f"| {title[:inner]:<{inner}} |", bar] + [f"| {l:<{inner}} |" for l in lines] + [bar]
    print("\n".join(out))
    log(f"BOX {title}")


def ask_enter(prompt="Press Enter when done (Ctrl+C to stop)... "):
    input(prompt)


def ask_yes(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


# ---------------------------------------------------------------- device state

def usb_identity() -> str:
    """Apple iPod USB instance ids (normal mode). The serial part contains the FwId."""
    return add_rockbox.ps("Get-PnpDevice -PresentOnly | ? InstanceId -match 'VID_05AC&PID_12[0-9A-F]{2}\\\\' "
                          "| % { $_.InstanceId }")


def is_patched_usb() -> bool:
    return PATCHED_FWID in usb_identity().upper()


def wait_drive(what: str, timeout=600) -> Path:
    say(f"Waiting for the iPod drive to appear ({what})...")
    t0 = time.time()
    while time.time() - t0 < timeout:
        drive, letters = add_rockbox.find_ipod_volume()
        if drive:
            time.sleep(2)  # let Windows finish mounting
            say(f"iPod drive: {drive}")
            return drive
        if len(letters) > 1:
            sys.exit(f"more than one iPod volume mounted ({letters}); connect only one iPod")
        time.sleep(2)
    sys.exit("timed out waiting for the iPod drive")


def install_bootloader(path: Path, why: str):
    box(f"Install bootloader over DFU ({why})",
        "The bootloader goes into the iPod's NOR flash over DFU. DFU is in the chip's ROM, "
        "so this step cannot brick the iPod; a failed send leaves it unchanged.",
        ["Safely eject the iPod in Windows (wait for 'safe to remove').",
         "Keep it plugged in to USB.",
         "Close iTunes AND iTunesHelper (Task Manager) if they are running.",
         "Hold SELECT + MENU about 12 seconds until the screen stays black (DFU)."],
        "a double beep = installed (then it reboots). A single low tone = failed, nothing changed.")
    running = add_rockbox.itunes_running()
    if running:
        say(f"WARNING: still running: {', '.join(running)}. Close them now.")
    say("Waiting for DFU...")
    if not add_rockbox.wait_dfu(timeout=300):
        sys.exit("no DFU device within 5 minutes; re-run this tool to try again")
    r = subprocess.run([str(add_rockbox.MKS5L), "--bl-inst", str(path)], capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    log(out)
    if r.returncode != 0 or "sent successfully" not in out:
        sys.exit(f"bootloader send FAILED (exit {r.returncode}):\n{out[-400:]}")
    say(f"Bootloader sent ({path.name}).")


USB_NOTE = ("After the beeps the iPod carries straight on and boots Rockbox. Rockbox then shows "
            "up as a drive on the PC by itself; no unplugging needed.")


# ---------------------------------------------------------------- stages

def stage_prepare(drive: Path):
    """Fresh iPod (original identity): put Rockbox + dump trigger on the disk, install syscfgtool."""
    box("STAGE 1 of 6: Prepare the iPod",
        "This iPod still has its original identity. The tool copies Rockbox onto the disk (needed "
        "so it can boot after each step) and asks the bootloader to read the iPod's identity (SysCFG) "
        "from NOR on the next boot. Nothing is written to NOR in this stage.")
    add_rockbox.ensure_rockbox(drive)
    d = drive / "syscfgtool"
    d.mkdir(exist_ok=True)
    if not (d / "dump.req").exists():
        syscfg6g.write_new(d / "dump.req", b"")
    say("Dump requested.")
    install_bootloader(TOOL_BL, "syscfgtool")
    box("STAGE 2 of 6: iPod reads its identity",
        "After the install beep the iPod reboots, reads NOR and saves it to the disk.\n" + USB_NOTE,
        ["Wait for the second double beep (dump saved).",
         "Wait for Rockbox to start; it appears as a drive."],
        "two double beeps in total.")


def stage_stage(drive: Path):
    d = drive / "syscfgtool"
    cur = syscfg6g.load(d / "nor.bin")
    box("STAGE 3 of 6: Back up and prepare the new identity",
        f"NOR was read. Current identity: {cur.serial} ({(cur.model() or ('unknown',))[0]}). "
        "The tool backs up the full NOR dump to originals/ on this PC, then writes the new identity "
        "and a checksummed request to the iPod. The bootloader will refuse it if anything doesn't match.")
    if not ask_yes("Back up and stage the 2.0.2-compatible identity now?"):
        sys.exit("stopped by you; nothing written")
    syscfg6g.stage(drive)
    box("STAGE 4 of 6: Flash the new identity",
        "On the next boot the bootloader checks power, checks the request against NOR, writes the "
        "identity, reads it back to verify, and saves the result.\n" + USB_NOTE,
        ["Safely eject the iPod in Windows.",
         "Keep it on USB power (it refuses to flash without external power).",
         "Reboot it: hold SELECT + MENU until the Apple logo / screen goes off, then let go.",
         "Wait for the double beep after the reboot.",
         "Wait for Rockbox to start; it appears as a drive."],
        "double beep = written and verified. One low tone = refused (nothing written; the log says why). "
        "Three low tones = write failed; see flash.log.")


def stage_verify(drive: Path) -> bool:
    box("STAGE 5 of 6: Check the result",
        "Reading the bootloader's log and its fresh NOR read-back.")
    ok = syscfg6g.verify(drive)
    if not ok:
        box("NOT VERIFIED", "The flash did not complete. NOR backups are in originals/. "
            "Read the flash.log lines above. If it says REFUSE power: charge or plug in, then re-run this "
            "tool (it re-stages). Do not continue to the iTunes restore.")
    return ok


def stage_itunes():
    if not IPSW.exists():
        say(f"WARNING: {IPSW.name} not found in the project folder.")
    box("STAGE 6 of 6: iTunes restore to 2.0.2",
        "The iPod now has its new identity, but still runs its old firmware. iTunes installs 2.0.2. "
        "Do it in exactly this order, or iTunes says 'firmware file not compatible'.",
        ["Open iTunes (12.10.11.2). Eject the iPod in iTunes, keep it plugged in.",
         "Put it in DFU: hold SELECT + MENU through the reboot, release after ~8 s, screen stays black.",
         "iTunes offers to download a restore image: ACCEPT. Do not Shift+Restore yet.",
         "Wait until the iPod disappears and comes back in iTunes.",
         f"NOW hold Shift and click Restore, pick {IPSW.name}.",
         "Wait for the restore to finish and the iPod to reboot to the Apple menu.",
         "In iTunes, tick 'Enable disk use' (Summary page) and Apply, so Windows sees the drive."],
        "nothing special; iTunes shows progress. The Rockbox bootloader is removed by this restore.")
    ask_enter("Press Enter when the restore has finished and the iPod shows as a drive... ")


def stage_finish(drive: Path, serial_hint: str, bootloader: str):
    box("FINAL: Re-add Rockbox and the original identity file",
        "Copies Rockbox and a folder 'ORIGINAL SYSCFG - DO NOT DELETE' (this iPod's original identity "
        "plus a README: do not update to 2.0.4, do not lose this file). Then installs the "
        f"{bootloader} Rockbox bootloader over DFU.")
    serial = serial_hint or input("This iPod's serial (Settings > About, or the back case): ").strip().upper()
    add_rockbox.write_original(drive, serial)
    add_rockbox.ensure_rockbox(drive)
    install_bootloader(add_rockbox.BOOTLOADERS[bootloader], f"{bootloader}, final")
    if not ask_yes("Did you hear the double beep, and does it boot into Rockbox?"):
        sys.exit("Not marked done. Re-run this tool to retry the bootloader install.")
    box("Mark complete", "", ["Plug the iPod back in so its drive appears (Rockbox USB)."])
    drive = wait_drive("to record completion")
    syscfg6g.write_new(drive / add_rockbox.ORIG_DIR / DONE_MARK,
                       f"bootloader {bootloader} installed {datetime.datetime.now():%Y-%m-%d %H:%M}\n".encode())
    box("DONE",
        "This iPod now runs 2.0.2 with a 7th-gen identity, Rockbox dual-boot, and its original "
        "SysCFG on the disk.\nHold MENU at power-on for the Apple firmware; anything else boots Rockbox.",
        ["Do NOT update it to 2.0.4 in iTunes.",
         "Keep originals/ on this PC; it is the only off-device copy of the original identity."])


# ---------------------------------------------------------------- driver

def detect(drive: Path):
    d = drive / "syscfgtool"
    if (drive / add_rockbox.ORIG_DIR / DONE_MARK).exists():
        return "done"
    if not d.exists():
        ids = usb_identity()
        if not ids:
            return "ask_identity"
        return "finish" if PATCHED_FWID in ids.upper() else "prepare"
    if (d / "flash.req").exists():
        return "await_flash"
    if (d / "flash.done").exists() and (d / "nor-after.bin").exists():
        nor, after = d / "nor.bin", d / "nor-after.bin"
        if nor.exists() and nor.read_bytes() == after.read_bytes() and not syscfg6g.is_original(syscfg6g.load(nor)):
            return "itunes"
        return "verify"
    if (d / "nor.bin").exists():
        return "stage"
    return "await_dump"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bootloader", choices=sorted(add_rockbox.BOOTLOADERS), default="official",
                    help="Rockbox bootloader to leave installed at the end (default: official)")
    ap.add_argument("--serial", help="this iPod's serial, used at the final step (asked if omitted)")
    a = ap.parse_args()
    for f in (add_rockbox.MKS5L, TOOL_BL, add_rockbox.ZIP, add_rockbox.BOOTLOADERS[a.bootloader]):
        if not f.exists():
            sys.exit(f"missing {f}")
    say(f"iPod 6G guide. Log: {LOG}")
    box("START",
        "Connect ONE iPod by USB. It should show up as a drive (Rockbox running, or iTunes disk mode).",
        ["Plug the iPod in and wait for its drive to appear."])

    while True:
        drive = wait_drive("connect the iPod")
        state = detect(drive)
        say(f"Detected stage: {state}")
        if state == "prepare":
            stage_prepare(drive)
        elif state == "await_dump":
            box("Waiting for the dump",
                "A dump was requested but no nor.bin yet: the syscfgtool bootloader has not run.",
                ["If you just installed it: let it reboot and wait for Rockbox.",
                 "Otherwise the bootloader may be missing; the tool will reinstall it now."])
            req = drive / "syscfgtool" / "dump.req"
            if not req.exists():  # interrupted prepare: dir exists but the request was never written
                syscfg6g.write_new(req, b"")
                say("dump.req was missing; recreated.")
            if ask_yes("Reinstall the syscfgtool bootloader now?"):
                install_bootloader(TOOL_BL, "syscfgtool")
        elif state == "stage":
            stage_stage(drive)
        elif state == "await_flash":
            box("Waiting for the flash",
                "A flash request is staged but has not run yet.",
                ["Safely eject, keep on USB power, reboot (hold SELECT+MENU), wait for the double beep,",
                 "then wait for Rockbox to start; it appears as a drive."])
        elif state == "verify":
            if not stage_verify(drive):
                return
            continue
        elif state == "itunes":
            stage_itunes()
        elif state == "finish":
            stage_finish(drive, a.serial, a.bootloader)
            return
        elif state == "ask_identity":
            box("Which state is this iPod in?",
                "The tool could not read the iPod's USB identity, so it cannot tell a fresh iPod from "
                "one that has already been changed and restored.")
            if ask_yes("Has this iPod ALREADY been changed and restored to 2.0.2?"):
                stage_finish(drive, a.serial, a.bootloader)
                return
            if ask_yes("Is it a fresh iPod with its ORIGINAL identity, to start from the beginning?"):
                stage_prepare(drive)
            else:
                return
        elif state == "done":
            box("Already done", "This iPod already has Rockbox and its original SysCFG folder.")
            return
        ask_enter("\nWhen the iPod is back as a drive, press Enter to continue... ")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped. Re-run any time; it picks up where you left off.")
    except (ValueError, OSError) as e:
        log(f"ERROR {e}")
        sys.exit(f"error: {e}")
