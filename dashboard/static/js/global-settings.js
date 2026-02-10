// Global Settings Management
// Handles loading, saving, and testing API keys

// Load settings when page loads
document.addEventListener('DOMContentLoaded', function() {
    loadGlobalSettings();
    checkSavedAPIKey(); // Check if API key is saved for Quick Campaign
});

// Load global settings
async function loadGlobalSettings() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();

        if (data.success) {
            const settings = data.settings;

            // AI Settings
            if (settings.ai) {
                // Provider
                if (settings.ai.provider) {
                    document.getElementById('settingsAIProvider').value = settings.ai.provider;
                }

                // OpenAI Key Status
                if (settings.ai.has_openai_key) {
                    document.getElementById('openaiKeyStatus').textContent = settings.ai.openai_api_key_masked;
                    document.getElementById('openaiKeyStatus').className = 'badge bg-success ms-2';
                } else {
                    document.getElementById('openaiKeyStatus').textContent = 'Not Set';
                    document.getElementById('openaiKeyStatus').className = 'badge bg-secondary ms-2';
                }

                // Anthropic Key Status
                if (settings.ai.has_anthropic_key) {
                    document.getElementById('anthropicKeyStatus').textContent = settings.ai.anthropic_api_key_masked;
                    document.getElementById('anthropicKeyStatus').className = 'badge bg-success ms-2';
                } else {
                    document.getElementById('anthropicKeyStatus').textContent = 'Not Set';
                    document.getElementById('anthropicKeyStatus').className = 'badge bg-secondary ms-2';
                }
            }

            // Automation Settings
            if (settings.automation) {
                if (settings.automation.max_username_attempts) {
                    document.getElementById('settingsMaxAttempts').value = settings.automation.max_username_attempts;
                }
                if (settings.automation.username_retry_delay) {
                    document.getElementById('settingsRetryDelay').value = settings.automation.username_retry_delay;
                }
            }

            // Profile Picture Settings
            if (settings.profile_pictures && settings.profile_pictures.default_strategy) {
                document.getElementById('settingsPictureStrategy').value = settings.profile_pictures.default_strategy;
            }
        }
    } catch (error) {
        console.error('Error loading settings:', error);
    }
}

// Save global settings
async function saveGlobalSettings() {
    try {
        const openAIKey = document.getElementById('settingsOpenAIKey').value.trim();
        const anthropicKey = document.getElementById('settingsAnthropicKey').value.trim();
        const provider = document.getElementById('settingsAIProvider').value;
        const maxAttempts = parseInt(document.getElementById('settingsMaxAttempts').value);
        const retryDelay = parseInt(document.getElementById('settingsRetryDelay').value);
        const pictureStrategy = document.getElementById('settingsPictureStrategy').value;

        const settings = {
            ai: {
                provider: provider,
                enabled: !!(openAIKey || anthropicKey)
            },
            automation: {
                max_username_attempts: maxAttempts,
                username_retry_delay: retryDelay
            },
            profile_pictures: {
                default_strategy: pictureStrategy
            }
        };

        // Only include API keys if they were entered
        if (openAIKey) {
            settings.ai.openai_api_key = openAIKey;
        }
        if (anthropicKey) {
            settings.ai.anthropic_api_key = anthropicKey;
        }

        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });

        const data = await response.json();

        if (data.success) {
            // Show success message
            showSettingsAlert('Settings saved successfully!', 'success');

            // Clear password fields for security
            document.getElementById('settingsOpenAIKey').value = '';
            document.getElementById('settingsAnthropicKey').value = '';

            // Reload settings to update status badges
            setTimeout(() => {
                loadGlobalSettings();
                checkSavedAPIKey(); // Update Quick Campaign section
            }, 500);
        } else {
            showSettingsAlert(`Error: ${data.error}`, 'danger');
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        showSettingsAlert(`Error saving settings: ${error.message}`, 'danger');
    }
}

// Test API Key
async function testAPIKey(provider) {
    const keyInput = provider === 'openai'
        ? document.getElementById('settingsOpenAIKey')
        : document.getElementById('settingsAnthropicKey');

    const apiKey = keyInput.value.trim();

    if (!apiKey) {
        showSettingsAlert('Please enter an API key to test', 'warning');
        return;
    }

    try {
        showSettingsAlert(`Testing ${provider} API key...`, 'info');

        const response = await fetch('/api/settings/ai/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider: provider,
                api_key: apiKey
            })
        });

        const data = await response.json();

        if (data.success) {
            showSettingsAlert(
                `✓ ${data.message}<br>Test result: ${data.test_result}`,
                'success'
            );
        } else {
            showSettingsAlert(`✗ ${data.error}`, 'danger');
        }
    } catch (error) {
        console.error('Error testing API key:', error);
        showSettingsAlert(`Error testing API key: ${error.message}`, 'danger');
    }
}

// Show alert in settings modal
function showSettingsAlert(message, type) {
    const alertDiv = document.getElementById('settingsTestResult');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.innerHTML = message;
    alertDiv.style.display = 'block';

    // Auto-hide after 5 seconds for success messages
    if (type === 'success') {
        setTimeout(() => {
            alertDiv.style.display = 'none';
        }, 5000);
    }
}

// Check if API key is saved (for Quick Campaign modal)
async function checkSavedAPIKey() {
    try {
        const response = await fetch('/api/settings/ai');
        const data = await response.json();

        if (data.success && data.ai_settings) {
            const hasKey = data.ai_settings.has_openai_key || data.ai_settings.has_anthropic_key;

            if (hasKey) {
                // Show "saved key" status
                document.getElementById('keyNotSaved').style.display = 'none';
                document.getElementById('keySaved').style.display = 'inline';
                document.getElementById('loadKeyBtn').disabled = false;
            } else {
                // Show "no key" status
                document.getElementById('keyNotSaved').style.display = 'inline';
                document.getElementById('keySaved').style.display = 'none';
                document.getElementById('loadKeyBtn').disabled = true;
            }
        }
    } catch (error) {
        console.error('Error checking saved API key:', error);
    }
}

// Load saved API key into Quick Campaign modal
async function loadSavedAPIKey() {
    try {
        const response = await fetch('/api/settings/ai');
        const data = await response.json();

        if (data.success && data.ai_settings) {
            if (data.ai_settings.has_openai_key || data.ai_settings.has_anthropic_key) {
                // Don't actually fill the field - backend will use saved key automatically
                document.getElementById('aiApiKey').placeholder = 'Using saved API key from Settings';
                alert('Using saved API key from Settings. Leave this field blank to use the saved key.');
            } else {
                alert('No API key saved. Please save one in Settings first.');
            }
        }
    } catch (error) {
        console.error('Error loading saved API key:', error);
        alert('Error loading saved API key. Please try again.');
    }
}

// Show/hide API key status when AI toggle changes
function toggleAIKey() {
    const useAI = document.getElementById('useAI').checked;
    const aiKeySection = document.getElementById('aiKeySection');

    if (useAI) {
        aiKeySection.style.display = 'block';
        checkSavedAPIKey(); // Check if key is saved when toggled on
    } else {
        aiKeySection.style.display = 'none';
    }
}
