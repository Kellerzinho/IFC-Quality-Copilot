[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

function Get-PublicErrorType {
    param([System.Management.Automation.ErrorRecord]$Record)

    if ($Record.Exception -is [System.Management.Automation.CommandNotFoundException]) {
        return "CommandNotFound"
    }
    if ($Record.Exception -is [System.TimeoutException]) {
        return "Timeout"
    }
    return "ParseError"
}

function New-UnavailableProbe {
    param([System.Management.Automation.ErrorRecord]$Record)

    return [ordered]@{
        status = "unavailable"
        error_type = Get-PublicErrorType -Record $Record
    }
}

function Invoke-CimProbe {
    param(
        [Parameter(Mandatory = $true)][string]$ClassName,
        [Parameter(Mandatory = $true)][string[]]$Properties,
        [switch]$Many
    )

    try {
        $rows = @(Get-CimInstance -ClassName $ClassName -ErrorAction Stop |
            Select-Object -Property $Properties)
        if ($Many) {
            $data = @($rows)
        }
        elseif ($rows.Count -gt 0) {
            $data = $rows[0]
        }
        else {
            throw "empty probe"
        }
        return [ordered]@{ status = "ok"; data = $data }
    }
    catch {
        return New-UnavailableProbe -Record $_
    }
}

$operatingSystem = Invoke-CimProbe -ClassName "Win32_OperatingSystem" -Properties @(
    "Caption", "Version", "BuildNumber", "OSArchitecture"
)
$computer = Invoke-CimProbe -ClassName "Win32_ComputerSystem" -Properties @(
    "Manufacturer", "Model", "SystemType", "TotalPhysicalMemory", "HypervisorPresent"
)
$processors = Invoke-CimProbe -ClassName "Win32_Processor" -Many -Properties @(
    "Name", "Manufacturer", "NumberOfCores", "NumberOfLogicalProcessors",
    "MaxClockSpeed", "L2CacheSize", "L3CacheSize", "VirtualizationFirmwareEnabled"
)
$memory = Invoke-CimProbe -ClassName "Win32_PhysicalMemory" -Many -Properties @(
    "Capacity", "Speed", "ConfiguredClockSpeed", "Manufacturer", "PartNumber", "FormFactor"
)
$video = Invoke-CimProbe -ClassName "Win32_VideoController" -Many -Properties @(
    "Name", "AdapterRAM", "DriverVersion", "DriverDate", "VideoProcessor", "Status"
)
$disks = Invoke-CimProbe -ClassName "Win32_DiskDrive" -Many -Properties @(
    "Model", "Size", "InterfaceType", "MediaType", "FirmwareRevision"
)
$volumes = Invoke-CimProbe -ClassName "Win32_LogicalDisk" -Many -Properties @(
    "DeviceID", "DriveType", "FileSystem", "Size", "FreeSpace"
)
$bios = Invoke-CimProbe -ClassName "Win32_BIOS" -Properties @(
    "Manufacturer", "SMBIOSBIOSVersion", "ReleaseDate"
)
$baseboard = Invoke-CimProbe -ClassName "Win32_BaseBoard" -Properties @(
    "Manufacturer", "Product", "Version"
)
$displayDrivers = Invoke-CimProbe -ClassName "Win32_VideoController" -Many -Properties @(
    "Name", "DriverVersion", "DriverDate", "Status"
)

try {
    $powerText = (& powercfg.exe /getactivescheme 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "powercfg failed"
    }
    $match = [regex]::Match($powerText, "\(([^()]*)\)\s*$")
    if (-not $match.Success -or [string]::IsNullOrWhiteSpace($match.Groups[1].Value)) {
        throw "power scheme name unavailable"
    }
    $power = [ordered]@{
        status = "ok"
        data = [ordered]@{ ActiveSchemeName = $match.Groups[1].Value.Trim() }
    }
}
catch {
    $power = New-UnavailableProbe -Record $_
}

$payload = [ordered]@{
    schema_version = 1
    os = $operatingSystem
    computer = $computer
    cpu = $processors
    memory = $memory
    gpu = $video
    storage = [ordered]@{ disks = $disks; volumes = $volumes }
    bios = $bios
    baseboard = $baseboard
    display_drivers = $displayDrivers
    power = $power
}

$payload | ConvertTo-Json -Depth 8 -Compress
