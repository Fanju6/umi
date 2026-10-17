#!/usr/bin/env python3
"""Read-only post-failure ADB capture in TWRP/recovery (no reboot or flash).

Stores raw pstore files *only* in a PRIVATE local directory outside Git.
Summary JSON contains only file names, sizes, hashes and keyword flags.
Recovery live dmesg isn't the failed experimental kernel's dmesg.
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

ALLOW = re.compile(
    r"^(?:console-ramoops(?:-[0-9]+)?|"
    r"dmesg-ramoops(?:-[0-9]+)?|"
    r"pmsg-ramoops(?:-[0-9]+)?|"
    r"ftrace-ramoops(?:-[0-9]+)?|"
    r"pstore-blk-(?:console|dmesg|pmsg|ftrace)(?:-[0-9]+)?)$"
)
MAX_SINGLE = 8 * 1024 * 1024
MAX_FILES = 32
TAG = "UMI612-MINIMAL-INIT"

def need(ok, msg):
    if not ok:
        raise ValueError(msg)

def check_recovery(adb):
    probe = subprocess.run(
        [adb, "shell", "sh", "-c",
         "printf 'MODE='; getprop ro.bootmode; "
         "printf 'TWRP='; getprop ro.twrp.version; "
         "printf 'UID='; id -u;"],
        capture_output=True, text=True, errors="replace", timeout=20,
        check=True)
    lines = probe.stdout.replace("\r", "").splitlines()
    values = {}
    for line in lines:
        name, sep, val = line.partition("=")
        if sep and name in ("MODE", "TWRP", "UID") and name not in values:
            values[name] = val.strip()
    need(values.get("UID") == "0", "recovery ADB is not root")
    need(values.get("MODE") == "recovery" or bool(values.get("TWRP")),
         "not confirmed recovery/TWRP; refusing to capture")
    return {"mode": values.get("MODE", ""), "twrp_version_present": bool(values.get("TWRP"))}

def enumerate_pstore(adb):
    cmd = ('for f in /sys/fs/pstore/*; do [ -f "$f" ] || continue; '
           'basename "$f"; done')
    p = subprocess.run([adb, "shell", "sh", "-c", cmd],
                       capture_output=True, text=True, errors="replace",
                       timeout=20, check=True)
    names = p.stdout.replace("\r", "").splitlines()
    need(len(names) <= 128, "unexpectedly many pstore filenames")
    return sorted(set(n for n in names if ALLOW.fullmatch(n)))[:MAX_FILES]

def read_file(adb, fullpath, directory, safe_name):
    need(safe_name == "last_kmsg" or ALLOW.fullmatch(safe_name),
         "invalid pstore filename")
    need(fullpath in ("/proc/last_kmsg", "/sys/fs/pstore/" + safe_name),
         "invalid remote input path")
    destination = directory / (safe_name + ".log")
    need(not destination.exists(), "won't overwrite previous log")
    fd, tmp = tempfile.mkstemp(prefix=".capture-", suffix=".partial", dir=directory)
    os.close(fd)
    p = None
    total = 0
    hash_obj = hashlib.sha256()
    saw_version = saw_panic = saw_tag = False
    tail = b""
    try:
        p = subprocess.Popen([adb, "exec-out", "cat", fullpath],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        with open(tmp, "wb") as stream:
            while True:
                data = p.stdout.read(65536)
                if not data:
                    break
                total += len(data)
                need(total <= MAX_SINGLE, "log exceeds safe size limit")
                hash_obj.update(data)
                scan = tail + data
                low = scan.lower()
                saw_version |= b"linux version 6.12" in low
                saw_panic |= b"kernel panic" in low or b"oops:" in low
                saw_tag |= TAG.encode().lower() in low
                tail = scan[-128:]
                stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        need(p.wait(timeout=12) == 0 and total > 0,
             "log missing or inaccessible")
        os.replace(tmp, destination)
        return {"filename": destination.name, "size_bytes": total,
                "sha256": hash_obj.hexdigest(),
                "contains_linux_612_banner": saw_version,
                "contains_kernel_panic_or_oops": saw_panic,
                "contains_test_init_marker": saw_tag}
    finally:
        if p is not None and p.poll() is None:
            p.kill()
            p.wait(timeout=10)
        if os.path.exists(tmp):
            os.unlink(tmp)

def capture(adb, folder, report_path):
    # Do not run on a booted Android OS, or write into the Git checkout.
    identity = check_recovery(adb)
    repo = Path(__file__).resolve().parents[1]
    need(not folder.resolve().is_relative_to(repo),
         "raw logs must be outside Git repository")
    folder.mkdir(parents=True, exist_ok=True)
    names = enumerate_pstore(adb)
    attempts = names + ["last_kmsg"]
    captured = []
    failed = []
    for name in attempts:
        path = "/proc/last_kmsg" if name == "last_kmsg" else "/sys/fs/pstore/" + name
        try:
            captured.append(read_file(adb, path, folder, name))
        except (OSError, ValueError, subprocess.SubprocessError):
            failed.append(name)
    r = {"device": "umi", "phase": "recovery-postmortem",
         "source": "TWRP/recovery read-only ADB log capture",
         "recovery_confirmed": True,
         "recovery_metadata": identity, "pstore_filenames_found": names,
         "captured": captured, "not_captured": failed,
         "linux_612_boot_log_found": any(x["contains_linux_612_banner"] for x in captured),
         "test_init_marker_found": any(x["contains_test_init_marker"] for x in captured),
         "recovery_dmesg_not_confused_with_failed_kernel": True,
         "raw_logs_kept_local": True,
         "writes_to_device": False, "safe_to_flash": False}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    return r

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--adb", default="adb")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--raw-log-dir", type=Path, required=True)
    a = ap.parse_args()
    if not a.probe:
        ap.error("requires --probe while TWRP/recovery is already booted")
    try:
        result = capture(a.adb, a.raw_log_dir, a.output)
        print(json.dumps({
            "recovery_confirmed": True,
            "pstore_files_detected": len(result["pstore_filenames_found"]),
            "logs_saved": len(result["captured"]),
            "linux_612_boot_log_found": result["linux_612_boot_log_found"],
            "test_init_marker_found": result["test_init_marker_found"],
            "share_summary_json": str(a.output),
            "keep_raw_logs_private": str(a.raw_log_dir)
        }, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError):
        print("Recovery log capture refused/failed; no device writes.",
              file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
