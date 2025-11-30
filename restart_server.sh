#!/bin/bash

echo "🛑 Stopping all VeriReceipt processes..."

# Kill any running FastAPI servers
pkill -f "uvicorn app.api.main:app" 2>/dev/null
pkill -f "python.*run_web_demo.py" 2>/dev/null

# Kill any processes on port 8000 and 3000
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null

echo "✅ All processes stopped"
echo ""
echo "🔄 Starting fresh server..."
sleep 2

# Start the web demo
python run_web_demo.py
