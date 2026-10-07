#!/bin/bash
echo "========================================"
echo "🧱 Starting Core Infrastructure"
echo "========================================"

# Function to clean up
cleanup() {
    echo -e "\n🛑 Stopping Infrastructure..."
    kill $(jobs -p) 2>/dev/null
    podman compose stop redis
    exit
}
trap cleanup SIGINT SIGTERM

echo "1. Starting Redis..."
podman compose up -d redis

echo "2. Starting Infinity Embeddings Server..."
cd infinity || exit
uv sync
uv run python main.py &
cd ..

echo "3. Starting Ollama Local AI Daemon..."
if ! pgrep -x "ollama" > /dev/null
then
    OLLAMA_HOST=127.0.0.1:11434 ollama serve &> /tmp/ollama.log &
else
    echo "Ollama is already running."
fi

echo "✅ Infrastructure is running. Keep this tab open."
wait
