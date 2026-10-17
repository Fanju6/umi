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

def adb_transport_state(adb):
    """ADB transport advertises recovery even when ro.bootmode is 'unknown'."""
    result = subprocess.run(
        [adb, "devices"], capture_output=True, text=True,
        errors="replace", timeout=20, check=True)
    transports = []
    for line in result.stdout.replace("\r", "").splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] != "List":
            transports.append(fields[1])
    need(len(transports) == 1, "expected exactly one attached ADB device")
    return transports[0]


def adb_shell_read(adb, *arguments):
    """ADB shell direct argv commands without nested sh -c quoting."""
    command = [adb, "shell", *arguments]
    p = subprocess.run(command, capture_output=True, text=True,
                       errors="replace", timeout=20, check=False)
    need(p.returncode == 0,
         "adb shell " + arguments[0] + " returned exit " + str(p.returncode) +
         " (check TWRP ADB connection)")
    return p.stdout.strip()


def check_recovery(adb):
    transport = adb_transport_state(adb)
    # TWRP getprop can be blank or 'unknown'. Only check what is available.
    uid = adb_shell_read(adb, "id", "-u")
    need(uid == "0", "recovery ADB is not root (id -u=" + uid[:8] + ")")
    mode = adb_shell_read(adb, "getprop", "ro.bootmode")
    twrp = adb_shell_read(adb, "getprop", "ro.twrp.version")
    need(transport == "recovery" or mode == "recovery" or bool(twrp),
         "ADB transport, ro.bootmode and TWRP property do not confirm recovery")
    return {"mode": mode, "adb_transport": transport,
            "twrp_version_present": bool(twrp)}


def enumerate_pstore(adb):
    # Nested sh -c arg quoting is not portable through Windows platform-tools.
    # Use direct, read-only ls argv instead. Not-mounted pstore is expected
    # on some TWRP builds: still try /proc/last_kmsg.
    p = subprocess.run([adb, "shell", "ls", "-1", "/sys/fs/pstore"],
                       capture_output=True, text=True, errors="replace",
                       timeout=20, check=False)
    if p.returncode != 0:
        # Differentiate a missing pstore mount from a dropped ADB connection.
        need(adb_shell_read(adb, "id", "-u") == "0",
             "pstore inaccessible and Recovery ADB is no longer root")
        print("Note: /sys/fs/pstore not readable/listable in this recovery; "
              "trying /proc/last_kmsg only.", file=sys.stderr)
        return []
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
    saw_version = saw_panic = saw_tag = saw_legacy_419 = False
    tail = b""
    beginning = bytearray()
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
                if len(beginning) < 256:
                    beginning.extend(data[:256 - len(beginning)])
                hash_obj.update(data)
                scan = tail + data
                low = scan.lower()
                saw_version |= b"linux version 6.12" in low
                saw_legacy_419 |= b"linux version 4.19." in low
                saw_panic |= b"kernel panic" in low or b"oops:" in low
                saw_tag |= TAG.encode().lower() in low
                tail = scan[-128:]
                stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        need(p.wait(timeout=12) == 0 and total > 0,
             "log missing or inaccessible")
        # On certain TWRP builds 'adb exec-out cat' can return 0 while
        # routing the remote cat error text into stdout. It is NOT a log.
        if beginning.startswith((b"cat: ", b"/system/bin/cat: ", b"/bin/cat: ")):
            if (b"No such file or directory" in beginning
                    or b"Permission denied" in beginning
                    or b"Not a directory" in beginning):
                raise ValueError("remote cat error is not a kernel log")
        os.replace(tmp, destination)
        return {"filename": destination.name, "size_bytes": total,
                "sha256": hash_obj.hexdigest(),
                "contains_linux_612_banner": saw_version,
                "contains_legacy_linux_419_banner": saw_legacy_419,
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
         "legacy_linux_419_log_found": any(x["contains_legacy_linux_419_banner"] for x in captured),
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
            "legacy_linux_419_log_found": result["legacy_linux_419_log_found"],
            "test_init_marker_found": result["test_init_marker_found"],
            "share_summary_json": str(a.output),
            "keep_raw_logs_private": str(a.raw_log_dir)
        }, ensure_ascii=False, indent=2))
        return 0
    except ValueError as exc:
        print("Recovery log capture refused: " + str(exc) +
              ". No device writes.", file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError) as exc:
        print("Recovery log capture could not use ADB (" +
              type(exc).__name__ + "). No device writes.", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
