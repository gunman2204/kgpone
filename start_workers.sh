#!/bin/bash
echo "========================================"
echo "⚙️ Starting Background Workers"
echo "========================================"

cleanup() {
    echo -e "\n🛑 Stopping Workers..."
    kill $(jobs -p) 2>/dev/null
    exit
}
trap cleanup SIGINT SIGTERM

cd backend || exit

echo "1. Starting Celery Worker..."
uv run celery -A src.workers.app.celery_app worker --loglevel=info --concurrency=2 &

echo "2. Starting Dropzone Watcher..."
uv run python -m src.workers.dropzone_watcher &

echo "✅ Workers are running. Restart this script if they crash."
wait
