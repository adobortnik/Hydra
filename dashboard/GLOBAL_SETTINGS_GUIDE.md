# Global Settings System

## Overview

The dashboard now has a global settings system that saves API keys and other configuration, so you don't have to enter them every time.

## Features

- ✅ **OpenAI API Key** - Saved globally, auto-used in quick campaigns
- ✅ **Anthropic API Key** - For Claude AI
- ✅ **Provider Selection** - Choose between OpenAI or Anthropic
- ✅ **Automation Settings** - Default values for retries, delays, etc.
- ✅ **Secure Storage** - API keys stored in `global_settings.json`

## API Endpoints

### Get All Settings
```http
GET /api/settings
```

Response:
```json
{
    "success": true,
    "settings": {
        "ai": {
            "provider": "openai",
            "enabled": true,
            "has_openai_key": true,
            "has_anthropic_key": false,
            "openai_api_key_masked": "sk-proj..."
        },
        "automation": {
            "max_username_attempts": 5,
            "username_retry_delay": 2,
            "default_wait_time": 3
        }
    }
}
```

### Update Settings
```http
POST /api/settings
Content-Type: application/json

{
    "ai": {
        "openai_api_key": "sk-proj-...",
        "provider": "openai",
        "enabled": true
    },
    "automation": {
        "max_username_attempts": 10
    }
}
```

### Update AI API Key (Specific)
```http
POST /api/settings/ai/key
Content-Type: application/json

{
    "provider": "openai",
    "api_key": "sk-proj-..."
}
```

### Test AI API Key
```http
POST /api/settings/ai/test
Content-Type: application/json

{
    "provider": "openai",
    "api_key": "sk-proj-..." // optional, uses saved key if not provided
}
```

Response:
```json
{
    "success": true,
    "message": "OpenAI API key is valid",
    "test_result": "test.username1"
}
```

## How It Works with Quick Campaign

### Before (Required API Key Every Time):
```json
POST /api/profile_automation/quick_campaign
{
    "tag": "chantall",
    "mother_account": "chantall.main",
    "use_ai": true,
    "ai_api_key": "sk-proj-..."  // HAD TO PROVIDE THIS
}
```

### After (Uses Saved Settings):
```json
POST /api/profile_automation/quick_campaign
{
    "tag": "chantall",
    "mother_account": "chantall.main",
    "use_ai": true
    // NO API KEY NEEDED - automatically uses saved key
}
```

If no global API key is saved and `use_ai: true`, you'll get:
```json
{
    "status": "error",
    "message": "AI is enabled but no API key is configured. Please set API key in Settings."
}
```

## File Structure

```
the-livehouse-dashboard/
├── global_settings.json          # Stores all settings
├── settings_routes.py             # API routes for settings
├── simple_app.py                  # Main app (registers settings blueprint)
├── profile_automation_routes.py   # Uses global settings for AI
└── templates/
    └── settings.html              # Settings page UI (TODO)
```

## Settings File Format

`global_settings.json`:
```json
{
    "ai": {
        "openai_api_key": "sk-proj-...",
        "anthropic_api_key": "",
        "provider": "openai",
        "enabled": true
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
```

## Frontend Integration (JavaScript)

### Load Settings on Page Load
```javascript
async function loadSettings() {
    const response = await fetch('/api/settings');
    const data = await response.json();

    if (data.success) {
        // Check if AI is configured
        if (data.settings.ai.has_openai_key) {
            console.log('OpenAI is configured');
            document.getElementById('useAI').disabled = false;
        }

        // Show masked key
        if (data.settings.ai.openai_api_key_masked) {
            document.getElementById('apiKeyDisplay').textContent =
                data.settings.ai.openai_api_key_masked;
        }
    }
}
```

### Save API Key
```javascript
async function saveOpenAIKey(apiKey) {
    const response = await fetch('/api/settings/ai/key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            provider: 'openai',
            api_key: apiKey
        })
    });

    const data = await response.json();
    if (data.success) {
        alert('API key saved!');
    }
}
```

