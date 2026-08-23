"""Verifies Clerk-issued session JWTs and resolves the local User row.

Clerk signs session tokens with RS256; the public keys live at
`{issuer}/.well-known/jwks.json`, where `issuer` is the Clerk "Frontend API"
URL for the app (e.g. "https://your-app-name.clerk.accounts.dev" in dev, or
your custom domain in prod). PyJWKClient fetches and caches that keyset so
verification never needs Clerk's *secret* key, only the public issuer URL.

First-successful-verification-provisions-a-row is the standard pattern for
pairing Clerk (or any external auth provider) with your own DB: Clerk owns
the identity, this app just needs a local primary key to hang UserBook rows
off of.
"""

import os

import jwt
from fastapi import Depends, Header, HTTPException
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

CLERK_ISSUER = os.environ.get("CLERK_ISSUER")

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        if not CLERK_ISSUER:
            raise RuntimeError(
                "CLERK_ISSUER is not set (expected in app/.env) — this is your Clerk "
                "app's Frontend API URL, e.g. https://your-app-name.clerk.accounts.dev"
            )
        # cache_keys caches the fetched JWKS in-process (PyJWKClient's default
        # lifespan is 5 minutes) so most requests don't refetch the keyset.
        _jwks_client = PyJWKClient(f"{CLERK_ISSUER}/.well-known/jwks.json", cache_keys=True)
    return _jwks_client


def verify_clerk_token(token: str) -> dict:
    """Validate signature, issuer, and expiry; return the token's claims."""
    client = _get_jwks_client()
    signing_key = client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=CLERK_ISSUER,
        # Clerk session tokens don't set a fixed "aud" claim by default.
        options={"verify_aud": False},
    )


def _bearer_token(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")
    return token


def get_current_user(
    authorization: str = Header(...),
    db: Session = Depends(get_db),
) -> User:
    token = _bearer_token(authorization)
    try:
        claims = verify_clerk_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc

    clerk_id = claims.get("sub")
    if not clerk_id:
        raise HTTPException(status_code=401, detail="token missing subject claim")

    user = db.query(User).filter(User.clerk_id == clerk_id).first()
    if user is None:
        user = User(clerk_id=clerk_id, email=claims.get("email"))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
