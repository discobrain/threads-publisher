"""CLI.

Auth (manual OAuth flow -- do this once, then refresh periodically):

  threads-poster auth-url        print the URL to open in a browser to grant access
  threads-poster auth <code>     exchange the ?code=... from the redirect for a
                                 long-lived token and save it to the token file
  threads-poster refresh         refresh the stored long-lived token (~60d -> +60d)
  threads-poster token           show stored token status (value masked)

Publishing commands (run/once) come later.
"""

import sys
import time

from . import config, threads, token_store


def _cmd_auth_url(cfg: config.Config) -> int:
    print(threads.authorize_url(cfg.app_id, cfg.redirect_uri))
    print(
        "\nOpen this in a browser, approve, then copy the `code` value from the\n"
        "redirect URL (it looks like <redirect_uri>?code=XXXXX#_) and run:\n\n"
        "  threads-poster auth <code>",
        file=sys.stderr,
    )
    return 0


def _cmd_auth(cfg: config.Config, code: str) -> int:
    code = code.strip().rstrip("#_")  # the redirect appends a literal #_
    short = threads.exchange_code(cfg.app_id, cfg.app_secret, cfg.redirect_uri, code)
    short_token = short["access_token"]
    user_id = str(short.get("user_id", ""))

    long = threads.exchange_long_lived(cfg.app_secret, short_token)
    now = int(time.time())
    tok = token_store.Token(
        access_token=long["access_token"],
        user_id=user_id,
        expires_at=now + int(long.get("expires_in", 0)),
        obtained_at=now,
    )
    token_store.save(cfg.token_path, tok)
    days = tok.expires_in(now) // 86400
    print(f"Saved long-lived token to {cfg.token_path} (user {user_id}, expires in ~{days}d)")
    return 0


def _cmd_refresh(cfg: config.Config) -> int:
    tok = token_store.load(cfg.token_path)
    if tok is None:
        print(f"No token at {cfg.token_path}; run `auth` first.", file=sys.stderr)
        return 1
    res = threads.refresh_long_lived(tok.access_token)
    now = int(time.time())
    new = token_store.Token(
        access_token=res["access_token"],
        user_id=tok.user_id,
        expires_at=now + int(res.get("expires_in", 0)),
        obtained_at=now,
    )
    token_store.save(cfg.token_path, new)
    days = new.expires_in(now) // 86400
    print(f"Refreshed; expires in ~{days}d")
    return 0


def _cmd_token(cfg: config.Config) -> int:
    tok = token_store.load(cfg.token_path)
    if tok is None:
        print(f"No token at {cfg.token_path}; run `auth-url` then `auth <code>`.")
        return 1
    now = int(time.time())
    left = tok.expires_in(now)
    masked = tok.access_token[:6] + "..." + tok.access_token[-4:]
    state = "EXPIRED" if left <= 0 else f"~{left // 86400}d left"
    print(f"user={tok.user_id} token={masked} ({state})")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "help"
    rest = argv[1:]

    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0

    cfg = config.load()

    if cmd == "auth-url":
        return _cmd_auth_url(cfg)
    if cmd == "auth":
        if not rest:
            print("usage: threads-poster auth <code>", file=sys.stderr)
            return 2
        return _cmd_auth(cfg, rest[0])
    if cmd == "refresh":
        return _cmd_refresh(cfg)
    if cmd == "token":
        return _cmd_token(cfg)

    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
