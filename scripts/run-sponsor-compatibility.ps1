$ErrorActionPreference = "Stop"

$localEnvironmentFile = Join-Path $PSScriptRoot "..\.env.compatibility.local"
if (Test-Path -LiteralPath $localEnvironmentFile) {
  foreach ($line in Get-Content -LiteralPath $localEnvironmentFile) {
    if ($line -match '^\s*(GEMINI_API_KEY|DAYTONA_API_KEY)=(.*)$') {
      $name = $Matches[1]
      $value = $Matches[2].Trim()
      if ($value -and -not [Environment]::GetEnvironmentVariable($name, "Process")) {
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
      }
    }
  }
}

if (-not $env:GEMINI_API_KEY) {
  throw "GEMINI_API_KEY is required"
}
if (-not $env:DAYTONA_API_KEY) {
  throw "DAYTONA_API_KEY is required"
}

$composeFile = Join-Path $PSScriptRoot "..\docker-compose.compatibility.yml"
$healthUrl = "http://localhost:8790/healthz"

docker compose -f $composeFile up -d --build --wait
if ($LASTEXITCODE -ne 0) {
  throw "The Docker compatibility stack did not become healthy"
}

npm run compatibility:prove
if ($LASTEXITCODE -ne 0) {
  throw "The live TrueForge compatibility proof failed"
}

docker compose -f $composeFile restart trueforge
if ($LASTEXITCODE -ne 0) {
  throw "TrueForge could not be restarted for persistence verification"
}

$deadline = [DateTimeOffset]::UtcNow.AddMinutes(2)
do {
  try {
    $response = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 3 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
      break
    }
  } catch {
    Start-Sleep -Seconds 2
  }
} while ([DateTimeOffset]::UtcNow -lt $deadline)

if ([DateTimeOffset]::UtcNow -ge $deadline) {
  throw "TrueForge did not recover after restart"
}

npm run compatibility:verify-persistence
if ($LASTEXITCODE -ne 0) {
  throw "TrueForge session persistence verification failed"
}
