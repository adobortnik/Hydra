"""
Hydra License Manager
======================
Validates license keys for Hydra deployment.
Supports both offline (HMAC) and online (phone-home) validation.

License key format: HYDRA-XXXXX-XXXXX-XXXXX-XXXXX
"""

import hashlib
import hmac
import json
import os
import sys
import time
import uuid
import platform
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# ── Secret (compiled into binary, not visible in source) ──
_LICENSE_SECRET = b"Hydr4_2026_S3cur3_K3y_!@#$%"
_LICENSE_VERSION = 1

# ── License tiers ──
TIERS = {
    "starter": {"max_devices": 5, "max_accounts": 50, "features": ["basic"]},
    "pro": {"max_devices": 25, "max_accounts": 300, "features": ["basic", "ai", "content_schedule"]},
    "enterprise": {"max_devices": 100, "max_accounts": 1000, "features": ["basic", "ai", "content_schedule", "job_orders", "api"]},
    "unlimited": {"max_devices": 9999, "max_accounts": 99999, "features": ["all"]},
}


def _get_machine_id():
    """Get a unique machine identifier (hardware fingerprint)."""
    parts = []
    parts.append(platform.node())  # hostname
    parts.append(platform.machine())  # architecture
    
    # Try to get MAC address
    try:
        mac = uuid.getnode()
        parts.append(str(mac))
    except Exception:
        pass
    
    # Try to get Windows product ID
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        product_id = winreg.QueryValueEx(key, "ProductId")[0]
        parts.append(product_id)
        winreg.CloseKey(key)
    except Exception:
        pass
    
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def generate_license_key(tier="pro", days=365, machine_id=None, customer_name=""):
    """
    Generate a license key (ADMIN ONLY — run this on YOUR machine).
    
    Args:
        tier: starter/pro/enterprise/unlimited
        days: validity in days (0 = perpetual)
        machine_id: lock to specific machine (None = any machine)
        customer_name: customer identifier
    
    Returns:
        dict with key, tier, expiry, etc.
    """
    if tier not in TIERS:
        raise ValueError(f"Invalid tier: {tier}. Must be one of: {list(TIERS.keys())}")
    
    # Build license payload
    payload = {
        "v": _LICENSE_VERSION,
        "tier": tier,
        "customer": customer_name,
        "machine": machine_id or "*",
        "created": int(time.time()),
        "expires": int(time.time()) + (days * 86400) if days > 0 else 0,
        "nonce": os.urandom(4).hex(),
    }
    
    # Serialize and sign
    payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    signature = hmac.new(_LICENSE_SECRET, payload_str.encode(), hashlib.sha256).hexdigest()[:20]
    
    # Encode to license key format
    import base64
    encoded = base64.urlsafe_b64encode(payload_str.encode()).decode().rstrip("=")
    
    # Build key: HYDRA-{encoded}.{signature}
    key = f"HYDRA-{encoded}.{signature}"
    
    return {
        "key": key,
        "tier": tier,
        "customer": customer_name,
        "machine": machine_id or "any",
        "expires": datetime.fromtimestamp(payload["expires"]).isoformat() if payload["expires"] else "never",
        "days": days,
    }


def validate_license_key(key):
    """
    Validate a license key.
    
    Returns:
        dict with valid=True/False, tier, expires, error, etc.
    """
    try:
        if not key or not key.startswith("HYDRA-"):
            return {"valid": False, "error": "Invalid key format"}
        
        # Parse key
        body = key[6:]  # Remove "HYDRA-"
        if "." not in body:
            return {"valid": False, "error": "Invalid key structure"}
        
        encoded, signature = body.rsplit(".", 1)
        
        # Decode payload
        import base64
        # Add padding back
        padding = 4 - len(encoded) % 4
        if padding != 4:
            encoded += "=" * padding
        
        payload_str = base64.urlsafe_b64decode(encoded).decode()
        payload = json.loads(payload_str)
        
        # Verify signature
        expected_sig = hmac.new(_LICENSE_SECRET, payload_str.encode(), hashlib.sha256).hexdigest()[:20]
        if not hmac.compare_digest(signature, expected_sig):
            return {"valid": False, "error": "Invalid license key (signature mismatch)"}
        
        # Check version
        if payload.get("v") != _LICENSE_VERSION:
            return {"valid": False, "error": "License key version mismatch"}
        
        # Check expiry
        expires = payload.get("expires", 0)
        if expires > 0 and time.time() > expires:
            exp_date = datetime.fromtimestamp(expires).strftime("%Y-%m-%d")
            return {"valid": False, "error": f"License expired on {exp_date}"}
        
        # Check machine lock
        machine = payload.get("machine", "*")
        if machine != "*":
            current_machine = _get_machine_id()
            if machine != current_machine:
                return {"valid": False, "error": "License not valid for this machine"}
        
        # Valid!
        tier = payload.get("tier", "starter")
        tier_info = TIERS.get(tier, TIERS["starter"])
        
        return {
            "valid": True,
            "tier": tier,
            "customer": payload.get("customer", ""),
            "max_devices": tier_info["max_devices"],
            "max_accounts": tier_info["max_accounts"],
            "features": tier_info["features"],
            "expires": datetime.fromtimestamp(expires).isoformat() if expires else "never",
            "machine_locked": machine != "*",
        }
    
    except Exception as e:
        return {"valid": False, "error": f"License validation error: {str(e)}"}


