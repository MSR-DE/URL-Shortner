"""Short-code generation.

Codes are random base62 strings rather than an encoding of the row's primary
key. Random codes cost one extra uniqueness check, but they keep the URL space
non-enumerable: with sequential ids, anyone can walk /1, /2, /3 and read every
link that has ever been shortened.
"""

import secrets
import string

# 0-9 A-Z a-z -> 62 symbols, all URL-safe and requiring no escaping.
ALPHABET = string.digits + string.ascii_uppercase + string.ascii_lowercase

# Paths served by the application itself, which therefore must never be handed
# out as a short code.
RESERVED_CODES = frozenset({"docs", "redoc", "openapi", "health", "stats", "shorten"})


def generate_short_code(length: int) -> str:
    """Return a cryptographically random base62 code of `length` characters."""
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if code.lower() not in RESERVED_CODES:
            return code
