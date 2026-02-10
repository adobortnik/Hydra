# Smart Username Changer - Intelligent Username Management with AI

## Overview

The Smart Username Changer automatically handles "username taken" scenarios by:
1. **Detecting** when Instagram rejects a username
2. **Generating** intelligent variations using AI or algorithms
3. **Retrying** automatically until successful or max attempts reached

## Features

### ✅ Automatic Error Detection
- Detects "This username isn't available" messages
- Recognizes "already taken" errors
- Handles all Instagram username error variants

### ✅ Intelligent Variation Generation
- **AI-Powered** (Optional): Uses OpenAI/Claude to generate smart variations based on mother account
- **Algorithmic Fallback**: 10+ variation patterns (numbers, dots, underscores, etc.)
- **No Duplicates**: Tracks attempted usernames to avoid retrying same one

### ✅ Configurable Retry Logic
- Set max attempts (default: 5)
- Automatic backoff between attempts
- Detailed logging of each attempt

## Quick Start

### Basic Usage (No AI)

```python
from smart_username_changer import SmartUsernameChanger
import uiautomator2 as u2

# Connect to device
device = u2.connect("10.1.10.36:5555")

# Create changer (no AI)
changer = SmartUsernameChanger(device)

# Try to change username with auto-retry
result = changer.change_username_with_retry(
    target_username="chantall.paris",
    max_attempts=5
)

if result['success']:
    print(f"Success! Username is now: {result['final_username']}")
else:
    print(f"Failed after {result['attempts']} attempts")
    print(f"Tried: {result['tried_usernames']}")
```

### Advanced Usage (With AI)

```python
from smart_username_changer import SmartUsernameChanger
import uiautomator2 as u2

# Connect to device
device = u2.connect("10.1.10.36:5555")

# Create changer with AI
changer = SmartUsernameChanger(
    device,
    ai_api_key="sk-your-openai-key-here",
    ai_provider="openai"  # or "anthropic" for Claude
)

# Try to change with AI-generated variations
result = changer.change_username_with_retry(
    target_username="chantall.paris",
    mother_account="chantall.main",  # AI will generate variations based on this
    max_attempts=5
)

print(f"Result: {result}")
```

## How It Works

### Flow Diagram

```
1. Attempt username "chantall.paris"
   ↓
2. Instagram says "username taken"
   ↓
3. Generate variation (AI or algorithmic)
   → AI: Analyzes "chantall.main" style → "chantall.style"
   → Algorithmic: "chantall.paris1"
   ↓
4. Retry with new variation
   ↓
5. Repeat until success or max attempts
```

### Variation Patterns (Algorithmic)

If username is `chantall.paris`:

1. `chantall.paris1` (attempt number)
2. `chantall.paris.2` (dot + number)
3. `chantall.paris_3` (underscore + number)
4. `chantall.ig` (suffix replacement)
5. `chantall_official` (semantic suffix)
6. `chantall.real` (semantic suffix)
7. `the.chantall` (prefix)
8. `chantall.page` (semantic suffix)
9. `chantall42` (random number)
10. `chantall.87` (dot + random)

### AI-Generated Variations

If mother account is `chantall.main`:

- AI analyzes the style: feminine, French name, simple
- Generates contextual variations:
  - `chantall.style`
  - `chantall.official`
  - `chantall.paris`
  - `chantall.fr`
  - `real.chantall`

## Integration with Automated Profile Manager

### Option 1: Replace Existing Username Change

Update `automated_profile_manager.py`:

```python
from smart_username_changer import SmartUsernameChanger

class AutomatedProfileManager:
    def __init__(self, ai_api_key=None):
        # ... existing code ...
        self.smart_changer = SmartUsernameChanger(
            self.device,
            ai_api_key=ai_api_key,
            ai_provider="openai"
        )

    def process_single_task(self, task):
        # ... existing code ...

        # Replace old username change:
        # if self.edit_username_automated(self.device, task['new_username']):

        # With smart username change:
        if task.get('new_username'):
            result = self.smart_changer.change_username_with_retry(
                target_username=task['new_username'],
                mother_account=task.get('mother_account'),  # Optional
                max_attempts=5
            )

            if result['success']:
                print(f"Username changed to: {result['final_username']}")
                changes_made.append("username")

                # Log the actual username used
                log_profile_change(
                    device_serial, instagram_package,
                    task.get('username', 'unknown'),
                    'username',
                    task.get('username'),
                    result['final_username'],  # Log actual username, not attempted
                    success=True
                )
            else:
                print(f"Username change failed: {result['message']}")
```

### Option 2: Add as Campaign Option

Update `tag_based_automation.py`:

