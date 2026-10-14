#requires -Version 5.1
<#
  Read-only recovered-device triage for failed experimental umi boot.
  No root, no flashing, no reboot, no access to private app data.
  May only find evidence if pstore still retained after restoring stock boot.
#>
$ErrorActionPreference = 'Continue'
if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
    throw 'Android platform-tools adb is not in PATH'
}
$devices = @(& adb devices)
$connected = @($devices | Where-Object { $_ -match '^\S+\s+device\s*$' })
if ($connected.Count -ne 1) {
    throw 'Connect exactly one authorized Android device'
}
$product = ((& adb shell getprop ro.product.device) | Out-String).Trim()
if ($product -ne 'umi') { throw "Expected umi; got $product" }
Write-Host "=== umi / previous failed boot evidence (read-only) ==="
foreach ($prop in @(
    'ro.boot.bootreason','sys.boot.reason','persist.sys.boot.reason',
    'ro.boot.verifiedbootstate','ro.build.version.sdk','ro.lineage.version'
)) {
    $v = ((& adb shell getprop $prop) | Out-String).Trim()
    Write-Output ("{0}: {1}" -f $prop, $v)
}
Write-Host "=== Stock kernel compiler after recovery ==="
& adb shell cat /proc/version

Write-Host "=== pstore file names and permissions ==="
$entries = @(& adb shell ls -la /sys/fs/pstore 2>&1)
$entries | ForEach-Object { Write-Output $_ }
Write-Host "=== Attempt read-only scanning of persisted kernel crash (limited output) ==="
$filenames = @(& adb shell ls -1 /sys/fs/pstore 2>$null)
$pattern = '(?i)(kernel panic|BUG:|Oops:|Call trace:|Unable to handle kernel|watchdog|fatal exception|KSU|KernelSU|SELinux|init:.*(abort|fatal|fail))'
$count = 0
foreach ($item in $filenames) {
    $f = ([string]$item).Trim()
    if ($f -notmatch '^(console|dmesg|pmsg)-ramoops(-[0-9]+)?$') { continue }
    $out = @(& adb shell cat "/sys/fs/pstore/$f" 2>$null)
    if ($LASTEXITCODE -ne 0) {
        Write-Output "Could not read $f (permissions or file missing)"
        continue
    }
    $hits = @($out | Select-String -Pattern $pattern | Select-Object -First 60)
    Write-Host "File: $f; matching lines: $($hits.Count) (first 60 only)"
    $hits | ForEach-Object { Write-Output $_.Line }
    $count += $hits.Count
}
if (-not $count) {
    Write-Warning 'No readable evidence found. It may have been overwritten during recovery; this does not rule out a panic.'
}
Write-Host 'No changes made. Review any logs for sensitive details before sharing.'
