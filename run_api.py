#!/usr/bin/env python3
"""
Startup script for VeriReceipt FastAPI server.

Usage:
    python run_api.py

Or with uvicorn directly:
    uvicorn app.api.main:app --reload --host 0.0.0.0 --port 9000
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,  # Auto-reload on code changes (dev mode)
        log_level="info",
    )
