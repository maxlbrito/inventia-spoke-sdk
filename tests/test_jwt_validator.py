"""HubJWTValidator — tests cobrindo happy path + corner cases."""

from __future__ import annotations

import time
from uuid import uuid4

import jwt
import pytest

from inventia_spoke_sdk import HubJWTValidator, InvalidToken, SpokePrincipal

SECRET = "test-secret-do-not-use-in-prod"


@pytest.fixture
def validator() -> HubJWTValidator:
    return HubJWTValidator(secret=SECRET, issuer="central-hub", audience="master-data")


def test_validate_returns_principal(validator: HubJWTValidator) -> None:
    user_id = uuid4()
    contract_id = uuid4()
    account_id = uuid4()
    token = validator.issue_for_test(
        {
            "sub": str(user_id),
            "email": "ana@acme.com.br",
            "active_contract_id": str(contract_id),
            "active_account_id": str(account_id),
            "scopes": ["master-data", "fiscal"],
            "is_super_admin": False,
        }
    )

    principal = validator.validate(token)
    assert isinstance(principal, SpokePrincipal)
    assert principal.user_id == user_id
    assert principal.email == "ana@acme.com.br"
    assert principal.contract_id == contract_id
    assert principal.account_id == account_id
    assert principal.scopes == ("master-data", "fiscal")
    assert principal.is_super_admin is False


def test_validate_legacy_claim_names(validator: HubJWTValidator) -> None:
    """Aceita ``contract_id``/``account_id`` (sem prefixo active_)."""
    user_id = uuid4()
    contract_id = uuid4()
    token = validator.issue_for_test(
        {
            "sub": str(user_id),
            "contract_id": str(contract_id),
            "scopes": [],
        }
    )
    principal = validator.validate(token)
    assert principal.contract_id == contract_id
    assert principal.account_id is None


def test_validate_super_admin(validator: HubJWTValidator) -> None:
    token = validator.issue_for_test({"sub": str(uuid4()), "is_super_admin": True})
    principal = validator.validate(token)
    assert principal.is_super_admin is True


def test_validate_empty_token_raises(validator: HubJWTValidator) -> None:
    with pytest.raises(InvalidToken, match="empty"):
        validator.validate("")


def test_validate_garbage_token_raises(validator: HubJWTValidator) -> None:
    with pytest.raises(InvalidToken):
        validator.validate("not.a.real.jwt")


def test_validate_wrong_secret_raises(validator: HubJWTValidator) -> None:
    other = HubJWTValidator(secret="other-secret", issuer="central-hub")
    forged = other.issue_for_test({"sub": str(uuid4())})
    with pytest.raises(InvalidToken):
        validator.validate(forged)


def test_validate_expired_raises(validator: HubJWTValidator) -> None:
    expired = jwt.encode(
        {
            "iss": "central-hub",
            "aud": "master-data",
            "sub": str(uuid4()),
            "exp": int(time.time()) - 3600,
            "iat": int(time.time()) - 7200,
        },
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(InvalidToken):
        validator.validate(expired)


def test_validate_wrong_issuer_raises(validator: HubJWTValidator) -> None:
    forged = jwt.encode(
        {
            "iss": "evil-issuer",
            "aud": "master-data",
            "sub": str(uuid4()),
            "exp": int(time.time()) + 60,
        },
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(InvalidToken):
        validator.validate(forged)


def test_validate_wrong_audience_raises(validator: HubJWTValidator) -> None:
    forged = jwt.encode(
        {
            "iss": "central-hub",
            "aud": "wrong-spoke",
            "sub": str(uuid4()),
            "exp": int(time.time()) + 60,
        },
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(InvalidToken):
        validator.validate(forged)


def test_validate_invalid_uuid_in_sub(validator: HubJWTValidator) -> None:
    forged = jwt.encode(
        {
            "iss": "central-hub",
            "aud": "master-data",
            "sub": "not-a-uuid",
            "exp": int(time.time()) + 60,
        },
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(InvalidToken, match="invalid sub"):
        validator.validate(forged)


def test_validate_invalid_contract_id_uuid(validator: HubJWTValidator) -> None:
    token = validator.issue_for_test({"sub": str(uuid4()), "active_contract_id": "not-a-uuid"})
    with pytest.raises(InvalidToken, match="invalid UUID"):
        validator.validate(token)


def test_validate_scopes_must_be_list(validator: HubJWTValidator) -> None:
    token = validator.issue_for_test({"sub": str(uuid4()), "scopes": "master-data"})
    with pytest.raises(InvalidToken, match="scopes"):
        validator.validate(token)


def test_validate_no_audience_check(validator: HubJWTValidator) -> None:
    """Validator com audience=None aceita tokens sem aud."""
    no_aud = HubJWTValidator(secret=SECRET, issuer="central-hub", audience=None)
    token = no_aud.issue_for_test({"sub": str(uuid4())})
    principal = no_aud.validate(token)
    assert principal.user_id


def test_validate_clock_skew_leeway() -> None:
    """Token expirado por 10s passa com leeway 30s, falha com leeway 5s."""
    now = int(time.time())
    forged = jwt.encode(
        {
            "iss": "central-hub",
            "sub": str(uuid4()),
            "exp": now - 10,
            "iat": now - 70,
        },
        SECRET,
        algorithm="HS256",
    )
    tolerant = HubJWTValidator(secret=SECRET, issuer="central-hub", leeway_seconds=30)
    strict = HubJWTValidator(secret=SECRET, issuer="central-hub", leeway_seconds=5)
    tolerant.validate(forged)  # passa
    with pytest.raises(InvalidToken):
        strict.validate(forged)
