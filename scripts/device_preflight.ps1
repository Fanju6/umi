#requires -Version 5.1
<#
  Read-only umi ADB preflight for Windows PowerShell.
  No root, flashing, firmware reads, partition writes or reboots.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
    throw "ADB is not in PATH. Install Android platform-tools first."
}

$devices = @(& adb devices)
if ($LASTEXITCODE -ne 0) { throw "Unable to query adb devices." }
$serials = @($devices | ForEach-Object {
    if ($_ -match '^\s*(\S+)\s+device\s*$') { $Matches[1] }
})
if ($serials.Count -ne 1) {
    throw "Connect exactly one authorized USB-debugging device (found $($serials.Count))."
}
$deviceSerial = $serials[0]

function Get-DeviceProp {
    param([Parameter(Mandatory)][string]$Key)
    $value = @(& adb -s $deviceSerial shell getprop $Key)
    if ($LASTEXITCODE -ne 0) { throw "Cannot read property: $Key" }
    return ($value | Out-String).Trim()
}
function Get-DeviceCommand {
    param([Parameter(Mandatory)][string[]]$Args)
    $value = @(& adb -s $deviceSerial shell @Args)
    if ($LASTEXITCODE -ne 0) { throw "Read-only adb shell query failed." }
    return ($value | Out-String).Trim()
}

$product = Get-DeviceProp 'ro.product.device'
$vendor = Get-DeviceProp 'ro.product.vendor.device'
if ($product -ne 'umi' -and $vendor -ne 'umi') {
    throw "Non-umi device: product=$product vendor=$vendor. Refusing to continue."
}

Write-Host "=== Xiaomi Mi 10 umi / read-only preflight ==="
Write-Output ("Device:          {0}" -f $product)
Write-Output ("Android API:     {0}" -f (Get-DeviceProp 'ro.build.version.sdk'))
Write-Output ("Android version: {0}" -f (Get-DeviceProp 'ro.build.version.release'))
Write-Output ("LineageOS:       {0}" -f (Get-DeviceProp 'ro.lineage.version'))
Write-Output ("Kernel:          {0}" -f (Get-DeviceCommand @('uname','-r')))
Write-Output ("SELinux:         {0}" -f (Get-DeviceCommand @('getenforce')))
Write-Output ("Boot slot:       {0}" -f (Get-DeviceProp 'ro.boot.slot_suffix'))
Write-Output ("Boot slot name:  {0}" -f (Get-DeviceProp 'ro.boot.slot'))
Write-Output ("Verified Boot:   {0}" -f (Get-DeviceProp 'ro.boot.verifiedbootstate'))
Write-Output ("A/B update prop: {0}" -f (Get-DeviceProp 'ro.build.ab_update'))
Write-Output ("Virtual A/B:     {0}" -f (Get-DeviceProp 'ro.virtual_ab.enabled'))

Write-Host "=== Partition names, not contents ==="
$locations = @('/dev/block/by-name', '/dev/block/bootdevice/by-name')
$found = $false
foreach ($location in $locations) {
    $entries = @(& adb -s $deviceSerial shell ls $location 2>$null)
    if ($LASTEXITCODE -eq 0) {
        $names = @($entries | Where-Object {
            $_ -match '^(boot|recovery|dtbo|vbmeta|vendor_boot|init_boot)(_[ab])?$'
        })
        Write-Output ("Path: {0}" -f $location)
        if ($names.Count -gt 0) {
            $names | ForEach-Object { Write-Output ("  {0}" -f $_) }
        } else {
            Write-Output "  No recognizable boot partition names."
        }
        $found = $true
        break
    }
}
if (-not $found) {
    Write-Warning "Partition symlinks not accessible to non-root adb shell."
}
Write-Host "Read-only check complete. No changes were made."
Write-Warning "No boot/root/SELinux runtime safety claim is made by this script."
