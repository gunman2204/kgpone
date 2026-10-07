@echo off
echo ========================================
echo 🚀 Starting KgpOne Development Environment
echo ========================================

echo 1. Starting Redis via Docker Compose...
docker compose up -d redis

echo.
echo 2. Starting Infinity Embeddings Server...
cd infinity
start "Infinity Server" cmd /c "uv sync && uv run python main.py"
cd ..

echo.
echo 3. Starting Backend API ^& Worker...
cd backend
echo Running DB Migrations...
call uv run alembic upgrade head
echo Training Intent Classifier...
call uv run python -m src.scripts.train_intent_classifier

start "Backend API Server" cmd /c "uv run uvicorn src.main:app --reload"
start "Celery Worker" cmd /c "uv run celery -A src.workers.app.celery_app worker --loglevel=info --pool=solo"
cd ..

echo.
echo 4. Starting Frontend Development Server...
cd frontend
call npm install
start "Frontend Server" cmd /c "npm run dev"
cd ..

echo ========================================
echo 🌟 All services are booting up in separate windows!
echo - Frontend: http://localhost:5173
echo - Backend API: http://localhost:8000
echo - API Docs: http://localhost:8000/docs
echo - Infinity Server: http://localhost:7997
echo ========================================
pause
