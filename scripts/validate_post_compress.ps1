param(
  [string]$Inputs = ".\clips",
  [string]$Config = "config_gpt_mini_amp.json",
  [string]$Output = "recap_canary.mp4",
  [int]$Seed = 42,
  [string]$Venv = ".\.venv\Scripts\Activate.ps1"
)

# 0) Activate venv
if (Test-Path $Venv) {
  & $Venv
} else {
  Write-Error "Venv not found at $Venv"
  exit 1
}

# 1) Preflight
python tools\preflight.py
if ($LASTEXITCODE -ne 0) {
  Write-Error "Preflight failed"
  exit 1
}

# Load config to determine deliverable suffix (default to 9:16)
$configJson = Get-Content $Config -Raw
$configData = $configJson | ConvertFrom-Json
$deliverables = @($configData.deliverables)
if (-not $deliverables -or $deliverables.Count -eq 0) {
  $deliverables = @("9:16")
}
$primaryRatio = $deliverables[0]
$ratioSuffix = $primaryRatio -replace ':', 'x'

function Get-OutputPath($stub, $suffix) {
  $base = [System.IO.Path]::GetFileNameWithoutExtension($stub)
  $ext = [System.IO.Path]::GetExtension($stub)
  if ([string]::IsNullOrEmpty($ext)) { $ext = '.mp4' }
  return "$base`_$suffix$ext"
}

$OutputVideo1 = Get-OutputPath $Output $ratioSuffix
$Output2 = if ($Output.EndsWith('.mp4')) { $Output.Replace('.mp4', '_r2.mp4') } else { "$Output_r2.mp4" }
$OutputVideo2 = Get-OutputPath $Output2 $ratioSuffix
$edl1 = if ($Output.EndsWith('.mp4')) { $Output.Replace('.mp4', '.edl.json') } else { "$Output.edl.json" }
$edl2 = if ($Output2.EndsWith('.mp4')) { $Output2.Replace('.mp4', '.edl.json') } else { "$Output2.edl.json" }

# 2) Run twice to confirm determinism
python -m mini.cli pipeline --inputs $Inputs --config $Config --output $Output --seed $Seed --run --edl $edl1
if ($LASTEXITCODE -ne 0) {
  Write-Error "Pipeline run 1 failed"
  exit 1
}

python -m mini.cli pipeline --inputs $Inputs --config $Config --output $Output2 --seed $Seed --run --edl $edl2
if ($LASTEXITCODE -ne 0) {
  Write-Error "Pipeline run 2 failed"
  exit 1
}

# 3) Compare EDLs
python tools\validate_outputs.py --config $Config --edl1 $edl1 --edl2 $edl2 --vid1 $OutputVideo1 --vid2 $OutputVideo2
if ($LASTEXITCODE -ne 0) {
  Write-Error "Validation failed"
  exit 1
}

Write-Host "✅ Post-compress validation PASSED"
