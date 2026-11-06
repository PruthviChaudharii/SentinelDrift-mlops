$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Open Docker Desktop, wait for Engine running, then run this script again.' }
docker compose --profile automation up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Docker startup failed. Read the error above; existing database volumes were preserved.' }
Write-Host 'Website: http://localhost:8000'
Write-Host 'MLflow: http://localhost:5000 | Grafana: http://localhost:3000 | Airflow: http://localhost:8080'
Write-Host 'Airflow login: admin; get its generated password with the command in docs/LOCAL-MLOPS.md.'
Start-Process 'http://localhost:8000'
