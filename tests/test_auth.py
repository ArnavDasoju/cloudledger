"""Tests for authentication — JWT token lifecycle and failure paths."""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from backend.auth import (
    hash_password,
    verify_password,
    create_token,
    decode_token,
    get_current_user_id,
    JWT_SECRET,
    JWT_ALGORITHM,
)


class TestPasswordHashing:
    def test_hash_and_verify_roundtrip(self):
        hashed = hash_password("correct-horse-battery-staple")
        assert verify_password("correct-horse-battery-staple", hashed)

    def test_wrong_password_rejected(self):
        hashed = hash_password("correct-horse-battery-staple")
        assert not verify_password("wrong-password", hashed)


class TestTokenLifecycle:
    def test_create_and_decode_roundtrip(self):
        token = create_token(42, "user@example.com")
        payload = decode_token(token)
        assert payload["user_id"] == 42
        assert payload["email"] == "user@example.com"
        assert "exp" in payload

    def test_expired_token_raises_401(self):
        """A token with exp in the past should be rejected."""
        payload = {
            "user_id": 1,
            "email": "user@example.com",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_malformed_token_raises_401(self):
        """Garbage string should be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            decode_token("not.a.valid.jwt.token")
        assert exc_info.value.status_code == 401

    def test_wrong_secret_raises_401(self):
        """Token signed with a different secret should be rejected."""
        payload = {
            "user_id": 1,
            "email": "user@example.com",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = pyjwt.encode(payload, "wrong-secret", algorithm=JWT_ALGORITHM)
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401


class TestGetCurrentUserId:
    def _make_request(self, auth_header=None):
        request = MagicMock()
        headers = MagicMock()
        headers.get = MagicMock(return_value=auth_header or "")
        request.headers = headers
        return request

    def test_valid_bearer_token(self):
        token = create_token(7, "test@test.com")
        request = self._make_request(f"Bearer {token}")
        assert get_current_user_id(request) == 7

    def test_missing_auth_header_raises_401(self):
        request = self._make_request(None)
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_id(request)
        assert exc_info.value.status_code == 401

    def test_non_bearer_scheme_raises_401(self):
        request = self._make_request("Basic dXNlcjpwYXNz")
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_id(request)
        assert exc_info.value.status_code == 401

    def test_empty_bearer_token_raises_401(self):
        request = self._make_request("Bearer ")
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_id(request)
        assert exc_info.value.status_code == 401


class TestSecretValidation:
    def test_default_dev_secret_meets_minimum_length(self):
        """The default dev secret must be >= 32 bytes for HS256 compliance."""
        from backend.auth import JWT_SECRET, _MIN_SECRET_BYTES
        assert len(JWT_SECRET.encode("utf-8")) >= _MIN_SECRET_BYTES, (
            f"Default JWT_SECRET is {len(JWT_SECRET.encode('utf-8'))} bytes, "
            f"below the {_MIN_SECRET_BYTES}-byte HS256 minimum"
        )
