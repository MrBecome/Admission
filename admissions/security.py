"""
Centralised one-time-password (OTP) handling for the admin login flow.

Kept deliberately separate from views.py: view functions should only decide
*when* to challenge for an OTP and *what to do* with the result, never how
the code itself is generated, stored, or compared. That logic lives here.
"""
import random

from django.core.cache import cache

OTP_CACHE_PREFIX = 'admin_otp_'
OTP_TTL_SECONDS = 300  # 5 minutes


def generate_otp(user_id):
    """
    Generates a fresh 6-digit numeric OTP, stores it against this user_id
    for OTP_TTL_SECONDS, and returns the code so the caller can email it.
    Overwrites any previously pending OTP for the same user.
    """
    otp = str(random.randint(100000, 999999))
    cache.set(f'{OTP_CACHE_PREFIX}{user_id}', otp, timeout=OTP_TTL_SECONDS)
    return otp


def verify_otp(user_id, submitted_code):
    """
    Returns True and clears the stored code if submitted_code matches what
    was generated for this user_id and hasn't expired. Returns False
    (without clearing anything) on any mismatch, missing code, or expiry -
    so a wrong guess doesn't burn the real code before it's tried correctly.
    """
    stored = cache.get(f'{OTP_CACHE_PREFIX}{user_id}')
    if stored and str(submitted_code) == stored:
        cache.delete(f'{OTP_CACHE_PREFIX}{user_id}')
        return True
    return False


def clear_otp(user_id):
    """Invalidates any pending OTP for this user_id (e.g. on logout or 'start over')."""
    cache.delete(f'{OTP_CACHE_PREFIX}{user_id}')
