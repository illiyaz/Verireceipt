# Quick Fix - Analysis Stuck at 0%

## Problem
The streaming endpoint has an issue with async/queue interaction causing the analysis to hang.

## Immediate Solution

### Option 1: Use Regular Endpoint (Recommended for now)

Update the web UI to use `/analyze/hybrid` instead of `/analyze/hybrid/stream`:

```javascript
// In web/index.html, change:
const response = await fetch(`${API_BASE_URL}/analyze/hybrid/stream`, {
// To:
const response = await fetch(`${API_BASE_URL}/analyze/hybrid`, {
```

This will work but won't show real-time updates. You'll wait for all 3 engines to complete.

### Option 2: Restart Everything

```bash
# Kill all processes
pkill -9 -f "uvicorn"
pkill -9 -f "run_web_demo"

# Start fresh
python run_web_demo.py
```

### Option 3: Use the Old UI (No Streaming)

```bash
# Copy the old version back
cp web/index_streaming.html web/index_backup.html
# Then manually edit web/index.html to use /analyze/hybrid
```

## Root Cause

The streaming endpoint mixes:
- Thread-based execution (`ThreadPoolExecutor`)
- Queue-based communication (`queue.Queue`)
- Async/await (`asyncio`)

This causes blocking issues where:
1. Queue.get() blocks the async loop
2. Events don't get yielded properly
3. Browser never receives updates

## Proper Fix (TODO)

Replace the streaming implementation with one of:

### A. Use asyncio.Queue instead of queue.Queue

```python
import asyncio

update_queue = asyncio.Queue()

# In worker threads, use:
asyncio.run_coroutine_threadsafe(
    update_queue.put(event),
    loop
)

# In event_generator:
while engines_completed < 3:
    try:
        update = await asyncio.wait_for(
            update_queue.get(),
            timeout=0.1
        )
        yield f"event: {update['event']}\ndata: ...\n\n"
    except asyncio.TimeoutError:
        continue
```

### B. Use WebSockets instead of SSE

```python
from fastapi import WebSocket

@app.websocket("/ws/analyze")
async def analyze_websocket(websocket: WebSocket):
    await websocket.accept()
    
    # Send updates via websocket.send_json()
    await websocket.send_json({"event": "engine_complete", ...})
```

### C. Use Polling with Status Endpoint

```python
# Store analysis status in memory/redis
analysis_status = {}

@app.post("/analyze/start")
async def start_analysis(file: UploadFile):
    analysis_id = str(uuid.uuid4())
    # Start analysis in background
    background_tasks.add_task(run_analysis, analysis_id, file)
    return {"analysis_id": analysis_id}

@app.get("/analyze/status/{analysis_id}")
async def get_status(analysis_id: str):
    return analysis_status.get(analysis_id, {"status": "not_found"})
```

## Temporary Workaround

For now, use the regular endpoint. It works perfectly, just doesn't show real-time updates.

**Steps:**
1. Stop all servers
2. Edit `web/index.html` line ~XXX
3. Change endpoint from `/analyze/hybrid/stream` to `/analyze/hybrid`
4. Restart: `python run_web_demo.py`
5. Analysis will work, just wait for all results at once

## Testing

```bash
# Test regular endpoint
curl -X POST "http://localhost:8000/analyze/hybrid" \
  -F "file=@data/raw/Gas_bill.jpeg"

# Should return complete results after 10-15 seconds
```

This works fine - you just don't see real-time updates.
