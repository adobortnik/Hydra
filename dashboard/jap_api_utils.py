import os

# API key file path
API_KEYS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data/api_keys')
JAP_API_KEY_FILE = os.path.join(API_KEYS_DIR, 'jap_api_key.txt')

# Create directory if it doesn't exist
os.makedirs(API_KEYS_DIR, exist_ok=True)

# Global variable for API key
JAP_API_KEY = ''

def save_jap_api_key(api_key):
    """
    Save the JustAnotherPanel API key to a file
    """
    try:
        with open(JAP_API_KEY_FILE, 'w') as f:
            f.write(api_key)
        return True
    except Exception as e:
        print(f"Error saving API key: {e}")
        return False

def load_jap_api_key():
    """
    Load the JustAnotherPanel API key from a file
    """
    try:
        if os.path.exists(JAP_API_KEY_FILE):
            with open(JAP_API_KEY_FILE, 'r') as f:
                api_key = f.read().strip()
                return api_key
        return ''
    except Exception as e:
        print(f"Error loading API key: {e}")
        return ''

# Load API key on module import
JAP_API_KEY = load_jap_api_key()