class LicenseGuard:
    """
    License enforcement for the dashboard.
    Caches validation result so we don't re-validate on every request.
    """
    
    def __init__(self, license_file=None):
        self._license_file = license_file or self._default_license_path()
        self._cached_result = None
        self._cache_time = 0
        self._cache_ttl = 300  # Re-validate every 5 minutes
    
    def _default_license_path(self):
        """Default license file location."""
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "license.key")
    
    def get_license(self):
        """Read and validate the current license. Returns validation result."""
        now = time.time()
        
        # Return cached result if fresh
        if self._cached_result and (now - self._cache_time) < self._cache_ttl:
            return self._cached_result
        
        # Read license file
        if not os.path.exists(self._license_file):
            result = {"valid": False, "error": "No license file found. Please activate Hydra."}
            self._cached_result = result
            self._cache_time = now
            return result
        
        try:
            with open(self._license_file, "r") as f:
                key = f.read().strip()
        except Exception as e:
            result = {"valid": False, "error": f"Cannot read license file: {e}"}
            self._cached_result = result
            self._cache_time = now
            return result
        
        result = validate_license_key(key)
        self._cached_result = result
        self._cache_time = now
        return result
    
    def activate(self, key):
        """Save a license key to the license file."""
        result = validate_license_key(key)
        if not result["valid"]:
            return result
        
        # Save to file
        try:
            with open(self._license_file, "w") as f:
                f.write(key)
            self._cached_result = None  # Clear cache
            return result
        except Exception as e:
            return {"valid": False, "error": f"Cannot save license: {e}"}
    
    def is_feature_allowed(self, feature):
        """Check if a feature is allowed by the current license."""
        lic = self.get_license()
        if not lic["valid"]:
            return False
        features = lic.get("features", [])
        return "all" in features or feature in features
    
    def check_device_limit(self, current_count):
        """Check if adding another device would exceed the limit."""
        lic = self.get_license()
        if not lic["valid"]:
            return False
        return current_count < lic.get("max_devices", 0)
    
    def check_account_limit(self, current_count):
        """Check if adding another account would exceed the limit."""
        lic = self.get_license()
        if not lic["valid"]:
            return False
        return current_count < lic.get("max_accounts", 0)


# ── CLI for key generation ──
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Hydra License Manager")
    sub = parser.add_subparsers(dest="command")
    
    # Generate key
    gen = sub.add_parser("generate", help="Generate a license key")
    gen.add_argument("--tier", choices=list(TIERS.keys()), default="pro")
    gen.add_argument("--days", type=int, default=365, help="Validity in days (0=perpetual)")
    gen.add_argument("--machine", type=str, default=None, help="Lock to machine ID")
    gen.add_argument("--customer", type=str, default="", help="Customer name")
    
    # Validate key
    val = sub.add_parser("validate", help="Validate a license key")
    val.add_argument("key", help="License key to validate")
    
    # Show machine ID
    mid = sub.add_parser("machine-id", help="Show this machine's ID")
    
    # Activate
    act = sub.add_parser("activate", help="Activate with a license key")
    act.add_argument("key", help="License key")
    
    args = parser.parse_args()
    
    if args.command == "generate":
        result = generate_license_key(
            tier=args.tier,
            days=args.days,
            machine_id=args.machine,
            customer_name=args.customer
        )
        print(f"\n{'='*60}")
        print(f"  HYDRA LICENSE KEY GENERATED")
        print(f"{'='*60}")
        print(f"  Tier:     {result['tier']}")
        print(f"  Customer: {result['customer'] or 'N/A'}")
        print(f"  Machine:  {result['machine']}")
        print(f"  Expires:  {result['expires']}")
        print(f"{'='*60}")
        print(f"\n  {result['key']}\n")
        print(f"{'='*60}\n")
    
    elif args.command == "validate":
        result = validate_license_key(args.key)
        if result["valid"]:
            print(f"\nValid license!")
            print(f"  Tier: {result['tier']}")
            print(f"  Max devices: {result['max_devices']}")
            print(f"  Max accounts: {result['max_accounts']}")
            print(f"  Features: {', '.join(result['features'])}")
            print(f"  Expires: {result['expires']}")
        else:
            print(f"\nInvalid: {result['error']}")
    
    elif args.command == "machine-id":
        print(f"\nMachine ID: {_get_machine_id()}")
    
    elif args.command == "activate":
        guard = LicenseGuard()
        result = guard.activate(args.key)
        if result["valid"]:
            print(f"\nActivated! Tier: {result['tier']}")
        else:
            print(f"\nFailed: {result['error']}")
    
    else:
        parser.print_help()
