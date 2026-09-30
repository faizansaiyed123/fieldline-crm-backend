from uuid import uuid4

import jwt
import pytest

from app.auth.crypto import hash_password, verify_password
from app.auth.tokens import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_refresh_token,
)
from app.core.config import Settings


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    password = "Correct Horse Battery Staple"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_round_trips() -> None:
    user_id = uuid4()
    token = create_access_token(user_id)
    assert decode_access_token(token) == user_id


def test_access_token_rejects_wrong_type() -> None:
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "type": "refresh",
            "iat": 1,
            "exp": 9999999999,
            "iss": "fieldline-api",
            "aud": "fieldline-web",
        },
        Settings().jwt_secret_key,
        algorithm="HS256",
    )
    with pytest.raises(ValueError):
        decode_access_token(token)


def test_refresh_tokens_are_opaque_and_hashed() -> None:
    token = create_refresh_token()
    assert len(token) >= 50
    assert hash_refresh_token(token) != token
    assert hash_refresh_token(token) == hash_refresh_token(token)


def test_production_requires_a_real_secret_and_secure_cookies() -> None:
    with pytest.raises(ValueError):
        Settings(
            environment="production",
            jwt_secret_key="development-only-change-me-development-only",
            secure_cookies=True,
        )
    with pytest.raises(ValueError):
        Settings(environment="production", jwt_secret_key="x" * 32, secure_cookies=False)


def test_secret_must_have_at_least_32_bytes() -> None:
    with pytest.raises(ValueError):
        Settings(jwt_secret_key="too-short")
