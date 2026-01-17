# ---------------------------------------------------
# Start script dla bloga FastAPI + PocketBase
# ---------------------------------------------------

# 1️⃣ Aktywacja virtualenv
$venvPath = ".\venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    Write-Host "Aktywacja virtual environment..."
    & $venvPath
} else {
    Write-Host "Nie znaleziono venv! Utwórz je najpierw: python -m venv venv"
    exit
}

# 2️⃣ Start PocketBase
$pbPath = ".\pocketbase.exe"   # <-- podaj poprawną ścieżkę do PocketBase
if (Test-Path $pbPath) {
    Write-Host "Uruchamianie PocketBase..."
    Start-Process -NoNewWindow -FilePath $pbPath
    Start-Sleep -Seconds 2  # małe opóźnienie, żeby PB się wczytał
} else {
    Write-Host "Nie znaleziono pocketbase.exe!"
    exit
}

# 3️⃣ Start FastAPI przez Uvicorn
Write-Host "Uruchamianie FastAPI (uvicorn main:app --reload)..."
uvicorn main:app --reload
