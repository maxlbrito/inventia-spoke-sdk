"""MCP / Resource Server discovery — RFC 9728 + RFC 8414 (Fase 5 do plano-auth).

Um Resource Server (servidor MCP ou API REST) publica seu próprio
``/.well-known/oauth-protected-resource`` (RFC 9728) apontando para o(s)
Authorization Server(s) e declarando os escopos que aceita. Clientes MCP usam
isso para descobrir o AS (e de lá, via RFC 8414, os endpoints OAuth).

O enforcement em si (validar token, escopo, tenant, CNPJ) é o mesmo das 5
camadas — ver ``enforcement`` e ``HubJWTValidator``. Aqui ficam só os metadados
de descoberta + o desafio ``WWW-Authenticate`` que aponta para o metadata.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import FastAPI

WELL_KNOWN_PROTECTED_RESOURCE = "/.well-known/oauth-protected-resource"


def protected_resource_metadata(
    *,
    resource: str,
    authorization_servers: Iterable[str],
    scopes_supported: Iterable[str] | None = None,
    bearer_methods_supported: Iterable[str] = ("header",),
    resource_documentation: str | None = None,
) -> dict[str, Any]:
    """Monta o documento RFC 9728 (OAuth 2.0 Protected Resource Metadata).

    Args:
        resource: identificador (URL) deste Resource Server — DEVE bater com o
            ``aud`` esperado nos tokens (Audience Mapper, ver Fase 1).
        authorization_servers: issuers dos AS (ex.: realm do Keycloak e/ou Hub).
        scopes_supported: escopos ``recurso:ação`` que este RS reconhece.
    """
    meta: dict[str, Any] = {
        "resource": resource,
        "authorization_servers": list(authorization_servers),
        "bearer_methods_supported": list(bearer_methods_supported),
    }
    if scopes_supported is not None:
        meta["scopes_supported"] = list(scopes_supported)
    if resource_documentation is not None:
        meta["resource_documentation"] = resource_documentation
    return meta


def mount_protected_resource_metadata(
    app: FastAPI,
    *,
    resource: str,
    authorization_servers: Iterable[str],
    scopes_supported: Iterable[str] | None = None,
    resource_documentation: str | None = None,
) -> None:
    """Registra ``GET /.well-known/oauth-protected-resource`` (RFC 9728) no app.

    Chame uma vez no startup do Resource Server (spoke / servidor MCP)::

        mount_protected_resource_metadata(
            app,
            resource="https://reinf.inventiaapp.com",
            authorization_servers=["http://localhost:8080/realms/inventia"],
            scopes_supported=["reinf:read", "reinf:write"],
        )
    """
    from fastapi.responses import JSONResponse

    meta = protected_resource_metadata(
        resource=resource,
        authorization_servers=authorization_servers,
        scopes_supported=scopes_supported,
        resource_documentation=resource_documentation,
    )

    async def _well_known() -> JSONResponse:
        return JSONResponse(meta)

    app.add_api_route(
        WELL_KNOWN_PROTECTED_RESOURCE,
        _well_known,
        methods=["GET"],
        include_in_schema=False,
    )


def protected_resource_challenge(resource: str, scope: str | None = None) -> str:
    """Header ``WWW-Authenticate`` que aponta para o metadata (RFC 9728 §5.1).

    O 401 de um RS deve indicar onde achar os metadados de descoberta.
    """
    parts = [
        'Bearer realm="mcp"',
        f'resource_metadata="{resource.rstrip("/")}{WELL_KNOWN_PROTECTED_RESOURCE}"',
    ]
    if scope:
        parts.append(f'scope="{scope}"')
    return ", ".join(parts)


__all__ = [
    "WELL_KNOWN_PROTECTED_RESOURCE",
    "protected_resource_metadata",
    "mount_protected_resource_metadata",
    "protected_resource_challenge",
]
