#!/usr/bin/env python3
"""
Check the status of VeriReceipt services.
"""

import requests
import sys


def check_services():
    """Check if all services are running."""
    
    print("\n" + "="*70)
    print("VeriReceipt Service Status Check")
    print("="*70 + "\n")
    
    services = {
        "Web UI": "http://localhost:3000",
        "API Server": "http://localhost:8000/health",
        "API Docs": "http://localhost:8000/docs",
        "Ollama": "http://localhost:11434/api/tags"
    }
    
    for name, url in services.items():
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                print(f"✅ {name:15} - Running ({url})")
            else:
                print(f"⚠️  {name:15} - Status {response.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"❌ {name:15} - Not running")
        except Exception as e:
            print(f"❌ {name:15} - Error: {e}")
    
    print("\n" + "="*70)
    print("Testing Hybrid Analysis Endpoint")
    print("="*70 + "\n")
    
    # Test if we can reach the hybrid endpoint
    try:
        response = requests.options("http://localhost:8000/analyze/hybrid", timeout=2)
        print(f"✅ /analyze/hybrid endpoint is accessible")
        print(f"   Allowed methods: {response.headers.get('allow', 'N/A')}")
    except Exception as e:
        print(f"❌ Cannot reach /analyze/hybrid: {e}")
    
    print("\n" + "="*70)
    print("Current Analysis Status")
    print("="*70 + "\n")
    
    # Check if there are any files being processed
    import os
    from pathlib import Path
    
    temp_dir = Path("/tmp/verireceipt_uploads")
    if temp_dir.exists():
        files = list(temp_dir.glob("*"))
        if files:
            print(f"⏳ Files being processed: {len(files)}")
            for f in files:
                print(f"   - {f.name}")
        else:
            print("✅ No files currently being processed")
    else:
        print("ℹ️  Temp directory not created yet")
    
    # Check recent analysis results
    logs_dir = Path("data/logs")
    if logs_dir.exists():
        log_files = sorted(logs_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if log_files:
            latest = log_files[0]
            import time
            age = time.time() - latest.stat().st_mtime
            print(f"\n📊 Latest analysis log:")
            print(f"   File: {latest.name}")
            print(f"   Age: {age:.0f} seconds ago")
        else:
            print("\nℹ️  No analysis logs found yet")
    
    print("\n" + "="*70)
    print("\n💡 To test the API:")
    print("   1. Open http://localhost:3000 in your browser")
    print("   2. Drag and drop a receipt image")
    print("   3. Click 'Analyze Receipt'")
    print("\n   Or use curl:")
    print('   curl -X POST "http://localhost:8000/analyze/hybrid" \\')
    print('     -F "file=@data/raw/Gas_bill.jpeg"')
    print()


if __name__ == "__main__":
    check_services()
