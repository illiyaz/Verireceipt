#!/usr/bin/env python3
"""
Test Ollama vision model with a simple query.
"""

import requests
import base64
import json
from pathlib import Path


def test_ollama_vision(image_path: str, model: str = "llama3.2-vision:latest"):
    """Test Ollama vision model."""
    
    print(f"Testing Ollama vision model: {model}")
    print(f"Image: {image_path}\n")
    
    # Check if image exists
    if not Path(image_path).exists():
        print(f"❌ Image not found: {image_path}")
        return
    
    # Encode image
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    
    print(f"✅ Image encoded ({len(image_data)} bytes)")
    
    # Test 1: Simple text query (no image)
    print("\n--- Test 1: Simple query (no image) ---")
    payload = {
        "model": model,
        "prompt": "Say hello",
        "stream": False
    }
    
    try:
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=30)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Response: {result.get('response', '')[:100]}")
        else:
            print(f"❌ Error: {response.text[:200]}")
    except Exception as e:
        print(f"❌ Exception: {e}")
    
    # Test 2: Vision query with image
    print("\n--- Test 2: Vision query with image ---")
    payload = {
        "model": model,
        "prompt": "What do you see in this image? Describe it briefly.",
        "images": [image_data],
        "stream": False
    }
    
    try:
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=60)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Response: {result.get('response', '')[:200]}")
        else:
            print(f"❌ Error: {response.text[:500]}")
    except Exception as e:
        print(f"❌ Exception: {e}")
    
    # Test 3: Check model info
    print("\n--- Test 3: Model info ---")
    try:
        response = requests.post(
            "http://localhost:11434/api/show",
            json={"name": model},
            timeout=10
        )
        if response.status_code == 200:
            info = response.json()
            print(f"✅ Model: {info.get('modelfile', 'N/A')[:200]}")
        else:
            print(f"⚠️  Could not get model info: {response.status_code}")
    except Exception as e:
        print(f"⚠️  Exception: {e}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        image_path = "data/raw/Gas_bill.jpeg"
    
    test_ollama_vision(image_path)
