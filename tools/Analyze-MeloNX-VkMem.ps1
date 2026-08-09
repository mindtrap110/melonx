param(
    [Parameter(Position = 0)]
    [string]$LogPath,

    [string]$CsvPath
)

$ErrorActionPreference = 'Stop'

function Convert-BytesToMiB([long]$Bytes) {
    return [math]::Round($Bytes / 1MB, 2)
}

if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $candidate = Get-ChildItem -Path . -File |
        Where-Object { $_.Name -like 'MeloNX-App-Log*.txt' -or $_.Name -like '*MeloNX*Log*.txt' } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($null -eq $candidate) {
        throw 'MeloNX log file was not found in the current folder. Put the log next to this script or pass -LogPath.'
    }

    $LogPath = $candidate.FullName
}

$LogPath = (Resolve-Path -LiteralPath $LogPath).Path

$rows = New-Object System.Collections.Generic.List[object]

Get-Content -LiteralPath $LogPath | ForEach-Object {
    $line = $_

    if ($line -match '\[VK-MEM\]\s+(?<data>.+)$') {
        $values = [ordered]@{}

        foreach ($token in ($Matches['data'] -split '\s+')) {
            if ($token -match '^(?<key>[^=]+)=(?<value>.+)$') {
                $key = $Matches['key']
                $value = $Matches['value'].TrimEnd('.', ',', ';')
                [long]$number = 0

                if ([long]::TryParse($value, [ref]$number)) {
                    $values[$key] = $number
                }
                else {
                    $values[$key] = $value
                }
            }
        }

        if ($values.Contains('ms') -and $values.Contains('blockBytes')) {
            $rows.Add([pscustomobject]$values)
        }
    }
}

if ($rows.Count -eq 0) {
    throw 'No [VK-MEM] records were found. Make sure the IPA was built from three-houses-recovery-2ms-fence-vkmem-audit.'
}

if ([string]::IsNullOrWhiteSpace($CsvPath)) {
    $directory = Split-Path -Parent $LogPath
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $CsvPath = Join-Path $directory "MeloNX-VkMem-Audit-$stamp.csv"
}

$rows | Export-Csv -LiteralPath $CsvPath -NoTypeInformation -Encoding UTF8

$first = $rows[0]
$last = $rows[$rows.Count - 1]
$peakBlockBytes = [long](($rows | Measure-Object -Property blockBytes -Maximum).Maximum)
$peakLiveBytes = [long](($rows | Measure-Object -Property liveBytes -Maximum).Maximum)
$peakSlackBytes = [long](($rows | Measure-Object -Property slackBytes -Maximum).Maximum)

$durationSeconds = [math]::Max(0.001, ([double]$last.ms - [double]$first.ms) / 1000.0)
$blockGrowthBytes = [long]$last.blockBytes - [long]$first.blockBytes
$liveGrowthBytes = [long]$last.liveBytes - [long]$first.liveBytes
$slackGrowthBytes = [long]$last.slackBytes - [long]$first.slackBytes
$blockGrowthRate = $blockGrowthBytes / $durationSeconds
$liveGrowthRate = $liveGrowthBytes / $durationSeconds

$efficiency = 0.0
$slackRatio = 0.0
if ([long]$last.blockBytes -gt 0) {
    $efficiency = 100.0 * [double]$last.liveBytes / [double]$last.blockBytes
    $slackRatio = [double]$last.slackBytes / [double]$last.blockBytes
}

$lastPipeline = $null
$pipelineMatches = Select-String -LiteralPath $LogPath -Pattern 'PipelineAB G#(?<g>[0-9]+)' -AllMatches
foreach ($matchLine in $pipelineMatches) {
    foreach ($match in $matchLine.Matches) {
        $lastPipeline = [long]$match.Groups['g'].Value
    }
}

Write-Host ''
Write-Host '=== MeloNX Vulkan Memory Audit ==='
Write-Host "Log: $LogPath"
Write-Host "Audit records: $($rows.Count)"
Write-Host ("Audit span: {0:N1} s" -f $durationSeconds)
if ($null -ne $lastPipeline) {
    Write-Host "Last PipelineAB: G#$lastPipeline"
}
Write-Host ''

