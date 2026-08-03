"""Configuration.

Split by concern, mirroring postmaker:
  - Secrets (Threads app id/secret, redirect uri, Discourse creds) come from the
    ENVIRONMENT only.
  - Structure (post limits, split, poll cadence) is declared in a TOML file.

The long-lived access token is NOT a config value: it is obtained via the OAuth
flow and persisted to a token file (see token_store), because the process must
be able to refresh and rewrite it.
"""

import os
import tomllib
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # Threads app credentials (Meta App -> Threads use case)
    app_id: str
    app_secret: str
    redirect_uri: str
    token_path: str
    # Discourse (source of drafts) -- optional for the pure-auth commands
    discourse_url: str
    discourse_api_key: str
    discourse_api_username: str
    # structure
    limit: int
    poll_interval: int
    dry_run: bool


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _load_toml(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def load(discourse_required: bool = False) -> Config:
    doc = _load_toml(os.environ.get("THREADS_CONFIG", "threads_poster.toml"))

    def req_env(name: str) -> str:
        v = os.environ.get(name)
        if not v:
            raise SystemExit(f"Missing required env var: {name}")
        return v

    app_id = req_env("THREADS_APP_ID")
    app_secret = req_env("THREADS_APP_SECRET")
    redirect_uri = req_env("THREADS_REDIRECT_URI")

    if discourse_required:
        d_url = req_env("DISCOURSE_URL").rstrip("/")
        d_key = req_env("DISCOURSE_API_KEY")
        d_user = req_env("DISCOURSE_API_USERNAME")
    else:
        d_url = (os.environ.get("DISCOURSE_URL") or "").rstrip("/")
        d_key = os.environ.get("DISCOURSE_API_KEY") or ""
        d_user = os.environ.get("DISCOURSE_API_USERNAME") or ""

    return Config(
        app_id=app_id,
        app_secret=app_secret,
        redirect_uri=redirect_uri,
        token_path=os.environ.get("THREADS_TOKEN_PATH", doc.get("token_path", ".threads-token.json")),
        discourse_url=d_url,
        discourse_api_key=d_key,
        discourse_api_username=d_user,
        limit=int(os.environ.get("THREADS_LIMIT", doc.get("limit", 500))),
        poll_interval=int(os.environ.get("THREADS_POLL_INTERVAL", doc.get("poll_interval", 60))),
        dry_run=_flag("THREADS_DRY_RUN"),
    )
