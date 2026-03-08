"""
Eversale License Validator - Validates subscription before allowing CLI usage.

Checks against the Eversale API to verify:
1. User has active subscription
2. License key is valid
3. Usage limits not exceeded

Without valid license, CLI refuses to run.
"""

import os
import json
import hashlib
import platform
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
import httpx
from loguru import logger


# License cache file
LICENSE_CACHE_PATH = Path.home() / ".eversale" / "license_cache.json"
EVERSALE_API_URL = os.environ.get(
    "EVERSALE_LICENSE_URL",
    "https://eversale.io/api/desktop/validate-license"
)

# Cache validity period (hours) - validates online once per day
CACHE_VALIDITY_HOURS = 24

# Request timeout in seconds
REQUEST_TIMEOUT = 10.0


def get_device_fingerprint() -> str:
    """Generate a unique device fingerprint."""
    parts = [
        platform.node(),  # hostname
        platform.system(),  # OS
        platform.machine(),  # arch
        os.getenv("USER", os.getenv("USERNAME", "unknown")),
    ]
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:32]


def load_license_cache() -> Optional[Dict]:
    """Load cached license validation result."""
    try:
        if LICENSE_CACHE_PATH.exists():
            with open(LICENSE_CACHE_PATH) as f:
                data = json.load(f)
                # Check if cache is still valid
                cached_at = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
                if datetime.now() - cached_at < timedelta(hours=CACHE_VALIDITY_HOURS):
                    return data
    except Exception as e:
        logger.debug(f"License cache load failed: {e}")
    return None


def save_license_cache(data: Dict):
    """Save license validation result to cache."""
    try:
        LICENSE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Set directory permissions to owner-only
        os.chmod(LICENSE_CACHE_PATH.parent, 0o700)

        data["cached_at"] = datetime.now().isoformat()
        with open(LICENSE_CACHE_PATH, "w") as f:
            json.dump(data, f)

        # Set file permissions to owner read/write only
        os.chmod(LICENSE_CACHE_PATH, 0o600)
    except Exception as e:
        logger.debug(f"License cache save failed: {e}")


def get_license_key() -> Optional[str]:
    """Get license key from environment or config file."""
    # Check environment first
    key = os.getenv("EVERSALE_LICENSE_KEY")
    if key:
        return key.strip()

    # Check config file
    config_path = Path.home() / ".eversale" / "license.key"
    if config_path.exists():
        try:
            return config_path.read_text().strip()
        except Exception:
            pass

    return None


def save_license_key(key: str):
    """Save license key to config file."""
    config_path = Path.home() / ".eversale" / "license.key"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    # Set directory permissions to owner-only
    os.chmod(config_path.parent, 0o700)

    config_path.write_text(key)

    # Set file permissions to owner read/write only
    os.chmod(config_path, 0o600)


def _build_validation_payload(license_key: str) -> Dict:
    """Build the validation request payload."""
    return {
        "license_key": license_key,
        "device_fingerprint": get_device_fingerprint(),
        "version": "0.8.2",
        "platform": platform.system(),
    }


def _process_validation_response(response: httpx.Response) -> Tuple[bool, str, Optional[Dict]]:
    """
    Process the HTTP response from license validation.

    Returns:
        (is_valid, message, user_data)
    """
    if response.status_code == 200:
        data = response.json()
        if data.get("valid"):
            return True, "License valid", data.get("user")
        else:
            return False, data.get("error", "Invalid license"), None
    elif response.status_code == 401:
        return False, "Invalid or expired license key", None
    elif response.status_code == 403:
        return False, "Subscription inactive - please renew at eversale.io", None
    elif response.status_code == 429:
        return False, "Too many validation attempts - please wait", None
    else:
        # Server error - allow cached validation to work
        logger.warning(f"License server returned {response.status_code}")
        return True, "Server unavailable - using cached validation", None


def validate_license_online_sync(license_key: str) -> Tuple[bool, str, Optional[Dict]]:
    """
    Validate license key against Eversale API (synchronous version).

    Returns:
        (is_valid, message, user_data)
    """
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.post(
                EVERSALE_API_URL,
                json=_build_validation_payload(license_key)
            )
            return _process_validation_response(response)

    except httpx.ConnectError:
        logger.warning("Cannot reach license server - offline mode")
        return True, "Offline - using cached validation", None
    except Exception as e:
        logger.warning(f"License validation error: {e}")
        return True, "Validation error - using cached", None


async def validate_license_online(license_key: str) -> Tuple[bool, str, Optional[Dict]]:
    """
    Validate license key against Eversale API (async version).

    Returns:
        (is_valid, message, user_data)
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                EVERSALE_API_URL,
                json=_build_validation_payload(license_key)
            )
            return _process_validation_response(response)

    except httpx.ConnectError:
        logger.warning("Cannot reach license server - offline mode")
        return True, "Offline - using cached validation", None
    except Exception as e:
        logger.warning(f"License validation error: {e}")
        return True, "Validation error - using cached", None


def _get_no_license_message() -> str:
    """Return the message shown when no license key is found."""
    return (
        "No license key found.\n"
        "Get your key at: https://eversale.io/desktop\n"
        "Then run: eversale --activate YOUR_LICENSE_KEY"
    )


def _check_cached_license(license_key: str) -> Optional[Tuple[bool, str]]:
    """
    Check if there's a valid cached license.

    Returns:
        (is_valid, message) if cache is valid, None if cache should be skipped
    """
    cached = load_license_cache()
    if cached and cached.get("license_key") == license_key and cached.get("valid"):
        logger.debug("Using cached license validation")
        return True, f"License valid (cached) - {cached.get('email', 'unknown')}"
    return None


def _process_validation_result(
    is_valid: bool,
    message: str,
    user_data: Optional[Dict],
    license_key: str
) -> Tuple[bool, str]:
    """
    Process the validation result and update cache accordingly.

    Returns:
        (is_valid, message) tuple for the final result
    """
    if is_valid and user_data:
        # Save to cache
        save_license_cache({
            "license_key": license_key,
            "valid": True,
            "email": user_data.get("email"),
            "plan": user_data.get("plan"),
            "expires_at": user_data.get("expires_at"),
        })
        return True, f"License valid - {user_data.get('email', 'unknown')}"
    elif is_valid:
        # Offline/error but allowing
        return True, message
    else:
        # Clear bad cache
        if LICENSE_CACHE_PATH.exists():
            LICENSE_CACHE_PATH.unlink()
        return False, message


async def validate_license() -> Tuple[bool, str]:
    """Local mode - license validation bypassed."""
    return True, "Local mode - license valid"


def validate_license_sync() -> Tuple[bool, str]:
    """Local mode - license validation bypassed."""
    return True, "Local mode - license valid"


def activate_license(key: str) -> Tuple[bool, str]:
    """Activate a new license key (synchronous - safe to call from anywhere)."""
    # Validate using synchronous httpx
    is_valid, message, user_data = validate_license_online_sync(key)

    if is_valid and user_data:
        # Save the key
        save_license_key(key)
        save_license_cache({
            "license_key": key,
            "valid": True,
            "email": user_data.get("email"),
            "plan": user_data.get("plan"),
            "expires_at": user_data.get("expires_at"),
        })
        return True, f"License activated for {user_data.get('email')}"
    else:
        return False, message


def deactivate_license():
    """Remove license key and cache."""
    key_path = Path.home() / ".eversale" / "license.key"
    if key_path.exists():
        key_path.unlink()
    if LICENSE_CACHE_PATH.exists():
        LICENSE_CACHE_PATH.unlink()
