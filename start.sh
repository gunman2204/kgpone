#!/bin/bash

echo "🚀 Starting KgpOne Development Environment..."

# Function to clean up background processes on exit
cleanup() {
    echo -e "\n🛑 Stopping all background processes..."
    kill $(jobs -p) 2>/dev/null
    echo "Stopping Redis..."
    podman compose stop redis
    echo "✅ All processes stopped."
    exit
}

# Catch Ctrl+C and call cleanup
trap cleanup SIGINT SIGTERM

echo "========================================"
echo "1. Starting Redis via Podman Compose"
echo "========================================"
podman compose up -d redis

echo "========================================"
echo "2. Starting Infinity Embeddings Server"
echo "========================================"
cd infinity || exit
uv sync
uv run python main.py &
INFINITY_PID=$!
cd ..

echo "========================================"
echo "2.5 Starting Ollama Local AI Daemon"
echo "========================================"
# Start ollama if it's not already running
if ! pgrep -x "ollama" > /dev/null
then
    echo "Starting ollama serve..."
    OLLAMA_HOST=127.0.0.1:11434 ollama serve &> /tmp/ollama.log &
    OLLAMA_PID=$!
else
    echo "Ollama is already running."
fi

echo "========================================"
echo "3. Starting Backend API & Worker"
echo "========================================"
cd backend || exit
uv sync
echo "Running DB Migrations..."
uv run alembic upgrade head
echo "Training Intent Classifier..."
uv run python -m src.scripts.train_intent_classifier

echo "Starting FastAPI Server..."
uv run uvicorn src.main:app --reload &
API_PID=$!

echo "Starting Celery Worker..."
uv run celery -A src.workers.app.celery_app worker --loglevel=info --concurrency=2 &
CELERY_PID=$!

echo "Starting Dropzone Watcher..."
uv run python -m src.workers.dropzone_watcher &
DROPZONE_PID=$!
cd ..

echo "========================================"
echo "4. Starting Frontend Development Server"
echo "========================================"
cd frontend || exit
npm install
npm run dev &
FRONTEND_PID=$!
cd ..

echo "========================================"
echo "🌟 All services are now running!"
echo "- Frontend: http://localhost:5173"
echo "- Backend API: http://localhost:8000"
echo "- API Docs: http://localhost:8000/docs"
echo "- Infinity Server: http://localhost:7997"
echo "========================================"
echo "Press Ctrl+C to stop everything."

# Wait for all background processes
wait
