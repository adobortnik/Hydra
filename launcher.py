"""
Hydra Dashboard Launcher
========================
Double-click to start the Hydra dashboard.
Checks Python version, installs dependencies if needed,
then starts the dashboard and opens browser.
"""
import os
import sys
import subprocess
import time
import webbrowser
import threading
import socket

# ── Configuration ──
REQUIRED_PYTHON = (3, 12)  # Minimum Python version
RECOMMENDED_PYTHON = "3.13"
PORT = 5055
URL = f'http://localhost:{PORT}'

# ── Paths ──
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DASHBOARD_DIR = os.path.join(BASE_DIR, 'dashboard')
RUN_DASHBOARD = os.path.join(DASHBOARD_DIR, 'run_dashboard.py')
SIMPLE_APP = os.path.join(DASHBOARD_DIR, 'simple_app.py')
REQUIREMENTS = os.path.join(BASE_DIR, 'requirements.txt')


def print_banner():
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║         HYDRA DASHBOARD LAUNCHER         ║")
    print("  ╚══════════════════════════════════════════╝")
    print()


def check_python_version():
    """Verify Python version meets requirements."""
    v = sys.version_info
    print(f"  Python:  {v.major}.{v.minor}.{v.micro}")
    
    if (v.major, v.minor) < REQUIRED_PYTHON:
        print(f"\n  ✗ Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ is required!")
        print(f"    Download from: https://www.python.org/downloads/")
        print(f"    Recommended:   Python {RECOMMENDED_PYTHON}")
        return False
    
    print(f"  Status:  ✓ OK")
    return True


def check_dependencies():
    """Check and install missing pip dependencies."""
    if not os.path.exists(REQUIREMENTS):
        print(f"  Deps:    (no requirements.txt found, skipping)")
        return True
    
    print(f"  Deps:    Checking...", end='', flush=True)
    
    # Quick check if Flask is importable (main dependency)
    try:
        import flask
        print(f" ✓ OK (Flask {flask.__version__})")
        return True
    except ImportError:
        pass
    
    print(f" installing...")
    print()
    
    # Install dependencies
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-r', REQUIREMENTS, '--quiet'],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            print(f"  Deps:    ✓ Installed successfully")
            return True
        else:
            print(f"  Deps:    ✗ Installation failed:")
            for line in result.stderr.strip().split('\n')[:5]:
                print(f"           {line}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  Deps:    ✗ Installation timed out")
        return False
    except Exception as e:
        print(f"  Deps:    ✗ Error: {e}")
        return False


def is_port_in_use(port):
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def wait_and_open_browser():
    """Wait for the dashboard to start, then open browser."""
    for _ in range(30):
        time.sleep(1)
        if is_port_in_use(PORT):
            time.sleep(1)
            webbrowser.open(URL)
            return
    print(f"\n  ⚠ Dashboard didn't start within 30 seconds")


def main():
    print_banner()
    
    # Step 1: Check Python
    if not check_python_version():
        input("\n  Press Enter to exit...")
        return
    
    # Step 2: Check if already running
    if is_port_in_use(PORT):
        print(f"  Port:    {PORT} already in use")
        print(f"\n  Dashboard is already running!")
        print(f"  Opening browser...")
        webbrowser.open(URL)
        time.sleep(2)
        return
    
    # Step 3: Check dependencies
    if not check_dependencies():
        input("\n  Press Enter to exit...")
        return
    
    # Step 4: Verify dashboard files
    if not os.path.exists(DASHBOARD_DIR):
        print(f"\n  ✗ dashboard/ folder not found!")
        print(f"    Expected at: {DASHBOARD_DIR}")
        input("\n  Press Enter to exit...")
        return
    
    script = RUN_DASHBOARD if os.path.exists(RUN_DASHBOARD) else SIMPLE_APP
    if not os.path.exists(script):
        print(f"\n  ✗ {os.path.basename(script)} not found!")
        input("\n  Press Enter to exit...")
        return
    
    # Step 5: Start dashboard
    print(f"  Port:    {PORT}")
    print(f"  Script:  {os.path.basename(script)}")
    print(f"\n  Starting dashboard...")
    print(f"  Browser will open automatically when ready.")
    print(f"  Close this window to stop the dashboard.")
    print(f"\n  {'─' * 42}\n")
    
    # Open browser when ready
    browser_thread = threading.Thread(target=wait_and_open_browser, daemon=True)
    browser_thread.start()
    
    # Run the dashboard
    try:
        process = subprocess.Popen(
            [sys.executable, '-u', script],
            cwd=DASHBOARD_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
        )
        
        for line in process.stdout:
            print(f"  {line}", end='')
        
        process.wait()
        
        if process.returncode != 0:
            print(f"\n  Dashboard exited with code {process.returncode}")
            input("\n  Press Enter to exit...")
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except:
            process.kill()
    except Exception as e:
        print(f"\n  Error: {e}")
        input("\n  Press Enter to exit...")


if __name__ == '__main__':
    main()
