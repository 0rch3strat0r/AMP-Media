param(
  [string]$Inputs = ".\clips",
  [string]$Config = "config_gpt_mini_amp.json",
  [string]$Output = "recap.mp4",
  [string]$Venv = ".\.venv\Scripts\Activate.ps1"
)

if (Test-Path $Venv) {
  & $Venv
} else {
  Write-Error "Venv not found at $Venv"
  exit 1
}

python tools\preflight.py
if ($LASTEXITCODE -ne 0) {
  Write-Error "Preflight failed"
  exit 1
}

python -m mini.cli pipeline --inputs $Inputs --config $Config --output $Output --run
exit $LASTEXITCODE
