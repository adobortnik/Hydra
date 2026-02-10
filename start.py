"""Debug launcher."""
import sys
import os
import traceback

# Suppress werkzeug writing to stderr
os.environ['WERKZEUG_RUN_MAIN'] = 'true'

# First check if port is available
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.bind(('0.0.0.0', 5055))
    sock.close()
    print("Port 5055 is available")
except OSError as e:
    print(f"Port 5055 NOT available: {e}")
    sock.close()
    sys.exit(1)

try:
    from app import create_app
    app = create_app()
    print("App created successfully")
    print("Starting server on 0.0.0.0:5055 ...")
    sys.stdout.flush()
    
    # Use waitress instead of Flask dev server (no stderr warnings)
    try:
        from waitress import serve
        print("Using waitress WSGI server")
        sys.stdout.flush()
        serve(app, host='0.0.0.0', port=5055, threads=8)
    except ImportError:
        print("waitress not installed, using Flask dev server")
        sys.stdout.flush()
        # Redirect stderr to devnull to prevent PowerShell from killing us
        devnull = open(os.devnull, 'w')
        old_stderr = sys.stderr
        sys.stderr = devnull
        app.run(host='0.0.0.0', port=5055, debug=False, use_reloader=False, threaded=True)
except Exception:
    traceback.print_exc()
    sys.exit(1)
