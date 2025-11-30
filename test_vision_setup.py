#!/usr/bin/env python3
"""
Test Ollama vision setup and connectivity.
"""

import requests
import json


def check_ollama_running():
    """Check if Ollama server is running."""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            print("✅ Ollama is running!")
            print(f"   Found {len(models)} models")
            
            # Check for vision models
            vision_models = [m for m in models if "vision" in m.get("name", "").lower() or "vl" in m.get("name", "").lower()]
            
            if vision_models:
                print(f"\n✅ Vision models available:")
                for model in vision_models:
                    name = model.get("name", "unknown")
                    size = model.get("size", 0) / (1024**3)  # Convert to GB
                    print(f"   - {name} ({size:.1f} GB)")
                return True, vision_models
            else:
                print("\n⚠️  No vision models found!")
                print("   Install one with: ollama pull llama3.2-vision")
                return True, []
        else:
            print(f"❌ Ollama returned status {response.status_code}")
            return False, []
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Ollama")
        print("\nTo start Ollama:")
        print("   1. Open a new terminal")
        print("   2. Run: ollama serve")
        print("   3. Keep it running in the background")
        return False, []
    except Exception as e:
        print(f"❌ Error: {e}")
        return False, []


def test_simple_vision_query(model="llama3.2-vision:latest"):
    """Test a simple vision query."""
    print(f"\n🔍 Testing vision model: {model}")
    print("   This will take 10-30 seconds...")
    
    # Create a simple test prompt (no image for now)
    payload = {
        "model": model,
        "prompt": "Hello, can you see images?",
        "stream": False
    }
    
    try:
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()
            answer = result.get("response", "").strip()
            print(f"\n✅ Model responded!")
            print(f"   Response: {answer[:100]}...")
            return True
        else:
            print(f"\n❌ Error: {response.status_code}")
            print(f"   {response.text[:200]}")
            return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def main():
    print("=" * 80)
    print("VeriReceipt - Vision LLM Setup Test")
    print("=" * 80)
    print()
    
    # Check Ollama
    running, vision_models = check_ollama_running()
    
    if not running:
        print("\n" + "=" * 80)
        print("❌ Setup incomplete - Ollama is not running")
        print("=" * 80)
        return
    
    if not vision_models:
        print("\n" + "=" * 80)
        print("⚠️  Setup incomplete - No vision models installed")
        print("=" * 80)
        print("\nTo install a vision model:")
        print("   ollama pull llama3.2-vision")
        return
    
    # Test a simple query
    model_name = vision_models[0].get("name", "llama3.2-vision:latest")
    success = test_simple_vision_query(model_name)
    
    print("\n" + "=" * 80)
    if success:
        print("✅ Setup Complete!")
        print("=" * 80)
        print("\nYou can now run:")
        print("   python compare_engines.py")
        print("   python -m app.pipelines.vision_llm data/raw/Gas_bill.jpeg")
    else:
        print("⚠️  Setup incomplete - Model test failed")
        print("=" * 80)
        print("\nTroubleshooting:")
        print("   1. Make sure Ollama is running: ollama serve")
        print("   2. Try pulling the model again: ollama pull llama3.2-vision")
        print("   3. Check Ollama logs for errors")


if __name__ == "__main__":
    main()
