#!/usr/bin/env python3
"""
Virtual Environment Activation Script for K2Think API Proxy

This script activates the Python virtual environment and provides
a Python interpreter context with all required dependencies loaded.
"""

import os
import sys
import subprocess
from pathlib import Path

def main():
    """Main activation function"""
    # Get the project root directory
    project_root = Path(__file__).parent
    venv_path = project_root / "venv"

    # Check if virtual environment exists
    if not venv_path.exists():
        print("❌ Virtual environment not found!")
        print("🔧 Please run: bash scripts/setup.sh")
        sys.exit(1)

    # Check if venv/bin/python exists
    venv_python = venv_path / "bin" / "python"
    if not venv_python.exists():
        print("❌ Virtual environment Python not found!")
        print("🔧 Please run: bash scripts/setup.sh")
        sys.exit(1)

    # Display activation information
    print("✅ K2Think Virtual Environment Activated")
    print(f"📍 Project Root: {project_root}")
    print(f"🐍 Python Path: {venv_python}")
    print(f"📦 Virtual Env: {venv_path}")
    print()
    print("🚀 You can now run Python scripts with all dependencies:")
    print(f"   {venv_python} your_script.py")
    print()
    print("💡 Alternatively, use the activation command:")
    print(f"   source {venv_path}/bin/activate")
    print()

    # If arguments provided, execute them in the venv context
    if len(sys.argv) > 1:
        # Execute the command using venv python
        cmd = [str(venv_python)] + sys.argv[1:]
        print(f"🔧 Executing: {' '.join(cmd)}")
        print()

        try:
            result = subprocess.run(cmd, cwd=project_root)
            sys.exit(result.returncode)
        except KeyboardInterrupt:
            print("\n⚡ Execution interrupted by user")
            sys.exit(130)
        except Exception as e:
            print(f"❌ Error executing command: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()