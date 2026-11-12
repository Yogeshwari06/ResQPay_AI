# Start the FastAPI camera/detection backend and React dashboard in separate windows.
# The backend owns the camera; running the edge agent at the same time can conflict.
$root = (Resolve-Path .).Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

$backendCommand = @"
Set-Location '$backend'
if (-not (Test-Path '.\venv\Scripts\python.exe')) {
    py -3.13 -m venv venv
    if (`$LASTEXITCODE -ne 0) { throw 'Python 3.13 is required to create the backend environment.' }
    .\venv\Scripts\python.exe -m pip install -r requirements.txt
    if (`$LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
} else {
    .\venv\Scripts\python.exe -c "import app; import cv2; assert cv2.__version__.split('.')[0] == '4' and hasattr(cv2, 'CascadeClassifier')"
    if (`$LASTEXITCODE -ne 0) {
        .\venv\Scripts\python.exe -m pip install -r requirements.txt
        if (`$LASTEXITCODE -ne 0) { throw 'Backend dependency repair failed.' }
    }
}
.\venv\Scripts\python.exe -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
"@
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand

if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Push-Location $frontend
    npm ci
    $installExitCode = $LASTEXITCODE
    Pop-Location
    if ($installExitCode -ne 0) { throw 'Frontend dependency installation failed.' }
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$frontend'; npm start"

Write-Host "Started the FastAPI backend and React frontend in separate windows."
Write-Host "The camera must be connected to this computer. Do not start backend/edge_agent.py at the same time."
if (-not (Test-Path (Join-Path $frontend ".env"))) {
    Write-Warning "Copy frontend/.env.example to frontend/.env and configure Firebase Web App values to enable sign-in."
}
if (-not (Test-Path (Join-Path $backend ".env"))) {
    Write-Warning "Create backend/.env with Firebase Admin credentials to enable authenticated API routes."
}
