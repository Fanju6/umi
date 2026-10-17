#!/usr/bin/env python3
"""One-shot umi Root READ-ONLY preflight + private local partition backups.

Reports only whitelisted boot/recovery metadata and safe kernel state.
Local boot/recovery/dtbo.img are NOT uploaded or copied to Git.
No device writes, sysfs changes, mount, reboot, fastboot or boot attempt.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PARTS = ("boot", "recovery", "dtbo")
LAYOUT = PARTS + ("vbmeta", "vbmeta_system", "vendor_boot", "super")
MAX_PART = 256 * 1024 * 1024
CFG = {"CONFIG_PSTORE", "CONFIG_PSTORE_RAM", "CONFIG_PSTORE_CONSOLE",
       "CONFIG_PSTORE_PMSG", "CONFIG_PSTORE_FTRACE", "CONFIG_DEBUG_FS",
       "CONFIG_SERIAL_EARLYCON", "CONFIG_MAGIC_SYSRQ", "CONFIG_KEXEC"}
CMD = {"console", "earlycon", "loglevel", "ramoops.mem_address",
       "ramoops.mem_size", "skip_initramfs"}
SHELL = r"""
printf 'ID|%s|%s|%s|%s|%s|%s\n' \
  "$(getprop ro.product.device)" "$(uname -r)" \
  "$(getprop ro.build.ab_update)" "$(getprop ro.boot.slot_suffix)" \
  "$(id -u)" "$(getprop sys.boot_completed)"
printf 'SEC|%s|%s|%s\n' "$(getprop ro.boot.verifiedbootstate)" \
  "$(getprop ro.boot.vbmeta.device_state)" "$(getprop ro.boot.flash.locked)"
for name in boot recovery dtbo vbmeta vbmeta_system vendor_boot super; do
  state=missing; bytes=0
  for base in /dev/block/by-name /dev/block/bootdevice/by-name; do
    file="$base/$name"; [ -r "$file" ] || continue
    state=present
    bytes=$(blockdev --getsize64 "$file" 2>/dev/null) || bytes=
    case "$bytes" in
      ''|*[!0-9]*)
        dev=$(basename "$(readlink -f "$file" 2>/dev/null)")
        sectors=$(cat "/sys/class/block/$dev/size" 2>/dev/null)
        case "$sectors" in ''|*[!0-9]*) bytes=0 ;;
          *) bytes=$((sectors * 512)) ;;
        esac ;;
    esac
    break
  done
  printf 'PART|%s|%s|%s\n' "$name" "$state" "$bytes"
done
for name in pstore debugfs; do
  if grep -q "[[:space:]]$name[[:space:]]" /proc/mounts; then state=yes; else state=no; fi
  printf 'MOUNT|%s|%s\n' "$name" "$state"
