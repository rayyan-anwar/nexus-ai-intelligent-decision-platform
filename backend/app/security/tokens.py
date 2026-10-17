"""Bearer-token authentication. Only SHA-256 hashes of tokens are ever configured or compared."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Principal:
    name: str
    role: str  # "user" | "admin"


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_bearer(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    value = value.strip()
    if scheme.lower() != "bearer" or not value or len(value) > 512:
        return None
    return value


def _match(presented_hash: str, hashes: Iterable[str]) -> bool:
    found = False
    for h in hashes:  # no early exit: constant work per configured hash
        found |= hmac.compare_digest(presented_hash, h)
    return found


def authenticate(header: str | None, api_hashes: Iterable[str], admin_hashes: Iterable[str]) -> Principal | None:
    token = parse_bearer(header)
    if token is None:
        return None
    digest = hash_token(token)
    if _match(digest, admin_hashes):
        return Principal("admin-token", "admin")
    if _match(digest, api_hashes):
        return Principal("api-token", "user")
    return None
