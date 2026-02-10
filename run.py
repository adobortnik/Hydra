"""
Phone Farm Dashboard Launcher
Uses waitress WSGI server for production stability on Windows.
"""
import sys
import os
import logging

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

from app import create_app

HOST = '0.0.0.0'
PORT = 5055

app = create_app()
print(f"Phone Farm Dashboard starting on http://{HOST}:{PORT}")
print(f"Health: http://127.0.0.1:{PORT}/api/health")

# Auto-start structured bot logging
try:
    from automation.bot_logger import setup_bot_logging
    setup_bot_logging()
    print("Bot structured logging initialized")
except Exception as e:
    print(f"Bot logging setup failed: {e}")

# Auto-start WebSocket server for real-time status
try:
    from automation.ws_server import start_ws_server
    start_ws_server()
    print(f"WebSocket server started on ws://0.0.0.0:5056")
except Exception as e:
    print(f"WebSocket server failed to start: {e}")

sys.stdout.flush()

try:
    from waitress import serve
    serve(app, host=HOST, port=PORT, threads=8, channel_timeout=120)
except ImportError:
    print("waitress not installed, using wsgiref")
    from wsgiref.simple_server import make_server
    httpd = make_server(HOST, PORT, app)
    httpd.serve_forever()