### Test API Key Before Saving
```javascript
async function testAPIKey(apiKey) {
    const response = await fetch('/api/settings/ai/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            provider: 'openai',
            api_key: apiKey
        })
    });

    const data = await response.json();
    if (data.success) {
        alert(`API key is valid! Test result: ${data.test_result}`);
        return true;
    } else {
        alert(`API key is invalid: ${data.error}`);
        return false;
    }
}
```

### Settings Modal UI (Example)
```html
<div id="settingsModal" class="modal">
    <div class="modal-content">
        <h2>Global Settings</h2>

        <div class="setting-section">
            <h3>AI Configuration</h3>

            <label>Provider:</label>
            <select id="aiProvider">
                <option value="openai">OpenAI (GPT-4)</option>
                <option value="anthropic">Anthropic (Claude)</option>
            </select>

            <label>API Key:</label>
            <input type="password" id="apiKey" placeholder="sk-proj-...">
            <button onclick="testAndSaveKey()">Test & Save</button>

            <div id="apiKeyStatus"></div>
        </div>

        <div class="setting-section">
            <h3>Automation Settings</h3>

            <label>Max Username Attempts:</label>
            <input type="number" id="maxAttempts" value="5" min="1" max="20">

            <label>Retry Delay (seconds):</label>
            <input type="number" id="retryDelay" value="2" min="1" max="10">
        </div>

        <button onclick="saveAllSettings()">Save All Settings</button>
    </div>
</div>

<script>
async function testAndSaveKey() {
    const apiKey = document.getElementById('apiKey').value;
    const provider = document.getElementById('aiProvider').value;

    // Test first
    const isValid = await testAPIKey(apiKey);

    // If valid, save
    if (isValid) {
        await saveOpenAIKey(apiKey);
    }
}

async function saveAllSettings() {
    const settings = {
        ai: {
            provider: document.getElementById('aiProvider').value,
            openai_api_key: document.getElementById('apiKey').value,
            enabled: true
        },
        automation: {
            max_username_attempts: parseInt(document.getElementById('maxAttempts').value),
            username_retry_delay: parseInt(document.getElementById('retryDelay').value)
        }
    };

    const response = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
    });

    const data = await response.json();
    if (data.success) {
        alert('Settings saved!');
        window.location.reload();
    }
}
</script>
```

## Usage in Python Code

```python
# In any Python module
from settings_routes import get_ai_config, get_openai_key

# Get full AI config
config = get_ai_config()
# Returns: {'provider': 'openai', 'api_key': 'sk-...', 'enabled': True}

# Just get the API key
api_key = get_openai_key()
# Returns: 'sk-proj-...'

# Use in smart username changer
from smart_username_changer import SmartUsernameChanger

changer = SmartUsernameChanger(
    device,
    ai_api_key=get_openai_key(),  # Auto-loads from settings
    ai_provider=get_ai_config()['provider']
)
```

## Security Notes

1. **API keys are stored in plaintext** in `global_settings.json`
2. **File permissions**: Ensure only authorized users can access the file
3. **Masked in API responses**: Full keys never returned in GET requests
4. **No client-side exposure**: Keys only sent to server, never stored in browser

## Migration from Old System

If you have existing code using `ai_api_key` in requests:

**Old way (still works):**
```json
{
    "use_ai": true,
    "ai_api_key": "sk-..."
}
```

**New way (preferred):**
```json
{
    "use_ai": true
    // API key loaded from global settings automatically
}
```

Both methods work! If `ai_api_key` is provided in request, it overrides global settings.

## Summary

✅ **No more re-entering API keys** - Set once in settings, use everywhere
✅ **Test before saving** - Validate API key before storing
✅ **Backward compatible** - Old method still works
✅ **Automatic fallback** - Uses global settings if not provided in request
✅ **Multiple providers** - Supports OpenAI and Anthropic
✅ **Easy integration** - Just check global settings, no changes to UI needed

Now you can set your OpenAI API key once and all campaigns will use it automatically! 🎉