```python
def create_campaign(self, tag_name, campaign_name, mother_account=None,
                   use_ai=False, strategies=None, use_smart_username=True):
    """
    Create campaign with smart username option

    Args:
        use_smart_username: Use smart username changer with retry (default: True)
    """
    # ... existing code ...

    # Store in campaign config
    campaign_data = {
        'tag_name': tag_name,
        'campaign_name': campaign_name,
        'mother_account': mother_account,
        'use_ai': use_ai,
        'use_smart_username': use_smart_username,  # NEW
        'strategies': strategies
    }
```

## Configuration

### Environment Variables (Optional)

Create `.env` file:

```bash
# AI Configuration
AI_PROVIDER=openai  # or anthropic
OPENAI_API_KEY=sk-your-key-here
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Username Change Settings
MAX_USERNAME_ATTEMPTS=5
USERNAME_RETRY_DELAY=2  # seconds between attempts
```

### Settings in Code

```python
changer = SmartUsernameChanger(
    device,
    ai_api_key="your-key",
    ai_provider="openai"  # openai, anthropic, or None
)

# Customize retry behavior
result = changer.change_username_with_retry(
    target_username="desired.username",
    mother_account="mother.account",
    max_attempts=10  # Try up to 10 times
)
```

## Error Messages Detected

The system detects these Instagram error messages:
- "This username isn't available"
- "isn't available"
- "already taken"
- "try another"
- "unavailable"
- "can't use this username"
- "Username not available"

## Response Format

```python
{
    'success': True/False,
    'final_username': 'chantall.paris2',  # Actual username set (if successful)
    'attempts': 3,  # Number of attempts made
    'message': 'Successfully changed to chantall.paris2',
    'tried_usernames': ['chantall.paris', 'chantall.paris1', 'chantall.paris2']  # Only if failed
}
```

## Testing

### Test Without Real Instagram

```python
# Test variation generation
changer = SmartUsernameChanger(device)

for i in range(1, 6):
    variation = changer._algorithmic_variation("chantall.paris", i)
    print(f"Variation {i}: {variation}")

# Output:
# Variation 1: chantall.paris1
# Variation 2: chantall.paris.2
# Variation 3: chantall.paris_3
# Variation 4: chantall.ig
# Variation 5: chantall_official
```

### Test AI Generation

```python
from ai_profile_generator import AIProfileGenerator

generator = AIProfileGenerator(
    api_key="your-key",
    provider="openai"
)

# Generate 5 variations
for i in range(5):
    username = generator.generate_username(
        mother_account="chantall.main",
        variations_count=1
    )
    print(f"AI Variation {i+1}: {username}")
```

## Best Practices

### 1. Use Mother Account for Consistency
```python
result = changer.change_username_with_retry(
    target_username="chantall.paris",
    mother_account="chantall.main",  # Ensures variations match style
    max_attempts=5
)
```

### 2. Set Reasonable Max Attempts
- **3-5 attempts**: Good for most cases
- **10+ attempts**: For high-demand usernames
- **1 attempt**: For testing/debugging only

### 3. Log All Attempts
```python
result = changer.change_username_with_retry(target_username="test.user")

# Log to database
if result['success']:
    log_username_change(
        old_username=current_username,
        new_username=result['final_username'],
        attempts=result['attempts']
    )
else:
    log_failed_username_change(
        desired_username=target_username,
        tried_usernames=result['tried_usernames']
    )
```

### 4. Handle API Limits
```python
import time

# Batch processing with rate limiting
for account in accounts:
    result = changer.change_username_with_retry(...)

    if not result['success'] and 'rate limit' in result['message'].lower():
        print("API rate limit hit, waiting 60 seconds...")
        time.sleep(60)
```

## Troubleshooting

### Issue: "All attempts failed"
**Solutions:**
1. Increase `max_attempts` to 10+
2. Check if mother_account style is too restrictive
3. Use AI for better variations
4. Manually check if base username pattern is banned

### Issue: AI not generating variations
**Solutions:**
1. Verify API key is set correctly
2. Check API credit balance
3. Test with fallback: `ai_api_key=None`
4. Check network connectivity

### Issue: Username changes but to wrong one
**Solutions:**
1. Check the `final_username` in result
2. Verify variation generation logic
3. Test generation separately before using

## Advanced: Custom Variation Logic

```python
class CustomSmartChanger(SmartUsernameChanger):
    """Custom changer with your own variation logic"""

    def _algorithmic_variation(self, base_username, attempt_num):
        """Override with custom patterns"""

        # Your custom logic
        if attempt_num == 1:
            return f"{base_username}.backup"
        elif attempt_num == 2:
            return f"{base_username}.alt"
        else:
            # Fallback to parent class
            return super()._algorithmic_variation(base_username, attempt_num)

# Use custom changer
changer = CustomSmartChanger(device)
```

## Summary

The Smart Username Changer provides:
- ✅ Automatic retry on "username taken"
- ✅ AI-powered intelligent variations
- ✅ Algorithmic fallback (works without AI)
- ✅ Detailed logging and result tracking
- ✅ Easy integration with existing automation
- ✅ Configurable retry behavior

Perfect for batch automation where username conflicts are common!
