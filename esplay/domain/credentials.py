"""CredentialManager — generates and stores cluster credentials.

Passwords are cryptographically strong (secrets module) and are ONLY
displayed in the credentials panel and written to the state file (mode 0o600).
They are never logged.
"""

from __future__ import annotations

import secrets
import string

_ALPHABET = string.ascii_letters + string.digits + "-_"
_SPECIAL = "!@#$%^&*"


def generate_password(length: int = 20) -> str:
    """Return a URL-safe random password.

    We avoid characters that break URL embedding (/, ?, #, @) so the
    connection string ``http://elastic:<password>@localhost:9200`` always works.
    """
    # Ensure at least one digit and one special char.
    core = [secrets.choice(_ALPHABET) for _ in range(length - 2)]
    core.append(secrets.choice(string.digits))
    core.append(secrets.choice(_SPECIAL))
    secrets.SystemRandom().shuffle(core)
    return "".join(core)
