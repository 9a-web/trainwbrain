# Start: Backend + Frontend

## Проверка перед запуском

```powershell
# MongoDB должен работать на localhost:27017
Get-Process mongod -ErrorAction SilentlyContinue
# Если нет — mongod --dbpath <data_dir>
```

## Backend — FastAPI (порт 8000)

```powershell
# Зависимости уже установлены, но если нет:
# pip install -r backend/requirements.txt

Start-Process -FilePath "python" `
  -ArgumentList "-m","uvicorn","server:app","--host","0.0.0.0","--port","8000","--reload" `
  -WorkingDirectory "<PROJECT_ROOT>/backend" `
  -WindowStyle Hidden

# Проверка (ждёт ~4 с):
Start-Sleep 4
Invoke-WebRequest http://localhost:8000/api/ -UseBasicParsing
# 200 → {"message":"Hello World"}
```

## Frontend — React/CRACO (порт 3000)

```powershell
# Зависимости уже установлены, но если нет:
# yarn install --cwd frontend

Start-Process -FilePath "cmd" `
  -ArgumentList "/c","yarn","start" `
  -WorkingDirectory "<PROJECT_ROOT>/frontend"

# Проверка (ждёт ~45 с, CRA компилируется долго):
Start-Sleep 45
Invoke-WebRequest http://localhost:3000 -UseBasicParsing -TimeoutSec 10
# 200
```

## Быстрый старт (оба сразу)

```powershell
cd <PROJECT_ROOT>

# 1. Backend
Start-Process -FilePath "python" `
  -ArgumentList "-m","uvicorn","server:app","--host","0.0.0.0","--port","8000","--reload" `
  -WorkingDirectory "$PWD/backend" -WindowStyle Hidden

# 2. Frontend (параллельно, пока backend поднимается)
Start-Process -FilePath "cmd" `
  -ArgumentList "/c","yarn","start" `
  -WorkingDirectory "$PWD/frontend"

# 3. Ждать пока оба поднимутся (~45 с)
Start-Sleep 4;  Write-Host "Backend: $(iwr http://localhost:8000/api/ -UseBasicParsing).StatusCode"
Start-Sleep 41; Write-Host "Frontend: $(iwr http://localhost:3000 -UseBasicParsing -TimeoutSec 10).StatusCode"
```

## Остановка

```powershell
Get-Process python,uwsgi,node -ErrorAction SilentlyContinue | Stop-Process -Force
```

## Важно

- **Порядок**: MongoDB → backend → frontend.
- **Тайминги**: backend ~4 с, frontend ~45 с (из-за CRA/CRACO).
- **Порты**: жёстко 8000 (back) и 3000 (front) — зашито в `.env`.
- **frontend/.env**: `REACT_APP_BACKEND_URL=http://localhost:8000` — без этого фронт не найдёт API.
- **Сборка**: `yarn` (не npm), старт через `craco`.