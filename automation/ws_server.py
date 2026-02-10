"""
WebSocket Server for Real-Time Status Updates
===============================================
Runs alongside the Flask dashboard on port 5056.
Broadcasts bot status, action events, and device state changes
to connected dashboard clients.

Usage:
    # Auto-started by run.py, or manually:
    python -m automation.ws_server

Events emitted:
    bot_status    - Bot engine state change (starting/running/idle/error)
    action_event  - Individual action completed (follow/unfollow/like/etc.)
    device_status - Device connection state change
    session_event - Bot session start/end
    stats_update  - Periodic stats refresh
"""

import asyncio
import json
import logging
import threading
import time
import datetime
from collections import deque

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Global event bus — thread-safe queue for broadcasting
# ---------------------------------------------------------------------------

_clients = set()
_event_queue = deque(maxlen=500)  # Buffer recent events
_broadcast_lock = threading.Lock()
_ws_loop = None
_ws_thread = None
_running = False

WS_HOST = '0.0.0.0'
WS_PORT = 5056


def broadcast_event(event_type, data=None):
    """
    Publish an event from any thread.
    Called by bot_engine, actions, device_connection, etc.

    Args:
        event_type: str — 'bot_status', 'action_event', 'device_status', etc.
        data: dict — event payload
    """
    event = {
        'type': event_type,
        'data': data or {},
        'timestamp': datetime.datetime.now().isoformat(),
    }

    with _broadcast_lock:
        _event_queue.append(event)

    # Schedule async broadcast if loop is running
    if _ws_loop and _ws_loop.is_running():
        asyncio.run_coroutine_threadsafe(_async_broadcast(event), _ws_loop)


async def _async_broadcast(event):
    """Broadcast event to all connected WebSocket clients."""
    if not _clients:
        return

    message = json.dumps(event)
    disconnected = set()

    for ws in _clients.copy():
        try:
            await ws.send(message)
        except Exception:
            disconnected.add(ws)

    # Clean up disconnected clients
    for ws in disconnected:
        _clients.discard(ws)


# ---------------------------------------------------------------------------
#  WebSocket handler
# ---------------------------------------------------------------------------

async def _ws_handler(websocket):
    """Handle a single WebSocket connection."""
    _clients.add(websocket)
    client_addr = websocket.remote_address
    log.info("[WS] Client connected: %s", client_addr)

    # Send recent events as history (last 50)
    try:
        with _broadcast_lock:
            recent = list(_event_queue)[-50:]
        for event in recent:
            await websocket.send(json.dumps(event))
    except Exception:
        pass

    # Send current status snapshot
    try:
        snapshot = _get_status_snapshot()
        await websocket.send(json.dumps({
            'type': 'status_snapshot',
            'data': snapshot,
            'timestamp': datetime.datetime.now().isoformat(),
        }))
    except Exception:
        pass

    try:
        # Keep connection alive, listen for client messages
        async for message in websocket:
            try:
                msg = json.loads(message)
                cmd = msg.get('command')

                if cmd == 'ping':
                    await websocket.send(json.dumps({
                        'type': 'pong',
                        'timestamp': datetime.datetime.now().isoformat(),
                    }))

                elif cmd == 'get_status':
                    snapshot = _get_status_snapshot()
                    await websocket.send(json.dumps({
                        'type': 'status_snapshot',
                        'data': snapshot,
                        'timestamp': datetime.datetime.now().isoformat(),
                    }))

                elif cmd == 'get_history':
                    limit = msg.get('limit', 50)
                    with _broadcast_lock:
                        history = list(_event_queue)[-limit:]
                    await websocket.send(json.dumps({
                        'type': 'event_history',
                        'data': history,
                        'timestamp': datetime.datetime.now().isoformat(),
                    }))

            except json.JSONDecodeError:
                pass

    except Exception as e:
        log.debug("[WS] Client disconnected: %s (%s)", client_addr, e)
    finally:
        _clients.discard(websocket)
        log.info("[WS] Client disconnected: %s (total: %d)",
                 client_addr, len(_clients))


