#Requires -Version 5.1
<#
.SYNOPSIS
    umi / LineageOS 23.2-20261004 KernelSU 3.3.0 userspace bootstrap.
.DESCRIPTION
    Checks the specific known TEST2 device and, only with -Install, uses
    explicitly enabled LineageOS Rooted debugging to install the pinned
    upstream ksud. NEVER flashes boot, remounts /system, or changes SELinux.
    This is an assisted installer, not an unattended on-device first boot fix.
.EXAMPLE
    .\scripts\umi-ksud-bootstrap.ps1
.EXAMPLE
    .\scripts\umi-ksud-bootstrap.ps1 -Install
#>
[CmdletBinding()]
param(
    [switch]$Install,
    [string]$Adb = "adb"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedSha256 = "8614de6cdc2233c71fd0d1c64381ea10fbe6658651bae9b5a8dab4fe08e6344b"
$OfficialUrl = "https://github.com/tiann/KernelSU/releases/download/v3.3.0/ksud-aarch64-linux-android"
$ExpectedRom = "23.2-20261004-NIGHTLY-umi"
$StagingPath = "/data/local/tmp/umi-ksud-3.3.0-bootstrap"
$InstalledPath = "/data/adb/ksud"

function Invoke-CheckedAdb {
    param([string[]]$Arguments)
    $output = & $Adb @Arguments 2>&1
    $status = $LASTEXITCODE
    $result = (($output | Out-String).Trim())
    if ($status -ne 0) {
        throw "adb $($Arguments -join ' ') failed (exit $status): $result"
    }
    return $result
}

Get-Command $Adb -ErrorAction Stop | Out-Null
Invoke-CheckedAdb -Arguments @("wait-for-device") | Out-Null

$device = Invoke-CheckedAdb -Arguments @("shell", "getprop", "ro.product.device")
$rom = Invoke-CheckedAdb -Arguments @("shell", "getprop", "ro.lineage.version")
$boot = Invoke-CheckedAdb -Arguments @("shell", "getprop", "sys.boot_completed")
$kernel = Invoke-CheckedAdb -Arguments @("shell", "uname", "-r")
$selinux = Invoke-CheckedAdb -Arguments @("shell", "getenforce")
$manager = Invoke-CheckedAdb -Arguments @("shell", "pm", "path", "me.weishu.kernelsu")

if ($device -ne "umi") { throw "This bootstrap is only for Xiaomi umi (found '$device')." }
if ($rom -ne $ExpectedRom) { throw "Expected $ExpectedRom; found '$rom'. Do not mix ROM versions." }
if ($boot -ne "1") { throw "Android boot is not complete; refusing to install." }
if ($kernel -notmatch "^4\.19\.325-cip131-st15-perf-g71b13e62f057") {
    throw "Kernel '$kernel' is not the pinned umi TEST2 family."
}
if ($selinux -ne "Enforcing") {
    throw "SELinux '$selinux' is not Enforcing; do not disguise a policy problem."
}
if ($manager -notmatch "^package:") {
    throw "Official KernelSU Manager (me.weishu.kernelsu) must be installed first."
}
Write-Host "Device: $device | ROM: $rom | boot completed | SELinux: $selinux"
Write-Host "Kernel: $kernel"
Write-Host "KernelSU Manager: installed"

if (-not $Install) {
    Write-Host "READ-ONLY PASS. To install official ksud, enable Rooted debugging and run:"
    Write-Host "  .\scripts\umi-ksud-bootstrap.ps1 -Install"
    exit 0
}

# Rooted debugging is a user-controlled switch. The script never alters device
# developer options or SELinux to obtain privileges.
Write-Host "Requesting ADB Root (must be enabled in LineageOS Developer options)..."
$rootReply = Invoke-CheckedAdb -Arguments @("root")
Write-Host $rootReply
Invoke-CheckedAdb -Arguments @("wait-for-device") | Out-Null
$uid = Invoke-CheckedAdb -Arguments @("shell", "id", "-u")
if ($uid -ne "0") {
    throw "ADB did not become uid=0; enable Rooted debugging explicitly. Nothing was installed."
}

# Do not overwrite a manager-maintained or previously manually installed ksud.
$existing = Invoke-CheckedAdb -Arguments @("shell", "sh", "-c",
    "if test -s /data/adb/ksud; then echo PRESENT; else echo ABSENT; fi")
if ($existing -ne "ABSENT") {
    $details = Invoke-CheckedAdb -Arguments @("shell", "ls", "-lZ", $InstalledPath)
    Write-Host "Existing ksud found; not overwriting it:"
    Write-Host $details
    Write-Host "Reopen KernelSU Manager and validate ordinary app authorization."
    exit 0
}

$localFile = Join-Path ([System.IO.Path]::GetTempPath()) "umi-ksud-v3.3.0-$PID"
try {
    Write-Host "Downloading official pinned KernelSU v3.3.0 ksud..."
    Invoke-WebRequest -Uri $OfficialUrl -OutFile $localFile -UseBasicParsing
    $actual = (Get-FileHash -Path $localFile -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedSha256) {
        throw "Refusing unverified ksud: SHA256 $actual != $ExpectedSha256"
    }
    if ((Get-Item $localFile).Length -ne 6286568) {
        throw "Unexpected ksud executable length"
    }

    Invoke-CheckedAdb -Arguments @("push", $localFile, $StagingPath) | Out-Host
    Invoke-CheckedAdb -Arguments @("shell", "chmod", "700", $StagingPath) | Out-Null

    # The *official* installer configures the SELinux label and extracted
    # binaries. Do not replace it with a bare cp of the executable.
    Invoke-CheckedAdb -Arguments @("shell", $StagingPath, "install") | Out-Host
    $details = Invoke-CheckedAdb -Arguments @("shell", "ls", "-lZ", $InstalledPath)
    if ($details -notmatch "u:object_r:ksu_file:s0") {
        throw "ksud exists but the expected ksu_file SELinux label is missing: $details"
    }
    $hash = Invoke-CheckedAdb -Arguments @("shell", "sha256sum", $InstalledPath)
    if ($hash -notmatch [regex]::Escape($ExpectedSha256)) {
        throw "Installed ksud SHA256 differs from the verified source"
    }
    Write-Host "Verified userspace installation: $details"
    Write-Host "Open KernelSU Manager to let it synchronize libksud.so, then test ordinary-app Root."
    Write-Host "After testing, turn Rooted debugging off."
} finally {
    # Clean only our temporary stage file; never touch /data/adb/ksud here.
    & $Adb shell rm -f $StagingPath 2>&1 | Out-Null
    Remove-Item -LiteralPath $localFile -ErrorAction SilentlyContinue
}
