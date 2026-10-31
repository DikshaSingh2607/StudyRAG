from backend.app.security import hash_password, token_digest, verify_password


def test_password_hash_verifies_only_the_original_password() -> None:
    encoded = hash_password("a sufficiently long test phrase")
    assert encoded != "a sufficiently long test phrase"
    assert verify_password(encoded, "a sufficiently long test phrase")
    assert not verify_password(encoded, "a different phrase")


def test_one_time_token_digest_is_stable_and_not_the_raw_token() -> None:
    token = "a-random-one-time-token-value"
    digest = token_digest(token)
    assert digest == token_digest(token)
    assert digest != token
    assert len(digest) == 64
