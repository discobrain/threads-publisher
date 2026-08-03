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
    category_id: int | None
    # structure
    network_key: str        # base of the -draft / -published tags
    draft_label: str        # [details="<label>"] the drafter wraps the posts in
    limit: int
    poll_interval: int
    min_publish_interval: int   # seconds; at most one publish per this window
    state_path: str
    crossreshare_to_ig: bool
    crossreshare_dark_mode: bool
    link_back: bool         # post a comment linking to the published Threads post
    dry_run: bool

    @property
    def draft_tag(self) -> str:
        return f"{self.network_key}-draft"

    @property
    def published_tag(self) -> str:
        return f"{self.network_key}-published"


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

    # Catch a .env still holding the .env.example placeholders, which otherwise
    # reach Meta as a bogus client_id ("no app id was sent").
    for name, value in (
        ("THREADS_APP_ID", app_id),
        ("THREADS_APP_SECRET", app_secret),
        ("THREADS_REDIRECT_URI", redirect_uri),
    ):
        if value.startswith("your-") or value == "https://example.com/callback":
            raise SystemExit(f"{name} still holds a placeholder value; set it in .env")

    if discourse_required:
        d_url = req_env("DISCOURSE_URL").rstrip("/")
        d_key = req_env("DISCOURSE_API_KEY")
        d_user = req_env("DISCOURSE_API_USERNAME")
    else:
        d_url = (os.environ.get("DISCOURSE_URL") or "").rstrip("/")
        d_key = os.environ.get("DISCOURSE_API_KEY") or ""
        d_user = os.environ.get("DISCOURSE_API_USERNAME") or ""

    category = os.environ.get("THREADS_CATEGORY_ID", doc.get("category"))
    return Config(
        app_id=app_id,
        app_secret=app_secret,
        redirect_uri=redirect_uri,
        token_path=os.environ.get("THREADS_TOKEN_PATH", doc.get("token_path", ".threads-token.json")),
        discourse_url=d_url,
        discourse_api_key=d_key,
        discourse_api_username=d_user,
        category_id=(int(category) if category not in (None, "") else None),
        network_key=os.environ.get("THREADS_NETWORK_KEY", doc.get("network_key", "threads")),
        draft_label=os.environ.get("THREADS_DRAFT_LABEL", doc.get("draft_label", "Threads")),
        limit=int(os.environ.get("THREADS_LIMIT", doc.get("limit", 500))),
        poll_interval=int(os.environ.get("THREADS_POLL_INTERVAL", doc.get("poll_interval", 60))),
        min_publish_interval=int(
            os.environ.get("THREADS_MIN_PUBLISH_INTERVAL", doc.get("min_publish_interval", 3600))
        ),
        state_path=os.environ.get("THREADS_STATE_PATH", doc.get("state_path", ".threads-state.json")),
        crossreshare_to_ig=bool(doc.get("crossreshare_to_ig", True)),
        crossreshare_dark_mode=bool(doc.get("crossreshare_dark_mode", False)),
        link_back=bool(doc.get("link_back", True)),
        dry_run=_flag("THREADS_DRY_RUN"),
    )