done
for item in /sys/fs/pstore/*; do
  [ -f "$item" ] || continue
  case "$(basename "$item")" in
    console-ramoops*) kind=console ;; dmesg-ramoops*) kind=dmesg ;;
    pmsg-ramoops*) kind=pmsg ;; ftrace-ramoops*) kind=ftrace ;;
    *) continue ;;
  esac
  printf 'PSTORE|%s\n' "$kind"
done
for key in mem_address mem_size record_size console_size pmsg_size ftrace_size; do
  file="/sys/module/ramoops/parameters/$key"
  [ -r "$file" ] || continue
  printf 'RAMOOPS|%s|%s\n' "$key" "$(head -n 1 "$file" 2>/dev/null)"
done
if [ -r /proc/config.gz ]; then
  (gzip -dc /proc/config.gz 2>/dev/null || zcat /proc/config.gz 2>/dev/null) |
  grep -E '^CONFIG_(PSTORE|PSTORE_RAM|PSTORE_CONSOLE|PSTORE_PMSG|PSTORE_FTRACE|DEBUG_FS|SERIAL_EARLYCON|MAGIC_SYSRQ|KEXEC)=' |
  head -n 20 | while IFS= read -r cfg; do printf 'CFG|%s\n' "$cfg"; done
fi
if [ -r /proc/cmdline ]; then
  for word in $(cat /proc/cmdline); do
    case "$word" in console=*|earlycon=*|loglevel=*|ramoops.mem_address=*|ramoops.mem_size=*|skip_initramfs=*)
      printf 'CMD|%s\n' "$word";;
    esac
  done
fi
printf 'END\n'
"""

def need(ok, reason):
    if not ok:
        raise ValueError(reason)

def parse(raw):
    need(len(raw) <= 35000, "output too large")
    report = {"parts": {}, "mounts": {}, "pstore_kinds": [],
              "ramoops": {}, "kernel_config": {}, "selected_cmdline": {}}
    identity = security = ended = False
    for row in raw.replace("\r", "").splitlines():
        if not row:
            continue
        if row == "END":
            need(not ended, "duplicate end marker")
            ended = True
            continue
        key, sep, val = row.partition("|")
        need(sep, "unknown diagnostic output")
        if key == "ID":
            values = val.split("|")
            need(not identity and len(values) == 6
                 and values[0] == "umi"
                 and re.fullmatch(r"4\.19\.[A-Za-z0-9._+~-]{1,120}", values[1])
                 and values[2:] == ["false", "", "0", "1"],
                 "incorrect umi, Root or non-A/B state")
            report["kernel"] = values[1]
            identity = True
        elif key == "SEC":
            values = val.split("|")
            need(not security and len(values) == 3
                 and all(re.fullmatch(r"[A-Za-z0-9._-]{0,40}", x) for x in values),
                 "invalid boot verification properties")
            report["boot_security"] = {
                name: (value or "unavailable")
                for name, value in zip(("verifiedbootstate", "vbmeta_device_state",
                                         "flash_locked"), values)}
            security = True
        elif key == "PART":
            parts = val.split("|")
            need(len(parts) == 3, "bad partition row")
            name, state, n = parts
            need(name in LAYOUT and name not in report["parts"] and
                 state in {"present", "missing"} and n.isdecimal(),
                 "invalid partition state")
            report["parts"][name] = {
                "present": state == "present",
                "size_bytes": int(n) if state == "present" else None}
        elif key == "MOUNT":
            fields = val.split("|")
            need(len(fields) == 2, "invalid mount")
            name, state = fields
            need(name in {"pstore", "debugfs"} and state in {"yes", "no"}
                 and name not in report["mounts"], "invalid mount name")
            report["mounts"][name] = state == "yes"
        elif key == "PSTORE":
            need(val in {"console", "dmesg", "pmsg", "ftrace"}, "invalid pstore type")
            report["pstore_kinds"].append(val)
        elif key == "RAMOOPS":
            fields = val.split("|")
            need(len(fields) == 2, "invalid ramoops metadata")
            name, value = fields
            need(name in {"mem_address", "mem_size", "record_size", "console_size",
                          "pmsg_size", "ftrace_size"} and
                 name not in report["ramoops"] and
                 re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)", value),
                 "invalid ramoops value")
            report["ramoops"][name] = value
        elif key == "CFG":
            item, _, value = val.partition("=")
            need(item in CFG and value in {"y", "n", "m"} and
                 item not in report["kernel_config"], "bad kernel config")
            report["kernel_config"][item] = value
        elif key == "CMD":
            item, _, value = val.partition("=")
            need(item in CMD and item not in report["selected_cmdline"] and
                 re.fullmatch(r"[A-Za-z0-9_.:+,@/-]{0,150}", value),
                 "unapproved cmdline value")
            report["selected_cmdline"][item] = value
        else:
            raise ValueError("unknown probe section")
    need(identity and security and ended and set(report["parts"]) == set(LAYOUT)
         and set(report["mounts"]) == {"pstore", "debugfs"},
         "incomplete Root preflight")
    report["pstore_kinds"] = sorted(set(report["pstore_kinds"]))
    return report

def read_header(path, part):
    with path.open("rb") as f:
        head = f.read(1660)
    if part in ("boot", "recovery"):
        need(len(head) >= 44 and head[:8] == b"ANDROID!",
             "not an Android boot header")
        version = int.from_bytes(head[40:44], "little")
        need(version == 2, "unexpected boot header version")
        return {"type": "android_boot_v2", "version": version,
                "page_size": int.from_bytes(head[36:40], "little"),
                "kernel_bytes": int.from_bytes(head[8:12], "little"),
                "ramdisk_bytes": int.from_bytes(head[16:20], "little"),
                "second_bytes": int.from_bytes(head[24:28], "little")}
    need(head[:4] == bytes.fromhex("d7b7ab1e"),
         "not standard DTBO table")
    total = int.from_bytes(head[4:8], "big")
    count = int.from_bytes(head[16:20], "big")
    need(total == 5514578 and count == 12, "DTBO header changed from known data")
    return {"type": "android_dt_table_v0", "declared_bytes": total,
            "entries": count}

def backup(adb, part, expect, folder):
    need(part in PARTS and isinstance(expect, int) and
         4096 <= expect <= MAX_PART, "partition size missing or too large")
    command = ('for p in /dev/block/by-name/{0} '
               '/dev/block/bootdevice/by-name/{0}; do '
               '[ -r "$p" ] || continue; exec dd if="$p" '
               'bs=1048576 2>/dev/null; done; exit 7').format(part)
    need(not (folder / (part + ".img")).exists(),
         "previous backup exists: no silent replacement")
    fd, tmp = tempfile.mkstemp(prefix="." + part + ".", suffix=".partial",
                               dir=str(folder))
    os.close(fd)
    n = 0
    digest = hashlib.sha256()
    proc = None
    try:
        proc = subprocess.Popen([adb, "exec-out", "su", "-c", command],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        with open(tmp, "wb") as f:
            while True:
                block = proc.stdout.read(1024 * 1024)
                if not block:
                    break
                n += len(block)
                need(n <= expect, "partition grew during copy")
                digest.update(block)
                f.write(block)
            f.flush()
            os.fsync(f.fileno())
        need(proc.wait(timeout=15) == 0 and n == expect,
             "short/failed partition read")
        head = read_header(Path(tmp), part)
        os.replace(tmp, folder / (part + ".img"))
        return {"saved_locally": True, "filename": part + ".img",
                "size_bytes": n, "sha256": digest.hexdigest(), "header": head}
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
        if os.path.exists(tmp):
            os.unlink(tmp)

def collect(adb, output, folder):
    pre = subprocess.run([adb, "shell", "getprop", "ro.product.device"],
                         text=True, capture_output=True, timeout=15, check=True)
    need(pre.stdout.strip() == "umi", "wrong device; aborted before Root")
    run = subprocess.run([adb, "shell", "su", "-c", "sh"], input=SHELL,
                         text=True, errors="replace", capture_output=True,
                         timeout=60, check=True)
    result = parse(run.stdout)
    repo = Path(__file__).resolve().parents[1]
    need(not folder.resolve().is_relative_to(repo),
         "private backup destination must be outside Git checkout")
    folder.mkdir(parents=True, exist_ok=True)
    result["backups"] = {}
    for part in PARTS:
        p = result["parts"][part]
        if not p["present"]:
            result["backups"][part] = {
                "saved_locally": False, "reason": "not_present"}
            continue
        try:
            result["backups"][part] = backup(adb, part, p["size_bytes"], folder)
        except (OSError, ValueError, subprocess.SubprocessError):
            result["backups"][part] = {
                "saved_locally": False, "reason": "read_or_validation_failed"}
    result.update({
        "device": "umi", "phase": "one-shot-readonly-preflight",
        "source": "Root read-only current OS + PRIVATE local boot/recovery/dtbo backups",
        "backup_files_only_on_pc": True,
        "independent_recovery_boot_verified": False,
        "independent_recovery_restore_verified": False,
        "reliable_early_kernel_logs_verified": False,
        "linux_612_boot_tested": False,
        "safe_to_attempt_mainline_boot": False, "safe_to_flash": False,
        "writes_to_device": False})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--probe", action="store_true",
                   help="explicit Root read-only metadata + local backup")
    p.add_argument("--adb", default="adb")
    p.add_argument("--output", type=Path, required=True,
                   help="safe metadata JSON; do not include raw partition data")
    p.add_argument("--backup-dir", type=Path, required=True,
                   help="PRIVATE PC directory for boot/recovery/dtbo.img")
    a = p.parse_args()
    if not a.probe:
        p.error("device contact requires explicit --probe")
    try:
        result = collect(a.adb, a.output, a.backup_dir)
        done = {n: v["saved_locally"] for n, v in result["backups"].items()}
        print(json.dumps({
            "device": "umi", "backup_completed": done,
            "boot_security": result["boot_security"],
            "pstore_mounted": result["mounts"]["pstore"],
            "safe_to_flash": False,
            "share_json": str(a.output), "keep_backups_private": str(a.backup_dir)
        }, ensure_ascii=False, indent=2))
        return 0 if all(done.values()) else 2
    except (ValueError, OSError, subprocess.SubprocessError):
        print("Read-only preflight aborted. Check ADB, su and umi; "
              "no device state changed.", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
