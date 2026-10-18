# Automated run-through script for Final Dashboard (webapp/server.py), will work on Windows, MacOS and Linux. Intended as install step process skip (for our team testing)
# Windows may still require "Set-ExecutionPolicy RemoteSigned -Scope CurrentUser" to be run to activate the venv.

# Note that the install steps outlined in our README work correctly, this is just an ease of use file for testing. 

# Creates the virtual environment (.venv), installs required dependencies, and also runs the build_cache.py script in webapp/ directory.
# Will need to enter "deactivate" into the terminal if venv is still active, and then manually delete these folders (.venv, webapp/"cache" (not parent webapp directory)) when finished. 

import os
import sys
import subprocess
import webbrowser

def main():
    print("=======================================================================")
    print("                 HIT401 Group 34 Capstone Project                    ")
    print("Interactive Groundwater & Climate Explorer for the Northern Territory")
    print("=======================================================================")

    # Determine the paths based on operating system (Windows, MacOS, Linux)
    if sys.platform == "win32":
        venv_python = os.path.join(".venv", "Scripts", "python.exe")
    else:
        # Using if/else as Windows uses 'Scripts', while macOS and Linux use 'bin' instead
        venv_python = os.path.join(".venv", "bin", "python")

    requirements_path = os.path.join("webapp", "requirements.txt")
    cache_file = os.path.join("webapp", "cache", "bores.parquet")

    # Check if the virtual environment exists already, if not, create it. 
    if not os.path.exists(venv_python):
        print("[INFO] Virtual environment not found. Creating it now...")
        try:
            subprocess.run([sys.executable, "-m", "venv", ".venv"], check=True)
            print("[INFO] Upgrading pip...")
            subprocess.run([venv_python, "-m", "pip", "install", "--upgrade", "pip"], check=True)
            
            if os.path.exists(requirements_path):
                print(f"[INFO] Installing dependencies from {requirements_path}...")
                subprocess.run([venv_python, "-m", "pip", "install", "-r", requirements_path], check=True)
            else:
                print(f"[WARNING] {requirements_path} not found. Skipping dependency installation.")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed during environment setup: {e}")
            input("\nPress Enter to exit...")
            sys.exit(1)
    else:
        print("[INFO] Virtual environment found. Proceeding...")

    # Check if the cache exists already, if not, create it too.
    if not os.path.exists(cache_file):
        print("[INFO] Data cache not found. Building cache now...")
        try:
            subprocess.run([venv_python, os.path.join("webapp", "build_cache.py")], check=True)
        except subprocess.CalledProcessError:
            print("[ERROR] Failed to build the data cache.")
            input("\nPress Enter to exit...")
            sys.exit(1)

    # Launch the browser and the server. Note: May need to manually open the local host URL sometimes. 
    print("\n[INFO] Starting web application server...")
    print("[INFO] Opening http://127.0.0.1:8000 in your browser...")
    
    # Safely opens the default system browser on any OS
    webbrowser.open("http://127.0.0.1:8000")

    # Run the 'server.py' file from webapp/server.py automatically. 
    try:
        subprocess.run([venv_python, os.path.join("webapp", "server.py")], check=True)
    except KeyboardInterrupt:
        print("\n[INFO] Server stopped by user.")
    except subprocess.CalledProcessError:
        print("[ERROR] Web application server crashed.")
        input("\nPress Enter to exit...")
        sys.exit(1)

if __name__ == "__main__":
    main()