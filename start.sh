#!/bin/bash
set -e

echo "🚀 Starting AWPIS demo..."

# Check if .env exists
if [ ! -f .env ]; then
  echo "❌ Error: .env file not found."
  echo "Please copy .env.example to .env and fill in your keys (GEMINI_API_KEY, GITHUB_TOKEN, etc)."
  exit 1
fi

# Start infra
docker-compose up -d mongo redis
echo "⏳ Waiting for MongoDB and Redis..."
sleep 3

# Seed demo data (skip if already seeded)
python scripts/seed_demo_data.py 2>/dev/null && echo "✅ Demo data seeded" || echo "ℹ️  Seed skipped"

# Start FastAPI backend
uvicorn backend.main:app --reload --port 8000 2>&1 | sed 's/^/[BACKEND]  /' &
BACKEND_PID=$!
echo "✅ Backend running on http://localhost:8000"

# Start Next.js frontend
cd frontend
npm run dev 2>&1 | sed 's/^/[FRONTEND] /' &
FRONTEND_PID=$!
echo "✅ Frontend running on http://localhost:3000"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AWPIS Demo Ready"
echo "  Dashboard → http://localhost:3000"
echo "  API Docs  → http://localhost:8000/docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Graceful shutdown on Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID; docker-compose stop" EXIT
wait
