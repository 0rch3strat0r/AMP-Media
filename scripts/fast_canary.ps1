param(
  [Parameter(Mandatory=$true)][string]$Inputs,
  [string]$Config = "config_gpt_mini_amp.json",
  [string]$Output = "recap_canary.mp4",
  [int]$Seed = 42,
  [switch]$Fast,
  [string]$Venv = ".\.venv\Scripts\Activate.ps1",
  [string]$LogPath = ".\_logs\fast_canary_$(Get-Date -Format yyyyMMdd_HHmmss).log"
)

$PSNativeCommandUseErrorActionPreference = $false
$ErrorActionPreference = "Continue"

function Invoke-Native {
  param([Parameter(Mandatory=$true)][string]$CmdLine)
  Write-Host ">> $CmdLine"
  $env:PYTHONWARNINGS = "ignore::UserWarning,ignore::FutureWarning"
  cmd /c $CmdLine
  if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $CmdLine" }
}

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
Invoke-Native 'python tools\preflight.py'

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
Invoke-Native ("python -m mini.cli pipeline --inputs `"{0}`" --config `"{1}`" --output `"{2}`" --seed {3} --run --edl `"{4}`"" -f $Inputs,$ConfigFullPath,$Output,$Seed,$edl1)

Write-Host "== Pipeline run 2 =="
Invoke-Native ("python -m mini.cli pipeline --inputs `"{0}`" --config `"{1}`" --output `"{2}`" --seed {3} --run --edl `"{4}`"" -f $Inputs,$ConfigFullPath,$Output2,$Seed,$edl2)

Write-Host "== Validate outputs =="
Invoke-Native ("python tools\validate_outputs.py --config `"{0}`" --edl1 `"{1}`" --edl2 `"{2}`" --vid1 `"{3}`" --vid2 `"{4}`"" -f $ConfigFullPath,$edl1,$edl2,$OutputVideo1,$OutputVideo2)

Write-Host "`n✅ Fast canary PASSED. Log: $LogPath"

if ($TempConfig -and (Test-Path $TempConfig)) {
  Remove-Item $TempConfig -Force
}
