param(
  [string]$Inputs = ".\clips",
  [string]$Config = "config_gpt_mini_amp.json",
  [string]$OutputStub = "recap.mp4",
  [int[]]$Seeds = @(42,73,104,135),
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

$base = [System.IO.Path]::GetFileNameWithoutExtension($OutputStub)
$ext  = [System.IO.Path]::GetExtension($OutputStub)

foreach ($seed in $Seeds) {
  Write-Host "=== Running seed $seed ==="
  $outFile = if ($ext) { "{0}_s{1}{2}" -f $base, $seed, $ext } else { "{0}_s{1}" -f $base, $seed }
  python -m mini.cli pipeline --inputs $Inputs --config $Config --output $outFile --seed $seed --run
  if ($LASTEXITCODE -ne 0) {
    Write-Error "Variant $seed failed"
    exit 1
  }
}
