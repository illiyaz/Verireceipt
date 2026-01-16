#!/usr/bin/env python3
"""
Launch VeriReceipt Web Demo.

This script starts both:
1. FastAPI backend (port 8000)
2. Web UI server (port 3000)
"""

import subprocess
import sys
import time
import webbrowser
from pathlib import Path
import http.server
import socketserver
import threading


def start_api_server():
    """Start FastAPI backend server."""
    print("🚀 Starting FastAPI backend on http://localhost:8000")
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )


def start_web_server():
    """Start web UI server."""
    PORT = 3000
    web_dir = Path(__file__).parent / "web"
    
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_dir), **kwargs)
        
        def send_header(self, keyword, value):
            """Override to ensure UTF-8 encoding for HTML Content-Type headers."""
            if keyword.lower() == 'content-type' and value.startswith('text/html'):
                value = 'text/html; charset=utf-8'
            super().send_header(keyword, value)
        
        def end_headers(self):
            # Add CORS headers
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', '*')
            # Force no caching for HTML files
            if hasattr(self, 'path') and self.path.endswith('.html'):
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
            super().end_headers()
        
        def log_message(self, format, *args):
            # Suppress logs
            pass
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"🌐 Starting Web UI on http://localhost:{PORT}")
        print(f"\n{'='*60}")
        print("✅ VeriReceipt Web Demo is ready!")
        print(f"{'='*60}")
        print(f"\n📱 Open in browser: http://localhost:{PORT}")
        print(f"📚 API Docs: http://localhost:8000/docs")
        print(f"\n💡 Press Ctrl+C to stop\n")
        
        # Open browser
        time.sleep(2)
        webbrowser.open(f"http://localhost:{PORT}")
        
        httpd.serve_forever()


def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║              VeriReceipt Web Demo Launcher              ║
║         AI-Powered Receipt Fraud Detection              ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # Start API server in background
    start_api_server()
    
    # Wait for API to start
    print("⏳ Waiting for API server to start...")
    time.sleep(3)
    
    # Start web server (blocking)
    try:
        start_web_server()
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down VeriReceipt Web Demo...")
        sys.exit(0)


if __name__ == "__main__":
    main()
