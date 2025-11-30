#!/usr/bin/env python3
"""
Check if an analysis is currently running.
"""

import requests
import time
from pathlib import Path
import subprocess


def check_temp_files():
    """Check for files being processed."""
    temp_dir = Path("/tmp/verireceipt_uploads")
    if temp_dir.exists():
        files = list(temp_dir.glob("*"))
        if files:
            print(f"\n🔄 ANALYSIS IN PROGRESS!")
            print(f"   Files being processed: {len(files)}")
            for f in files:
                age = time.time() - f.stat().st_mtime
                print(f"   📄 {f.name}")
                print(f"   ⏱️  Processing for: {age:.1f}s")
                
                # Estimate which engine
                if age < 5:
                    print(f"   🔧 Likely running: Rule-Based Engine (2-5s)")
                elif age < 15:
                    print(f"   🔧 Likely running: DONUT Transformer (5-15s)")
                else:
                    print(f"   🔧 Likely running: Vision LLM (10-30s)")
            return True
        else:
            print("\n✅ No files in temp directory")
            return False
    else:
        print("\n✅ Temp directory doesn't exist yet")
        return False


def check_api_health():
    """Check if API is responding."""
    try:
        response = requests.get("http://localhost:8000/health", timeout=2)
        if response.status_code == 200:
            print("\n✅ API Server: Healthy")
            return True
        else:
            print(f"\n⚠️  API Server: Status {response.status_code}")
            return False
    except requests.exceptions.Timeout:
        print("\n⏳ API Server: Busy (might be processing)")
        return "busy"
    except requests.exceptions.ConnectionError:
        print("\n❌ API Server: Not responding")
        return False


def check_ollama():
    """Check Ollama status."""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            print("✅ Ollama: Running")
            return True
        else:
            print(f"⚠️  Ollama: Status {response.status_code}")
            return False
    except:
        print("❌ Ollama: Not running")
        return False


def check_python_processes():
    """Check for active Python analysis processes."""
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        # Look for analysis-related processes
        keywords = ['analyze_receipt', 'donut', 'vision_llm', 'extract_receipt']
        active = []
        
        for line in result.stdout.split('\n'):
            if any(kw in line for kw in keywords):
                if 'grep' not in line and 'check_current' not in line:
                    active.append(line.strip())
        
        if active:
            print(f"\n🔧 ACTIVE ANALYSIS PROCESSES: {len(active)}")
            for proc in active[:3]:
                print(f"   {proc[:100]}...")
            return True
        else:
            print("\n✅ No active analysis processes")
            return False
            
    except:
        return False


def main():
    print("\n" + "="*80)
    print("VeriReceipt - Current Analysis Status")
    print("="*80)
    
    # Check all indicators
    has_temp_files = check_temp_files()
    api_status = check_api_health()
    has_ollama = check_ollama()
    has_processes = check_python_processes()
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    if has_temp_files:
        print("\n🔄 ANALYSIS IS RUNNING!")
        print("   Check the web UI for real-time updates")
    elif api_status == "busy":
        print("\n⏳ API IS BUSY - Analysis might be running")
        print("   The API is not responding, likely processing a request")
    elif has_processes:
        print("\n🔧 ANALYSIS PROCESSES DETECTED")
        print("   Python processes are running analysis code")
    else:
        print("\n✅ NO ANALYSIS CURRENTLY RUNNING")
        print("   System is idle and ready for new requests")
    
    if not has_ollama:
        print("\n⚠️  WARNING: Ollama is not running!")
        print("   Vision LLM analysis will fail")
        print("   Start with: ollama serve")
    
    print("\n💡 To start a new analysis:")
    print("   1. Open http://localhost:3000")
    print("   2. Upload a receipt")
    print("   3. Click 'Analyze Receipt'")
    print("   4. Watch real-time updates!")
    
    print()


if __name__ == "__main__":
    main()
