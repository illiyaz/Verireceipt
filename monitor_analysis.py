#!/usr/bin/env python3
"""
Real-time analysis monitor.
Shows live updates of what's happening during receipt analysis.
"""

import time
import os
from pathlib import Path
from datetime import datetime
import json


def monitor_temp_files():
    """Monitor temporary upload directory."""
    temp_dir = Path("/tmp/verireceipt_uploads")
    if temp_dir.exists():
        files = list(temp_dir.glob("*"))
        return files
    return []


def monitor_logs():
    """Monitor analysis logs."""
    logs_dir = Path("data/logs")
    if logs_dir.exists():
        log_files = sorted(logs_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if log_files:
            latest = log_files[0]
            age = time.time() - latest.stat().st_mtime
            return latest, age
    return None, None


def check_processes():
    """Check if analysis processes are running."""
    import subprocess
    
    # Check for Python processes doing analysis
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        processes = []
        for line in result.stdout.split('\n'):
            if any(keyword in line.lower() for keyword in ['donut', 'vision', 'ollama', 'analyze']):
                if 'grep' not in line and 'monitor' not in line:
                    processes.append(line.strip())
        
        return processes
    except:
        return []


def print_status():
    """Print current status."""
    print("\n" + "="*80)
    print(f"VeriReceipt Analysis Monitor - {datetime.now().strftime('%H:%M:%S')}")
    print("="*80)
    
    # Check temp files
    temp_files = monitor_temp_files()
    if temp_files:
        print(f"\n🔄 FILES BEING PROCESSED: {len(temp_files)}")
        for f in temp_files:
            age = time.time() - f.stat().st_mtime
            print(f"   📄 {f.name} (processing for {age:.0f}s)")
    else:
        print("\n✅ No files currently being processed")
    
    # Check logs
    latest_log, log_age = monitor_logs()
    if latest_log:
        print(f"\n📊 LATEST ANALYSIS:")
        print(f"   File: {latest_log.name}")
        print(f"   Age: {log_age:.0f} seconds ago")
        
        # Try to read last analysis
        try:
            with open(latest_log, 'r') as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    last = data[-1]
                    if 'hybrid_verdict' in last:
                        verdict = last['hybrid_verdict']
                        print(f"   Verdict: {verdict.get('final_label', 'unknown').upper()}")
                        print(f"   Confidence: {verdict.get('confidence', 0)*100:.1f}%")
        except:
            pass
    
    # Check active processes
    processes = check_processes()
    if processes:
        print(f"\n⚙️  ACTIVE ANALYSIS PROCESSES: {len(processes)}")
        for proc in processes[:3]:  # Show first 3
            # Extract relevant info
            parts = proc.split()
            if len(parts) > 10:
                print(f"   🔧 {' '.join(parts[10:13])}...")
    
    print("\n" + "="*80)


def main():
    """Monitor in real-time."""
    print("""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║         VeriReceipt Real-Time Analysis Monitor          ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝

Monitoring:
  • Temporary upload files
  • Analysis processes
  • Recent logs

Press Ctrl+C to stop
    """)
    
    try:
        while True:
            print_status()
            
            # Check for temp files
            temp_files = monitor_temp_files()
            if temp_files:
                print("\n💡 Analysis in progress! Checking engines...")
                
                # Give hints about what might be running
                age = time.time() - temp_files[0].stat().st_mtime
                
                if age < 5:
                    print("   🔄 Likely: Rule-Based Engine (fast, 2-5s)")
                elif age < 15:
                    print("   🔄 Likely: DONUT Transformer (medium, 5-15s)")
                else:
                    print("   🔄 Likely: Vision LLM (slow, 10-30s)")
                
                print(f"   ⏱️  Processing time: {age:.0f}s")
            
            time.sleep(2)  # Update every 2 seconds
            
    except KeyboardInterrupt:
        print("\n\n👋 Monitoring stopped")


if __name__ == "__main__":
    main()
