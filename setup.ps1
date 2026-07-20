# One-command setup for Jimothy (Windows). Safe to re-run -- only loads
# example data on a genuinely fresh install (skips it if db.sqlite3 already
# exists, so it never wipes a real portfolio).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Fail($msg) {
    Write-Host $msg -ForegroundColor Yellow
    exit 1
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Fail "Python was not found. Install Python 3.12+ from https://www.python.org/downloads/ (check `"Add python.exe to PATH`" during install) and try again."
}

$verOutput = (& python --version) 2>&1 | Out-String
$verString = ($verOutput -replace "Python ", "").Trim()
$verParts = $verString.Split(".")
$verMajor = [int]$verParts[0]
$verMinor = [int]$verParts[1]
if ($verMajor -lt 3 -or ($verMajor -eq 3 -and $verMinor -lt 12)) {
    Fail "Jimothy needs Python 3.12+. Found $verString. Install a newer version from https://www.python.org/downloads/ and try again."
}

$freshInstall = -not (Test-Path "db.sqlite3")

if (-not (Test-Path ".venv")) {
    Write-Host "Creating a virtual environment (.venv)..."
    python -m venv .venv
}

$venvPy = ".venv\Scripts\python.exe"

Write-Host "Installing dependencies..."
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r requirements.txt

if (-not (Test-Path ".env")) {
    Write-Host "Creating .env with a freshly generated secret key..."
    # Done entirely in Python, not PowerShell -replace -- the generated
    # key's charset includes $ and other characters that have special
    # meaning in a -replace replacement string.
    $pyScript = @'
from django.core.management.utils import get_random_secret_key

key = get_random_secret_key()
with open('.env.example') as f:
    lines = f.readlines()
with open('.env', 'w') as f:
    for line in lines:
        if line.startswith('DJANGO_SECRET_KEY='):
            f.write('DJANGO_SECRET_KEY=%s\n' % key)
        else:
            f.write(line)
'@
    $pyScript | & $venvPy -
}

Write-Host "Setting up the database..."
& $venvPy manage.py migrate

if ($freshInstall) {
    Write-Host "Loading example data..."
    & $venvPy manage.py seed_demo
}

Write-Host ""
Write-Host "Ready. Starting the server -- open http://127.0.0.1:8000/ in your browser." -ForegroundColor Green
Write-Host "(Press Ctrl+C to stop it.)"
& $venvPy manage.py runserver
