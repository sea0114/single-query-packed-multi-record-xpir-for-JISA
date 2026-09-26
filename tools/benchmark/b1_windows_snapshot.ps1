# Additive B1 launcher. Does not invoke the B0/B1 formal CLI.
param([string]$SnapshotName="windows_precheck.json")
$ErrorActionPreference="Stop"

$b1Log=Join-Path (Get-Location) "revision_notes/B1_primary_logs"
$b1Since=(Get-Item -LiteralPath "revision_notes/B0_frozen/B0-1.1.json").LastWriteTimeUtc
function Get-B1WindowsSnapshot([DateTime]$Since) {
    $eventStatus="READ_OK";$events=@()
    try {
        $all=Get-WinEvent -FilterHashtable @{ LogName="System"; StartTime=$Since } -ErrorAction Stop
        $events=@($all | Where-Object {
            ($_.ProviderName -eq "Microsoft-Windows-Kernel-Power" -and $_.Id -in @(42,506,507)) -or
            ($_.ProviderName -eq "Microsoft-Windows-Power-Troubleshooter" -and $_.Id -eq 1) -or
            ($_.ProviderName -eq "Microsoft-Windows-Kernel-General" -and $_.Id -eq 12) -or
            ($_.ProviderName -eq "Microsoft-Windows-UserModePowerService")
        } | ForEach-Object { [ordered]@{ provider=$_.ProviderName; id=$_.Id; utc=$_.TimeCreated.ToUniversalTime().ToString("o") } })
    } catch {
        if ($_.FullyQualifiedErrorId -notlike "*NoMatchingEventsFound*") { $eventStatus=$_.Exception.Message }
    }
    $processes=@(Get-Process | Select-Object Id,ProcessName,CPU,WorkingSet64)
    $competitors=@($processes | Where-Object { $_.ProcessName -match "^(g\+\+|gcc|cc1plus|nvcc|sage|b0_worker|s4_n_e2e|prime95|furmark|cinebench)$" })
    $os=Get-CimInstance Win32_OperatingSystem
    return [ordered]@{
        captured_utc=[DateTime]::UtcNow.ToString("o")
        processor=(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
        os=($os | Select-Object Caption,Version,BuildNumber)
        last_boot_utc=$os.LastBootUpTime.ToUniversalTime().ToString("o")
        events_since_utc=$Since.ToUniversalTime().ToString("o")
        power_plan=(powercfg /getactivescheme | Out-String).Trim()
        event_log_status=$eventStatus
        relevant_environment_events=$events
        competing_processes=$competitors
        processes=$processes
    }
}
$startPath=Join-Path $b1Log $SnapshotName
if (Test-Path -LiteralPath $startPath) { throw "Immutable snapshot exists." }
Get-B1WindowsSnapshot $b1Since | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $startPath -Encoding UTF8
Write-Output "B1 Windows snapshot captured."
