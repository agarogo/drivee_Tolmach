$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$venvPython = Join-Path $repoRoot ".venv\\Scripts\\python.exe"
$pythonCommand = if (Test-Path $venvPython) { $venvPython } else { "python" }

$pythonPathEntries = @(
  $repoRoot.Path,
  (Join-Path $repoRoot "backend")
)
$existingPythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH", "Process")
if ($existingPythonPath) {
  $pythonPathEntries += $existingPythonPath.Split([IO.Path]::PathSeparator) | Where-Object { $_ }
}
$env:PYTHONPATH = ($pythonPathEntries | Select-Object -Unique) -join [IO.Path]::PathSeparator

Push-Location $repoRoot
try {
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & $pythonCommand -c "import fastapi, pydantic, pydantic_settings, sqlglot" 1>$null 2>$null
  $depsReady = $LASTEXITCODE -eq 0
  $ErrorActionPreference = $previousErrorActionPreference

  if ($depsReady) {
    & $pythonCommand -m unittest discover backend/tests
    exit $LASTEXITCODE
  }

  docker image inspect drivee_tolmach-backend *> $null
  if ($LASTEXITCODE -ne 0) {
    docker compose build backend | Out-Host
  }

  docker run --rm `
    -v "${repoRoot}:/workspace" `
    -w /workspace `
    -e PYTHONPATH=/workspace:/workspace/backend `
    -e PLATFORM_DATABASE_URL=postgresql://user:pass@localhost/testdb `
    -e ANALYTICS_DATABASE_URL=postgresql://user:pass@localhost/testdb `
    -e FRONTEND_ORIGINS=http://localhost:5173 `
    drivee_tolmach-backend python -m unittest discover backend/tests
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
