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
