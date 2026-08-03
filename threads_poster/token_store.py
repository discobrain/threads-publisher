"""Persist the long-lived Threads access token to a local JSON file.

Unlike Discourse credentials (which are static env secrets), the access token
rotates: it is issued for ~60 days and must be refreshed before it expires. The
process therefore needs a writable place to keep the current token plus the
timestamp it expires at, so it can decide when to refresh.

File shape:
  {
    "access_token": "...",
    "user_id": "17841400000000000",
    "expires_at": 1735689600,   # unix seconds; when the token stops working
    "obtained_at": 1730505600   # unix seconds; when we last (re)issued it
  }
"""

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    access_token: str
    user_id: str
    expires_at: int
    obtained_at: int

    def expires_in(self, now: int) -> int:
        return self.expires_at - now


def load(path: str) -> Token | None:
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        d = json.load(f)
    return Token(
        access_token=d["access_token"],
        user_id=str(d.get("user_id", "")),
        expires_at=int(d.get("expires_at", 0)),
        obtained_at=int(d.get("obtained_at", 0)),
    )


def save(path: str, token: Token) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(
            {
                "access_token": token.access_token,
                "user_id": token.user_id,
                "expires_at": token.expires_at,
                "obtained_at": token.obtained_at,
            },
            f,
            indent=2,
        )
    os.replace(tmp, path)
    os.chmod(path, 0o600)
