$ErrorActionPreference = "Stop"

Write-Host "=== AssistBall setup ===" -ForegroundColor Cyan

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  throw "Node.js is required. Install Node.js LTS and run this script again."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "npm is required. Install Node.js LTS and run this script again."
}

$PythonCommand = "python"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCommand = "py"
  } else {
    throw "Python 3.11+ is required. Install Python and run this script again."
  }
}

Write-Host "Installing Node dependencies..." -ForegroundColor Yellow
npm install

Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path "backend/venv")) {
  if ($PythonCommand -eq "py") {
    py -3 -m venv backend/venv
  } else {
    python -m venv backend/venv
  }
}

Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
& .\backend\venv\Scripts\python.exe -m pip install --upgrade pip
& .\backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt

Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Run: npm run dev" -ForegroundColor Green