def _get_status_snapshot():
    """Get current status from DB for initial client sync."""
    try:
        from automation.actions.helpers import get_db
        conn = get_db()

        # Bot status per device
        bot_rows = conn.execute("""
            SELECT bs.*, d.device_name
            FROM bot_status bs
            LEFT JOIN devices d ON d.device_serial = bs.device_serial
            ORDER BY bs.device_serial
        """).fetchall()

        # Today's action summary
        today = datetime.date.today().isoformat()
        action_rows = conn.execute("""
            SELECT action_type, COUNT(*) as cnt
            FROM action_history
            WHERE timestamp >= ? AND success=1
            GROUP BY action_type
        """, (today,)).fetchall()

        # Active sessions
        session_rows = conn.execute("""
            SELECT device_serial, username, session_start, status
            FROM account_sessions
            WHERE status='running'
            ORDER BY session_start DESC
        """).fetchall()

        conn.close()

        return {
            'bot_status': [dict(r) for r in bot_rows],
            'today_actions': {r['action_type']: r['cnt'] for r in action_rows},
            'active_sessions': [dict(r) for r in session_rows],
            'connected_clients': len(_clients),
        }

    except Exception as e:
        log.error("[WS] Status snapshot error: %s", e)
        return {'error': str(e)}


# ---------------------------------------------------------------------------
#  Periodic stats broadcaster
# ---------------------------------------------------------------------------

async def _stats_broadcaster():
    """Periodically broadcast stats to all clients."""
    while _running:
        await asyncio.sleep(10)  # Every 10 seconds
        if _clients:
            try:
                snapshot = _get_status_snapshot()
                event = {
                    'type': 'stats_update',
                    'data': snapshot,
                    'timestamp': datetime.datetime.now().isoformat(),
                }
                message = json.dumps(event)
                disconnected = set()
                for ws in _clients.copy():
                    try:
                        await ws.send(message)
                    except Exception:
                        disconnected.add(ws)
                for ws in disconnected:
                    _clients.discard(ws)
            except Exception as e:
                log.debug("[WS] Stats broadcast error: %s", e)


# ---------------------------------------------------------------------------
#  Server lifecycle
# ---------------------------------------------------------------------------

async def _run_server():
    """Run the WebSocket server."""
    import websockets
    global _running

    _running = True
    log.info("[WS] Starting WebSocket server on ws://%s:%d", WS_HOST, WS_PORT)

    # Start stats broadcaster
    stats_task = asyncio.create_task(_stats_broadcaster())

    try:
        async with websockets.serve(_ws_handler, WS_HOST, WS_PORT,
                                     ping_interval=30, ping_timeout=10):
            log.info("[WS] WebSocket server running on ws://%s:%d", WS_HOST, WS_PORT)
            # Run forever until stopped
            while _running:
                await asyncio.sleep(1)
    except Exception as e:
        log.error("[WS] Server error: %s", e)
    finally:
        _running = False
        stats_task.cancel()
        log.info("[WS] WebSocket server stopped")


def start_ws_server():
    """Start the WebSocket server in a background thread."""
    global _ws_loop, _ws_thread, _running

    if _running:
        log.info("[WS] Already running")
        return

    def _thread_target():
        global _ws_loop
        _ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_ws_loop)
        _ws_loop.run_until_complete(_run_server())

    _ws_thread = threading.Thread(target=_thread_target, daemon=True,
                                   name="WebSocket-Server")
    _ws_thread.start()
    log.info("[WS] Server thread started")


def stop_ws_server():
    """Stop the WebSocket server."""
    global _running
    _running = False
    log.info("[WS] Server stop requested")


def get_ws_status():
    """Get WebSocket server status."""
    return {
        'running': _running,
        'port': WS_PORT,
        'connected_clients': len(_clients),
        'buffered_events': len(_event_queue),
    }


# ---------------------------------------------------------------------------
#  CLI entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print(f"Starting WebSocket server on ws://0.0.0.0:{WS_PORT}")
    asyncio.run(_run_server())