Write-Host 'VkDeviceMemory blocks'
Write-Host ("  start : {0,10:N2} MiB" -f (Convert-BytesToMiB ([long]$first.blockBytes)))
Write-Host ("  peak  : {0,10:N2} MiB" -f (Convert-BytesToMiB $peakBlockBytes))
Write-Host ("  end   : {0,10:N2} MiB" -f (Convert-BytesToMiB ([long]$last.blockBytes)))
Write-Host ("  growth: {0,10:N2} MiB ({1:N2} MiB/s)" -f (Convert-BytesToMiB $blockGrowthBytes), ($blockGrowthRate / 1MB))
Write-Host "  blocks: $($first.blocks) -> $($last.blocks)"
Write-Host "  creates/frees: $($last.blockCreates) / $($last.blockFrees)"
Write-Host ''

Write-Host 'Live Vulkan suballocations'
Write-Host ("  start : {0,10:N2} MiB" -f (Convert-BytesToMiB ([long]$first.liveBytes)))
Write-Host ("  peak  : {0,10:N2} MiB" -f (Convert-BytesToMiB $peakLiveBytes))
Write-Host ("  end   : {0,10:N2} MiB" -f (Convert-BytesToMiB ([long]$last.liveBytes)))
Write-Host ("  growth: {0,10:N2} MiB ({1:N2} MiB/s)" -f (Convert-BytesToMiB $liveGrowthBytes), ($liveGrowthRate / 1MB))
Write-Host "  allocs: $($first.allocs) -> $($last.allocs)"
Write-Host "  creates/frees: $($last.suballocCreates) / $($last.suballocFrees)"
Write-Host ''

Write-Host 'Unused bytes inside retained blocks'
Write-Host ("  start : {0,10:N2} MiB" -f (Convert-BytesToMiB ([long]$first.slackBytes)))
Write-Host ("  peak  : {0,10:N2} MiB" -f (Convert-BytesToMiB $peakSlackBytes))
Write-Host ("  end   : {0,10:N2} MiB" -f (Convert-BytesToMiB ([long]$last.slackBytes)))
Write-Host ("  growth: {0,10:N2} MiB" -f (Convert-BytesToMiB $slackGrowthBytes))
Write-Host ("  end allocation efficiency: {0:N1}%" -f $efficiency)
Write-Host ''

Write-Host 'Buffer / image split at final sample'
Write-Host ("  buffers: blocks={0} blockMiB={1:N2} liveMiB={2:N2} allocs={3}" -f $last.bufBlocks, (Convert-BytesToMiB ([long]$last.bufBlockBytes)), (Convert-BytesToMiB ([long]$last.bufLiveBytes)), $last.bufAllocs)
Write-Host ("  images : blocks={0} blockMiB={1:N2} liveMiB={2:N2} allocs={3}" -f $last.imgBlocks, (Convert-BytesToMiB ([long]$last.imgBlockBytes)), (Convert-BytesToMiB ([long]$last.imgLiveBytes)), $last.imgAllocs)
Write-Host ("  managed heap at final sample: {0:N2} MiB" -f (Convert-BytesToMiB ([long]$last.managed)))
Write-Host ''

Write-Host 'Automatic interpretation'
$large = 512MB
if ($blockGrowthBytes -gt $large -and $slackGrowthBytes -gt $large -and $slackRatio -gt 0.50) {
    Write-Host '  STRONG SIGNAL: VkDeviceMemory blocks are growing much faster than live Vulkan allocations.'
    Write-Host '  Likely direction: allocator fragmentation/block-retention or excessively small VkDeviceMemory block sizing.'
}
elseif ($liveGrowthBytes -gt $large -and $liveGrowthBytes -gt ($blockGrowthBytes * 0.60)) {
    Write-Host '  STRONG SIGNAL: live Vulkan resource memory itself is accumulating.'
    Write-Host '  Likely direction: image/buffer lifetime leak. Use the buffer/image split above to choose the next target.'
}
elseif ($blockGrowthBytes -lt 128MB -and $liveGrowthBytes -lt 128MB) {
    Write-Host '  Vulkan allocator growth is small. If iOS process footprint still grows by gigabytes, investigate MoltenVK/Metal or host-imported memory outside this allocator.'
}
else {
    Write-Host '  MIXED SIGNAL: both retained block memory and live allocations contribute, or the sample interval is too short.'
    Write-Host '  Compare blockBytes, liveBytes, slackBytes, and the buffer/image split in the CSV.'
}

Write-Host ''
Write-Host "CSV written to: $CsvPath"
