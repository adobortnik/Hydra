"""
Phone Farm Server
==================
Unified launcher that starts:
1. Flask dashboard (with automation API)
2. Task scheduler (background)
3. Device orchestrator (optional, start via API)

Usage:
    python run_server.py
    python run_server.py --port 5000
    python run_server.py --auto-start-orchestrator
"""

import os
import sys
import argparse
import logging

# Ensure phone-farm root is on sys.path
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger("server")


def create_app():
    """Create the Flask app with all blueprints."""
    from flask import Flask

    app = Flask(
        __name__,
        template_folder=os.path.join(ROOT, 'dashboard', 'templates'),
        static_folder=os.path.join(ROOT, 'dashboard', 'static'),
    )
    app.secret_key = os.environ.get('SECRET_KEY', 'phone-farm-secret-2025')

    # Initialize database
    from db.models import init_db
    db_path = init_db()
    log.info("Database: %s", db_path)

    # Register automation API blueprint
    from automation.api import automation_bp
    app.register_blueprint(automation_bp)

    # Register existing dashboard routes if available
    try:
        from dashboard.app import register_dashboard_routes
        register_dashboard_routes(app)
        log.info("Dashboard routes registered")
    except ImportError:
        log.info("No dashboard routes module found, using API-only mode")
        # Add a minimal index route
        from flask import jsonify
        @app.route('/')
        def index():
            return jsonify({
                'name': 'Phone Farm Automation Server',
                'version': '2.0',
                'endpoints': {
                    'devices': '/api/automation/status',
                    'bot_status': '/api/automation/bot/status',
                    'orchestrator': '/api/automation/orchestrator/status',
                    'scheduler': '/api/automation/scheduler/status',
                    'stats': '/api/automation/stats/summary',
                    'adb_devices': '/api/automation/adb-devices',
                }
            })

    return app


def main():
    parser = argparse.ArgumentParser(description='Phone Farm Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    parser.add_argument('--auto-start-scheduler', action='store_true', default=True,
                       help='Auto-start the task scheduler on boot')
    args = parser.parse_args()

    app = create_app()

    # Start task scheduler
    if args.auto_start_scheduler:
        from automation.scheduler import get_scheduler
        scheduler = get_scheduler()
        scheduler.start()
        log.info("Task scheduler started")

    log.info("Starting server on %s:%d", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == '__main__':
    main()
