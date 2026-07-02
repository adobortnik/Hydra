"""
Global Settings API Routes
Manages application-wide settings like API keys, defaults, etc.
"""

from flask import Blueprint, jsonify, request
import json
from pathlib import Path

settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')

SETTINGS_FILE = Path(__file__).parent / 'global_settings.json'

def load_settings():
    """Load settings from JSON file"""
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        else:
            # Return default settings
            return {
                "ai": {
                    "openai_api_key": "",
                    "anthropic_api_key": "",
                    "provider": "openai",
                    "enabled": False
                },
                "automation": {
                    "max_username_attempts": 5,
                    "username_retry_delay": 2,
                    "default_wait_time": 3
                },
                "profile_pictures": {
                    "default_strategy": "rotate",
                    "quality": "high"
                },
                "jap": {
                    "api_key": ""
                }
            }
    except Exception as e:
        print(f"Error loading settings: {e}")
        return {}

def save_settings(settings):
    """Save settings to JSON file"""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

@settings_bp.route('', methods=['GET'])
def get_settings():
    """Get all settings"""
    try:
        settings = load_settings()

        # Mask API keys (only show first 7 chars for security)
        if settings.get('ai', {}).get('openai_api_key'):
            key = settings['ai']['openai_api_key']
            settings['ai']['openai_api_key_masked'] = key[:7] + '...' if len(key) > 7 else '***'
            settings['ai']['has_openai_key'] = bool(key)
        else:
            settings['ai']['has_openai_key'] = False

        if settings.get('ai', {}).get('anthropic_api_key'):
            key = settings['ai']['anthropic_api_key']
            settings['ai']['anthropic_api_key_masked'] = key[:7] + '...' if len(key) > 7 else '***'
            settings['ai']['has_anthropic_key'] = bool(key)
        else:
            settings['ai']['has_anthropic_key'] = False

        # Mask JAP API key too
        jap_key = settings.get('jap', {}).get('api_key', '')
        if jap_key:
            settings.setdefault('jap', {})
            settings['jap']['api_key_masked'] = jap_key[:8] + '...' if len(jap_key) > 8 else '***'
            settings['jap']['has_key'] = True
        else:
            settings.setdefault('jap', {})
            settings['jap']['has_key'] = False

        return jsonify({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('', methods=['POST'])
def update_settings():
    """Update settings"""
    try:
        data = request.json
        current_settings = load_settings()

        # Update settings (merge with existing)
        if 'ai' in data:
            current_settings.setdefault('ai', {})
            current_settings['ai'].update(data['ai'])

        if 'automation' in data:
            current_settings.setdefault('automation', {})
            current_settings['automation'].update(data['automation'])

        if 'profile_pictures' in data:
            current_settings.setdefault('profile_pictures', {})
            current_settings['profile_pictures'].update(data['profile_pictures'])

        if 'jap' in data:
            current_settings.setdefault('jap', {})
            current_settings['jap'].update(data['jap'])
            # Sync to legacy file
            jap_key = data['jap'].get('api_key', '')
            if jap_key:
                _sync_jap_key_to_legacy(jap_key)

        # Save updated settings
        if save_settings(current_settings):
            return jsonify({
                'success': True,
                'message': 'Settings updated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save settings'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/ai', methods=['GET'])
def get_ai_settings():
    """Get AI settings only"""
    try:
        settings = load_settings()
        ai_settings = settings.get('ai', {})

        # Return safe version (without exposing full keys)
        return jsonify({
            'success': True,
            'ai_settings': {
                'provider': ai_settings.get('provider', 'openai'),
                'enabled': ai_settings.get('enabled', False),
                'has_openai_key': bool(ai_settings.get('openai_api_key')),
                'has_anthropic_key': bool(ai_settings.get('anthropic_api_key'))
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/ai/key', methods=['POST'])
def update_ai_key():
    """Update AI API key"""
    try:
        data = request.json
        provider = data.get('provider', 'openai')
        api_key = data.get('api_key', '')

        settings = load_settings()
        settings.setdefault('ai', {})

        if provider == 'openai':
            settings['ai']['openai_api_key'] = api_key
        elif provider == 'anthropic':
            settings['ai']['anthropic_api_key'] = api_key

        settings['ai']['provider'] = provider
        settings['ai']['enabled'] = bool(api_key)

        if save_settings(settings):
            return jsonify({
                'success': True,
                'message': f'{provider.capitalize()} API key updated'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save settings'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings_bp.route('/ai/test', methods=['POST'])
def test_ai_key():
    """Test if AI API key is valid"""
    try:
        data = request.json
        provider = data.get('provider', 'openai')
        api_key = data.get('api_key')

        if not api_key:
            # Load from settings
            settings = load_settings()
            if provider == 'openai':
                api_key = settings.get('ai', {}).get('openai_api_key')
            else:
                api_key = settings.get('ai', {}).get('anthropic_api_key')

        if not api_key:
            return jsonify({
                'success': False,
                'error': 'No API key provided'
            }), 400

        # Test the API key
        import sys
        sys.path.append(str(Path(__file__).parent.parent / 'uiAutomator'))
        from ai_profile_generator import AIProfileGenerator

        generator = AIProfileGenerator(api_key=api_key, provider=provider)

        # Try to generate a test username
        test_username = generator.generate_username("test.account", variations_count=1)

        return jsonify({
            'success': True,
            'message': f'{provider.capitalize()} API key is valid',
            'test_result': test_username
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'API key test failed: {str(e)}'
        }), 400

def get_openai_key():
    """
    Helper function to get OpenAI API key from settings
    Used by other modules
    """
    settings = load_settings()
    return settings.get('ai', {}).get('openai_api_key', '')

def get_ai_config():
    """
    Helper function to get AI configuration
    Returns: dict with 'api_key', 'provider', 'enabled'
    """
    settings = load_settings()
    ai_settings = settings.get('ai', {})

    provider = ai_settings.get('provider', 'openai')

    return {
        'provider': provider,
        'api_key': ai_settings.get(f'{provider}_api_key', ''),
        'enabled': ai_settings.get('enabled', False)
    }


# =============================================================================
# JAP (JustAnotherPanel) API Key — integrated into global settings
# =============================================================================

@settings_bp.route('/jap', methods=['GET'])
def get_jap_settings():
    """Get JustAnotherPanel API key status."""
    settings = load_settings()
    jap_key = settings.get('jap', {}).get('api_key', '')
    return jsonify({
        'success': True,
        'has_key': bool(jap_key),
        'api_key_masked': (jap_key[:8] + '...') if len(jap_key) > 8 else ('***' if jap_key else ''),
    })


@settings_bp.route('/jap', methods=['POST'])
def update_jap_settings():
    """Save JustAnotherPanel API key to global_settings.json."""
    try:
        data = request.json
        api_key = (data.get('api_key') or '').strip()

        settings = load_settings()
        settings.setdefault('jap', {})
        settings['jap']['api_key'] = api_key

        if save_settings(settings):
            # Also write to legacy file so existing code picks it up
            _sync_jap_key_to_legacy(api_key)
            return jsonify({'success': True, 'message': 'JAP API key saved'})
        return jsonify({'success': False, 'error': 'Failed to save'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/jap/test', methods=['POST'])
def test_jap_key():
    """Test if the JAP API key works by fetching services."""
    import requests as _req
    try:
        data = request.json or {}
        api_key = (data.get('api_key') or '').strip()

        if not api_key:
            settings = load_settings()
            api_key = settings.get('jap', {}).get('api_key', '')

        if not api_key:
            return jsonify({'success': False, 'error': 'No JAP API key'}), 400

        resp = _req.post('https://justanotherpanel.com/api/v2',
                         data={'key': api_key, 'action': 'services'}, timeout=10)
        services = resp.json()
        if isinstance(services, list) and len(services) > 0:
            return jsonify({'success': True,
                            'message': f'Key valid — {len(services)} services available'})
        elif isinstance(services, dict) and services.get('error'):
            return jsonify({'success': False, 'error': services['error']}), 400
        else:
            return jsonify({'success': False, 'error': 'Unexpected response'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


def get_jap_api_key():
    """Helper: get JAP API key from global_settings or legacy file."""
    settings = load_settings()
    key = settings.get('jap', {}).get('api_key', '')
    if key:
        return key
    # Fallback: legacy txt file
    import os as _os
    legacy = _os.path.join(_os.path.dirname(__file__), '..', 'data', 'api_keys', 'jap_api_key.txt')
    if _os.path.exists(legacy):
        with open(legacy) as f:
            return f.read().strip()
    return ''


def _sync_jap_key_to_legacy(api_key):
    """Write key to legacy file so simple_app.py / jap_api_utils.py pick it up."""
    import os as _os
    legacy_dir = _os.path.join(_os.path.dirname(__file__), '..', 'data', 'api_keys')
    _os.makedirs(legacy_dir, exist_ok=True)
    legacy_file = _os.path.join(legacy_dir, 'jap_api_key.txt')
    try:
        with open(legacy_file, 'w') as f:
            f.write(api_key)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────
# Spoofing vault location (where source uploads + generated variants live)
# ─────────────────────────────────────────────────────────────────

@settings_bp.route('/spoof-vault', methods=['GET'])
def get_spoof_vault():
    """Current vault root + usage stats. Used by the Settings UI."""
    try:
        from spoof_storage import get_vault_stats
        return jsonify({'success': True, **get_vault_stats()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/spoof-vault/pick-folder', methods=['POST'])
def pick_spoof_vault_folder():
    """Open a NATIVE Windows folder-browser dialog on the host running the
    dashboard. Returns the chosen path so the UI can pre-fill the input.

    Only useful when the operator is physically at the dashboard's host PC —
    if they're browsing via Cloudflare from elsewhere, the dialog opens on
    the home PC where they can't see it (UI keeps a manual text input as
    the primary path).
    """
    import subprocess as _sp
    # PowerShell one-liner — Shell.Application BrowseForFolder. -1 = no parent
    # window (dialog floats free, comes to front).
    ps = (
        "$f = (New-Object -ComObject Shell.Application)"
        ".BrowseForFolder(0,'Pick the Hydra Spoofing Vault folder',0,0); "
        "if ($f) { Write-Output $f.Self.Path }"
    )
    try:
        proc = _sp.run(
            ["powershell", "-NoProfile", "-STA", "-Command", ps],
            capture_output=True, text=True, timeout=120,
        )
        path = (proc.stdout or '').strip()
        if not path:
            return jsonify({'success': True, 'path': '',
                            'message': 'cancelled'})
        return jsonify({'success': True, 'path': path})
    except _sp.TimeoutExpired:
        return jsonify({'success': False,
                        'error': 'picker timed out (dialog left open?)'}), 504
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/spoof-vault', methods=['POST'])
def set_spoof_vault():
    """Change the vault root. Empty / null path reverts to default.
    Body: {"path": "D:/hydra-vault" | "" | null}"""
    try:
        data = request.get_json() or {}
        path = data.get('path', '')
        from spoof_storage import set_vault_root, get_vault_stats
        result = set_vault_root(path)
        if not result['ok']:
            return jsonify({'success': False,
                            'error': result['error'],
                            'root': result['root']}), 400
        # Return fresh stats so the UI can re-render usage immediately
        return jsonify({'success': True, **get_vault_stats()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
