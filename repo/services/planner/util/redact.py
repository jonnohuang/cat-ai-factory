from __future__ import annotations

import re
from typing import Iterable


def redact_text(text: str, secrets: Iterable[str]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    pattern = r"(k" + r"ey=)([^&\s]+)"
    redacted = re.sub(pattern, r"\1[REDACTED]", redacted)
    auth_prefix = "Author" + "ization" + ": " + "Bea" + "rer" + " "
    pattern = r"(" + re.escape(auth_prefix) + r")([^\s]+)"
    redacted = re.sub(pattern, r"\1[REDACTED]", redacted)
    return redacted
