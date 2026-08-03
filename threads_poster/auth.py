"""OAuth orchestration: turn an authorization code into a stored long-lived token.

Shared by the `auth` CLI subcommand and the `get-token` helper so the exchange
logic lives in exactly one place.
"""

import urllib.parse

from . import threads, token_store
from .config import Config


def code_from_input(arg: str) -> str:
    """Accept either a bare authorization code or the full redirect URL that the
    browser landed on, and return just the code.

    The redirect looks like `<redirect_uri>?code=XXXXX#_`; a pasted bare code may
    carry the same trailing `#_`.
    """
    arg = arg.strip()
    if "://" in arg:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(arg).query)
        code = (params.get("code") or [""])[0]
        if not code:
            raise SystemExit("No `code` parameter found in the URL")
        return code
    return arg.rstrip("#_")


def fetch_and_store(cfg: Config, code: str, now: int) -> token_store.Token:
    """Code -> short-lived -> long-lived token, persisted to the token file."""
    short = threads.exchange_code(cfg.app_id, cfg.app_secret, cfg.redirect_uri, code)
    long = threads.exchange_long_lived(cfg.app_secret, short["access_token"])
    tok = token_store.Token(
        access_token=long["access_token"],
        user_id=str(short.get("user_id", "")),
        expires_at=now + int(long.get("expires_in", 0)),
        obtained_at=now,
    )
    token_store.save(cfg.token_path, tok)
    return tok
