$ErrorActionPreference = "Stop"

Write-Host "[AssistBall] Installing/checking PyInstaller..."
if (Test-Path "backend\venv\Scripts\python.exe") {
  $Python = "backend\venv\Scripts\python.exe"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
  $Python = "py"
} else {
  $Python = "python"
}

if ($Python -eq "py") {
  & py -3 -m pip install pyinstaller
} else {
  & $Python -m pip install pyinstaller
}

if (Test-Path "backend-dist") { Remove-Item -Recurse -Force "backend-dist" }
New-Item -ItemType Directory -Force -Path "backend-dist" | Out-Null

Write-Host "[AssistBall] Building backend executable..."
if ($Python -eq "py") {
  & py -3 -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name AssistBallBackend `
    --distpath backend-dist `
    --workpath .build/backend `
    --specpath .build/backend `
    backend/launcher.py
} else {
  & $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name AssistBallBackend `
    --distpath backend-dist `
    --workpath .build/backend `
    --specpath .build/backend `
    backend/launcher.py
}

Write-Host "[AssistBall] Backend build complete."
