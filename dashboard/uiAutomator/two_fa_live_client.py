"""
two_fa_live_client.py

Client for 2fa.live SMS code retrieval service
Simple HTTP-based integration for Instagram 2FA automation

API Pattern:
GET https://2fa.live/tok/{TOKEN}
Returns: {"token": "123456"}

Author: Claude Code
Created: 2025-11-21
"""

import requests
import time
from datetime import datetime


class TwoFALiveClient:
    """
    Client for fetching SMS codes from 2fa.live

    Usage:
        client = TwoFALiveClient("CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD")
        code = client.get_code()  # Returns "123456"
    """

    def __init__(self, token, timeout=60):
        """
        Initialize 2FA client

        Args:
            token: 2fa.live token (e.g., "CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD")
            timeout: Maximum time to wait for code (seconds)
        """
        self.token = token
        self.timeout = timeout
        self.base_url = "https://2fa.live/tok"

    def get_code(self, max_retries=20, retry_interval=3):
        """
        Get SMS code from 2fa.live with retry logic

        SMS codes may take 10-60 seconds to arrive, so we poll repeatedly.

        Args:
            max_retries: Maximum number of retry attempts (default: 20)
            retry_interval: Seconds between retries (default: 3)

        Returns:
            str: 6-digit code (e.g., "123456"), or None if failed
        """
        print(f"Fetching 2FA code from 2fa.live...")
        print(f"Token: {self.token}")
        print(f"Will retry up to {max_retries} times (every {retry_interval}s)")

        url = f"{self.base_url}/{self.token}"
        start_time = time.time()

        for attempt in range(1, max_retries + 1):
            elapsed = int(time.time() - start_time)

            try:
                print(f"\nAttempt {attempt}/{max_retries} (elapsed: {elapsed}s)...")

                # Make request to 2fa.live
                response = requests.get(url, timeout=10)

                # Check HTTP status
                if response.status_code != 200:
                    print(f"⚠ HTTP {response.status_code}: {response.text}")

                    # If we get 404 or similar, the token might be invalid
                    if response.status_code in [404, 403]:
                        print(f"✗ Token appears invalid: {self.token}")
                        return None

                    # Otherwise, retry
                    time.sleep(retry_interval)
                    continue

                # Parse JSON response
                data = response.json()

                # Check if code is present
                if 'token' in data and data['token']:
                    code = str(data['token']).strip()

                    # Validate code format (should be 6 digits)
                    if len(code) == 6 and code.isdigit():
                        print(f"✓ Code received: {code}")
                        return code
                    else:
                        print(f"⚠ Invalid code format: {code}")
                        time.sleep(retry_interval)
                        continue

                # No code yet, probably still waiting for SMS
                print(f"⏳ No code yet, retrying in {retry_interval}s...")
                time.sleep(retry_interval)

            except requests.exceptions.Timeout:
                print(f"⚠ Request timeout, retrying...")
                time.sleep(retry_interval)

            except requests.exceptions.ConnectionError:
                print(f"⚠ Connection error, retrying...")
                time.sleep(retry_interval)

            except requests.exceptions.RequestException as e:
                print(f"⚠ Request error: {e}")
                time.sleep(retry_interval)

            except ValueError as e:
                print(f"⚠ JSON parse error: {e}")
                print(f"Response: {response.text}")
                time.sleep(retry_interval)

            # Check if we've exceeded total timeout
            if time.time() - start_time > self.timeout:
                print(f"✗ Timeout reached ({self.timeout}s), giving up")
                return None

        print(f"✗ Failed to get code after {max_retries} attempts")
        return None

    def test_connection(self):
        """
        Test if the token is valid and accessible

        Returns:
            dict: {'success': bool, 'message': str, 'code': str or None}
        """
        print(f"Testing 2fa.live connection...")
        print(f"Token: {self.token}")

        url = f"{self.base_url}/{self.token}"

        try:
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()

                if 'token' in data:
                    code = data.get('token', '')

                    if code:
                        return {
                            'success': True,
                            'message': f'Token valid, code available: {code}',
                            'code': str(code)
                        }
                    else:
                        return {
                            'success': True,
                            'message': 'Token valid, waiting for SMS',
                            'code': None
                        }
                else:
                    return {
                        'success': False,
                        'message': f'Unexpected response format: {data}',
                        'code': None
                    }

            else:
                return {
                    'success': False,
                    'message': f'HTTP {response.status_code}: {response.text}',
                    'code': None
                }

        except Exception as e:
            return {
                'success': False,
                'message': f'Connection error: {str(e)}',
                'code': None
            }

    @staticmethod
    def format_token_url(token):
        """
        Format a token into a full 2fa.live URL

        Args:
            token: Token string

        Returns:
            str: Full URL
        """
        return f"https://2fa.live/tok/{token}"

    @staticmethod
    def validate_code(code):
        """
        Validate that a code is a valid 6-digit format

        Args:
            code: Code string to validate

        Returns:
            bool: True if valid 6-digit code
        """
        if not code:
            return False

        code_str = str(code).strip()
        return len(code_str) == 6 and code_str.isdigit()


def test_2fa_client(token):
    """
    Test function for 2FA client

    Args:
        token: 2fa.live token to test
    """
    print("="*70)
    print("2FA.LIVE CLIENT TEST")
    print("="*70)

    client = TwoFALiveClient(token)

    # Test connection
    print("\n" + "-"*70)
    print("1. Testing Connection")
    print("-"*70)

    test_result = client.test_connection()
    print(f"\nResult: {test_result['message']}")

    if test_result['success']:
        print("✓ Connection successful")

        if test_result['code']:
            print(f"✓ Code available: {test_result['code']}")
        else:
            print("⏳ No code yet (waiting for SMS)")

            # Try to get code with retries
            print("\n" + "-"*70)
            print("2. Attempting to Fetch Code (with retries)")
            print("-"*70)

            code = client.get_code(max_retries=10, retry_interval=3)

            if code:
                print(f"\n✓ Successfully retrieved code: {code}")
                print(f"✓ Code validation: {TwoFALiveClient.validate_code(code)}")
            else:
                print("\n✗ Could not retrieve code")
    else:
        print(f"✗ Connection failed: {test_result['message']}")

    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python two_fa_live_client.py <TOKEN>")
        print("\nExample:")
        print("  python two_fa_live_client.py CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD")
        sys.exit(1)

    token = sys.argv[1]
    test_2fa_client(token)
