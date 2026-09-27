# Starts the SamudraVani API on port 8000.
#
# Credentials are read from your Windows user environment variables, so they never live in this
# repository or in a terminal history. Save each one once in PowerShell, e.g.:
#   [Environment]::SetEnvironmentVariable("MOSDAC_USERNAME", "<your MOSDAC username>", "User")
# Supported: MOSDAC_USERNAME, MOSDAC_PASSWORD, CDSAPI_URL, CDSAPI_KEY, ANTHROPIC_API_KEY,
#            COPERNICUSMARINE_SERVICE_USERNAME, COPERNICUSMARINE_SERVICE_PASSWORD, OPENMETEO_API_KEY
# (Copernicus Marine can also use the file written by `copernicusmarine login`, ERA5 ~/.cdsapirc.)
#
# Usage:  .\run_server.ps1                   (uses `python` on PATH)
#         .\run_server.ps1 -Python C:\path\to\python.exe
param([string]$Python = "python", [int]$Port = 8000)

$names = "MOSDAC_USERNAME", "MOSDAC_PASSWORD", "CDSAPI_URL", "CDSAPI_KEY", "ANTHROPIC_API_KEY",
         "COPERNICUSMARINE_SERVICE_USERNAME", "COPERNICUSMARINE_SERVICE_PASSWORD", "OPENMETEO_API_KEY", "ASK_MODE"
$loaded = @()
foreach ($n in $names) {
    $v = [Environment]::GetEnvironmentVariable($n, "User")
    if ($v) { Set-Item -Path "Env:$n" -Value $v; $loaded += $n }
}
Write-Host ("Loaded from your user settings: " + ($(if ($loaded) { $loaded -join ", " } else { "(none)" })))

Set-Location $PSScriptRoot
& $Python -m uvicorn main:app --host 0.0.0.0 --port $Port
