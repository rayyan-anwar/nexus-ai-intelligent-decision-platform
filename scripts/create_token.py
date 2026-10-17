"""Generate an API token and the SHA-256 hash the server is configured with.

Only the HASH goes into .env (NEXUS_API_TOKEN_HASHES / NEXUS_ADMIN_TOKEN_HASHES).
Give the TOKEN to the person or system that will call the API; it is not stored anywhere.
"""

import hashlib
import secrets

token = secrets.token_urlsafe(32)
print(f"token (keep secret, shown once): {token}")
print(f"hash  (put in .env):             {hashlib.sha256(token.encode()).hexdigest()}")
