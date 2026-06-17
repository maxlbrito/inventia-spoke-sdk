"""Decifragem in-process do material do certificado A1.

A chave Fernet **per-tenant** vem do próprio banco do account (read-model
``CertificateKey``); aqui só aplicamos o Fernet. ``cryptography`` é importado de
forma preguiçosa para não obrigar consumidores do SDK que só leem metadados a
instalá-lo — peça o extra ``inventia-spoke-sdk[masterdata]`` para usar material.
"""

from __future__ import annotations


class CertificateKeyMissing(Exception):
    """Não há chave Fernet per-tenant no banco — impossível decifrar o cert."""


class CertificateDecryptError(Exception):
    """Token inválido/adulterado ou chave incorreta ao decifrar o certificado."""


def decrypt_tokens(key: str, *tokens: str) -> list[bytes]:
    """Decifra um ou mais tokens Fernet com a chave per-tenant.

    Levanta ``CertificateDecryptError`` se algum token for inválido para a chave.
    """
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ModuleNotFoundError as exc:  # pragma: no cover - defensivo
        raise RuntimeError(
            "Material de certificado requer 'cryptography'. "
            "Instale o extra: inventia-spoke-sdk[masterdata]."
        ) from exc

    fernet = Fernet(key.encode())
    try:
        return [fernet.decrypt(token.encode()) for token in tokens]
    except InvalidToken as exc:
        raise CertificateDecryptError(str(exc)) from exc
