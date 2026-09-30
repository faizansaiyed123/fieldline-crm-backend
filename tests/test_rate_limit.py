from app.auth.rate_limit import fingerprint


def test_rate_limit_fingerprint_is_deterministic_and_scoped() -> None:
    a = fingerprint("login-email", "user@example.com|127.0.0.1")
    b = fingerprint("login-email", "user@example.com|127.0.0.1")
    c = fingerprint("login-ip", "user@example.com|127.0.0.1")

    assert a == b
    assert len(a) == 64
    assert a != c
