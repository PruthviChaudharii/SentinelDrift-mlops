$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
docker compose --profile automation stop
Write-Host 'Services stopped. Database, model versions and experiment volumes are preserved.'
