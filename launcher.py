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
import io

# Fix encoding for Windows (cp1250 can't handle unicode box chars)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Fix for PyInstaller --windowed mode (no stdin/stdout)
if sys.stdin is None:
    sys.stdin = io.StringIO()
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

# â”€â”€ Configuration â”€â”€
REQUIRED_PYTHON = (3, 12)  # Minimum Python version
RECOMMENDED_PYTHON = "3.13"
PORT = 5055
URL = f'http://localhost:{PORT}'

# â”€â”€ Paths â”€â”€
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
    print("  â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—")
    print("  â•‘         HYDRA DASHBOARD LAUNCHER         â•‘")
    print("  â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•ť")
    print()


def check_python_version():
    """Verify Python version meets requirements."""
    v = sys.version_info
    print(f"  Python:  {v.major}.{v.minor}.{v.micro}")
    
    if (v.major, v.minor) < REQUIRED_PYTHON:
        print(f"\n  âś— Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ is required!")
        print(f"    Download from: https://www.python.org/downloads/")
        print(f"    Recommended:   Python {RECOMMENDED_PYTHON}")
        return False
    
    print(f"  Status:  âś“ OK")
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
        print(f" âś“ OK (Flask {flask.__version__})")
        return True
    except ImportError:
        pass
    
    print(f" installing...")
    print()
    
    # Install dependencies
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-r', REQUIREMENTS, '--quiet'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=120,
        )
        if result.returncode == 0:
            print(f"  Deps:    âś“ Installed successfully")
            return True
        else:
            print(f"  Deps:    âś— Installation failed:")
            for line in result.stderr.strip().split('\n')[:5]:
                print(f"           {line}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  Deps:    âś— Installation timed out")
        return False
    except Exception as e:
        print(f"  Deps:    âś— Error: {e}")
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
    print(f"\n  âš  Dashboard didn't start within 30 seconds")


def main():
    print_banner()
    
    # Step 1: Check Python
    if not check_python_version():
        time.sleep(10)  # Show error for 10 seconds
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
        time.sleep(10)  # Show error for 10 seconds
        return
    
    # Step 4: Verify dashboard files
    if not os.path.exists(DASHBOARD_DIR):
        print(f"\n  âś— dashboard/ folder not found!")
        print(f"    Expected at: {DASHBOARD_DIR}")
        time.sleep(10)  # Show error for 10 seconds
        return
    
    script = RUN_DASHBOARD if os.path.exists(RUN_DASHBOARD) else SIMPLE_APP
    if not os.path.exists(script):
        print(f"\n  âś— {os.path.basename(script)} not found!")
        time.sleep(10)  # Show error for 10 seconds
        return
    
    # Step 5: Start dashboard
    print(f"  Port:    {PORT}")
    print(f"  Script:  {os.path.basename(script)}")
    print(f"\n  Starting dashboard...")
    print(f"  Browser will open automatically when ready.")
    print(f"  Close this window to stop the dashboard.")
    print(f"\n  {'â”€' * 42}\n")
    
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
            time.sleep(10)  # Show error for 10 seconds
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except:
            process.kill()
    except Exception as e:
        print(f"\n  Error: {e}")
        time.sleep(10)  # Show error for 10 seconds


if __name__ == '__main__':
    main()

