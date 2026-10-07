#!/bin/bash
echo "========================================"
echo "🌐 Starting Web Services (API & Frontend)"
echo "========================================"

cleanup() {
    echo -e "\n🛑 Stopping Web Services..."
    kill $(jobs -p) 2>/dev/null
    exit
}
trap cleanup SIGINT SIGTERM

echo "1. Starting FastAPI Backend (Auto-reload enabled)..."
cd backend || exit
uv sync
uv run alembic upgrade head
uv run uvicorn src.main:app --reload &
cd ..

echo "2. Starting Vite Frontend (Auto-reload enabled)..."
cd frontend || exit
npm install
npm run dev &
cd ..

echo "✅ Web Services running! (FastAPI: :8000, Vite: :5173)"
wait
