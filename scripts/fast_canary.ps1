param(
  [Parameter(Mandatory=$true)][string]$Inputs,
  [string]$Config = "config_gpt_mini_amp.json",
  [string]$Output = "recap_canary.mp4",
  [int]$Seed = 42,
  [switch]$Fast,
  [string]$Venv = ".\.venv\Scripts\Activate.ps1",
  [string]$LogPath = ".\_logs\fast_canary_$(Get-Date -Format yyyyMMdd_HHmmss).log"
)

$ErrorActionPreference = "Stop"
$logDir = Split-Path $LogPath -Parent
if (-not $logDir) { $logDir = "." }
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Test-Path $Venv)) { throw "Venv not found at $Venv" }
. $Venv

function Resolve-ConfigPath([string]$path) {
  if (-not (Test-Path $path)) { throw "Config not found: $path" }
  return (Resolve-Path $path).Path
}

function New-FastConfig([string]$baseConfigPath) {
  $cfg = Get-Content $baseConfigPath -Raw | ConvertFrom-Json
  $cfg.deliverables = @("9:16")
  $cfg.max_duration = 20
  if (-not $cfg.render) { $cfg | Add-Member -NotePropertyName render -NotePropertyValue @{} }
  $cfg.render.preset = "ultrafast"
  $cfg.render.crf = 23
  $configDir = Split-Path $baseConfigPath -Parent
  if (-not $configDir) { $configDir = (Get-Location).Path }
  $tempPath = Join-Path $configDir "config_fast_canary.json"
  $cfg | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $tempPath
  return $tempPath
}

function Get-PrimaryRatio([string]$configPath) {
  $cfgObj = Get-Content $configPath -Raw | ConvertFrom-Json
  $delivs = @($cfgObj.deliverables)
  if (-not $delivs -or $delivs.Count -eq 0) { $delivs = @("9:16") }
  return $delivs[0]
}

function Get-OutputPath([string]$stub, [string]$suffix) {
  $base = [System.IO.Path]::GetFileNameWithoutExtension($stub)
  $ext = [System.IO.Path]::GetExtension($stub)
  if ([string]::IsNullOrWhiteSpace($ext)) { $ext = '.mp4' }
  return "$base`_$suffix$ext"
}

Write-Host "== Preflight =="
python tools\preflight.py 2>&1 | Tee-Object -FilePath $LogPath -Append
if ($LASTEXITCODE -ne 0) { throw "Preflight failed; see $LogPath" }

$ConfigFullPath = Resolve-ConfigPath $Config
$TempConfig = $null
if ($Fast) {
  Write-Host "== Building temporary fast config =="
  $TempConfig = New-FastConfig $ConfigFullPath
  $ConfigFullPath = $TempConfig
}

$primaryRatio = Get-PrimaryRatio $ConfigFullPath
$ratioSuffix = ($primaryRatio -replace ':', 'x')

$edl1 = $Output.Replace('.mp4', '.edl.json')
$OutputVideo1 = Get-OutputPath $Output $ratioSuffix
$Output2 = $Output.Replace('.mp4', '_r2.mp4')
$edl2 = $Output2.Replace('.mp4', '.edl.json')
$OutputVideo2 = Get-OutputPath $Output2 $ratioSuffix

Write-Host "== Pipeline run 1 =="
$env:FFMPEG_LOG_LEVEL = "error"
python -m mini.cli pipeline --inputs $Inputs --config $ConfigFullPath --output $Output --seed $Seed --run --edl $edl1 2>&1 | Tee-Object -FilePath $LogPath -Append
if ($LASTEXITCODE -ne 0) { throw "Pipeline run 1 failed; see $LogPath" }

Write-Host "== Pipeline run 2 =="
python -m mini.cli pipeline --inputs $Inputs --config $ConfigFullPath --output $Output2 --seed $Seed --run --edl $edl2 2>&1 | Tee-Object -FilePath $LogPath -Append
if ($LASTEXITCODE -ne 0) { throw "Pipeline run 2 failed; see $LogPath" }

Write-Host "== Validate outputs =="
python tools\validate_outputs.py --config $ConfigFullPath --edl1 $edl1 --edl2 $edl2 --vid1 $OutputVideo1 --vid2 $OutputVideo2 2>&1 | Tee-Object -FilePath $LogPath -Append
if ($LASTEXITCODE -ne 0) { throw "Validation failed; see $LogPath" }

Write-Host "`n✅ Fast canary PASSED. Log: $LogPath"

if ($TempConfig -and (Test-Path $TempConfig)) {
  Remove-Item $TempConfig -Force
}
