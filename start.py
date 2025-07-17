#!/usr/bin/env python3
"""
Qloo Voice Scheduler - Startup Script
"""

import os
import sys
import subprocess
import threading
import time
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import fastapi
        import streamlit
        import openai
        print("✅ All dependencies are installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Please run: pip install -r requirements.txt")
        return False

def check_env_file():
    """Check if .env file exists"""
    if not os.path.exists('.env'):
        print("⚠️  .env file not found")
        print("Please copy .env.example to .env and configure your API keys")
        return False
    print("✅ .env file found")
    return True

def start_backend():
    """Start the FastAPI backend"""
    print("🚀 Starting FastAPI backend...")
    subprocess.run([sys.executable, "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"])

def start_frontend():
    """Start the Streamlit frontend"""
    print("🚀 Starting Streamlit frontend...")
    time.sleep(2)  # Give backend time to start
    subprocess.run([sys.executable, "-m", "streamlit", "run", "mobile_app.py", "--server.port", "8501"])

def main():
    """Main startup function"""
    print("🗓️  Qloo Voice Scheduler")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check environment
    if not check_env_file():
        print("You can still run the app, but some features may not work without API keys")
    
    print("\n🚀 Starting services...")
    print("Backend will be available at: http://localhost:8000")
    print("Frontend will be available at: http://localhost:8501")
    print("\nPress Ctrl+C to stop both services")
    
    # Start backend in a separate thread
    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()
    
    # Start frontend in main thread
    try:
        start_frontend()
    except KeyboardInterrupt:
        print("\n👋 Shutting down services...")
        sys.exit(0)

if __name__ == "__main__":
    main()