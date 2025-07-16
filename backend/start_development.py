#!/usr/bin/env python3
"""
Cursor Background Agent Startup Script
Run this to start continuous development of the Qloo backend
"""

import os
import sys
import subprocess
import json
from pathlib import Path

def setup_environment():
    """Setup development environment"""
    print("🚀 Setting up Qloo Backend Development Environment")
    
    # Create necessary directories
    dirs_to_create = [
        "logs",
        "agents",
        "tests/__pycache__",
        ".cursor"
    ]
    
    for dir_name in dirs_to_create:
        Path(dir_name).mkdir(parents=True, exist_ok=True)
        print(f"✅ Created directory: {dir_name}")
    
    # Install dependencies
    print("\n📦 Installing dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    print("✅ Dependencies installed")
    
    # Create environment file template
    env_template = """# Qloo Backend Environment Variables
OPENAI_API_KEY=your_openai_key_here
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_TOKEN_FILE=token.json
ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_DEFAULT_VOICE=21m00Tcm4TlvDq8ikWAM
SUPABASE_URL=your_supabase_project_url_here
SUPABASE_KEY=your_supabase_anon_key_here
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key_here
DATABASE_URL=postgresql+asyncpg://postgres:[password]@db.[project-ref].supabase.co:5432/postgres
SECRET_KEY=your_secret_key_here
"""
    
    if not Path(".env").exists():
        with open(".env", "w") as f:
            f.write(env_template)
        print("✅ Created .env template file")
    
    print("\n🎯 Environment setup complete!")

def create_agent_instructions():
    """Create instructions for Cursor agents"""
    instructions = {
        "project_context": "Voice-based scheduling assistant backend",
        "current_priority": "Implement core FastAPI backend with voice processing",
        "next_steps": [
            "Complete main.py with FastAPI setup",
            "Implement data models in shared/models.py",
            "Create intent parser with GPT-4",
            "Build scheduling engine",
            "Add calendar integrations",
            "Implement voice processing",
            "Create comprehensive tests"
        ],
        "testing_strategy": "Run pytest after each implementation",
        "success_metrics": [
            "All endpoints working",
            "Voice processing functional",
            "Calendar integration active",
            "Tests passing >90%"
        ]
    }
    
    with open(".cursor/agent_instructions.json", "w") as f:
        json.dump(instructions, f, indent=2)
    
    print("✅ Created agent instructions")

def main():
    """Main startup function"""
    print("🤖 Starting Cursor Background Agents for Qloo Backend")
    print("=" * 50)
    
    setup_environment()
    create_agent_instructions()
    
    print("\n🎉 Setup complete! Now:")
    print("1. Update your .env file with actual API keys")
    print("2. In Cursor, enable background agents:")
    print("   - Open Command Palette (Ctrl+Shift+P)")
    print("   - Search for 'Cursor: Enable Background Agents'")
    print("   - Select the agent_tasks.md file as reference")
    print("3. The agents will start working automatically!")
    
    print("\n📊 Monitor progress through:")
    print("- Cursor's agent panel")
    print("- Git commits from agents")
    print("- Test output in terminal")
    
    print("\n🔧 Manual commands:")
    print("- Run tests: python -m pytest tests/ -v")
    print("- Start server: python main.py")
    print("- Check logs: tail -f logs/app.log")

if __name__ == "__main__":
    main() 