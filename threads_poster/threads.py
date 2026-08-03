"""Minimal Threads Graph API client (stdlib only).

Covers the OAuth token lifecycle now; publishing endpoints come later.

Token lifecycle (Meta docs):
  1. authorize   -> browser sends the user to threads.net/oauth/authorize,
                    which redirects back to redirect_uri with ?code=<CODE>.
  2. code        -> short-lived token (1h):  POST graph.threads.net/oauth/access_token
  3. short-lived -> long-lived token (60d):  GET  graph.threads.net/access_token
  4. refresh     -> extend long-lived (60d): GET  graph.threads.net/refresh_access_token

Hosts:
  - authorization page:  https://threads.net
  - graph/token/publish: https://graph.threads.net
"""

import json
import urllib.error
import urllib.parse
import urllib.request

AUTH_HOST = "https://threads.net"
GRAPH_HOST = "https://graph.threads.net"

SCOPES = [
    "threads_basic",
    "threads_content_publish",
    # cross-reshare a published thread to the user's linked IG account as a Story
    # (native Threads API feature via crossreshare_to_ig on the create-post call)
    "threads_share_to_instagram",
]


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "threads-poster/0.1"})
    return _read(req, "GET", url)


def _post(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "threads-poster/0.1",
        },
    )
    return _read(req, "POST", url)


def _read(req: urllib.request.Request, method: str, url: str) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        # strip query so client_secret / code never land in logs
        safe = url.split("?", 1)[0]
        raise RuntimeError(f"{method} {safe} -> HTTP {e.code}: {detail}") from None


def authorize_url(app_id: str, redirect_uri: str, state: str = "") -> str:
    """The URL to open in a browser to grant the app access (manual flow)."""
    q = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "scope": ",".join(SCOPES),
        "response_type": "code",
    }
    if state:
        q["state"] = state
    return f"{AUTH_HOST}/oauth/authorize?" + urllib.parse.urlencode(q)


def exchange_code(app_id: str, app_secret: str, redirect_uri: str, code: str) -> dict:
    """Authorization code -> short-lived token. Returns {access_token, user_id}."""
    return _post(
        f"{GRAPH_HOST}/oauth/access_token",
        {
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )


def exchange_long_lived(app_secret: str, short_lived_token: str) -> dict:
    """Short-lived -> long-lived (~60d). Returns {access_token, token_type, expires_in}."""
    return _get(
        f"{GRAPH_HOST}/access_token?"
        + urllib.parse.urlencode(
            {
                "grant_type": "th_exchange_token",
                "client_secret": app_secret,
                "access_token": short_lived_token,
            }
        )
    )


def refresh_long_lived(long_lived_token: str) -> dict:
    """Extend a long-lived token by another ~60d. Returns {access_token, expires_in}."""
    return _get(
        f"{GRAPH_HOST}/refresh_access_token?"
        + urllib.parse.urlencode(
            {
                "grant_type": "th_refresh_token",
                "access_token": long_lived_token,
            }
        )
    )


# --- publishing ------------------------------------------------------------

API = f"{GRAPH_HOST}/v1.0"


def create_container(
    user_id: str,
    access_token: str,
    *,
    media_type: str,
    text: str | None = None,
    image_url: str | None = None,
    children: list[str] | None = None,
    is_carousel_item: bool = False,
    reply_to_id: str | None = None,
    topic_tag: str | None = None,
    crossreshare_to_ig: bool = False,
    dark_mode: bool = False,
) -> dict:
    """Create a media container. media_type is TEXT, IMAGE or CAROUSEL:
      - TEXT: text
      - IMAGE: image_url (+ optional text; is_carousel_item for a carousel child)
      - CAROUSEL: children (ids of IMAGE items) + optional text
    reply_to_id chains it under another post (thread). crossreshare_to_ig=True
    also reshares to Instagram Stories (response carries crossreshare_to_ig_status).
    Returns {id, ...}."""
    data = {"media_type": media_type, "access_token": access_token}
    if text is not None:
        data["text"] = text
    if image_url is not None:
        data["image_url"] = image_url
    if children:
        data["children"] = ",".join(children)
    if is_carousel_item:
        data["is_carousel_item"] = "true"
    if reply_to_id:
        data["reply_to_id"] = reply_to_id
    if topic_tag:
        data["topic_tag"] = topic_tag
    if crossreshare_to_ig:
        data["crossreshare_to_ig_dark_mode" if dark_mode else "crossreshare_to_ig"] = "true"
    return _post(f"{API}/{user_id}/threads", data)


def get_status(container_id: str, access_token: str) -> str:
    """Container processing status: FINISHED / IN_PROGRESS / ERROR / EXPIRED."""
    r = _get(f"{API}/{container_id}?"
             + urllib.parse.urlencode({"fields": "status", "access_token": access_token}))
    return r.get("status", "")


def publish_container(user_id: str, access_token: str, creation_id: str) -> dict:
    """Publish a previously created container. Returns {id} of the live post."""
    return _post(
        f"{API}/{user_id}/threads_publish",
        {"creation_id": creation_id, "access_token": access_token},
    )


def get_permalink(media_id: str, access_token: str) -> str:
    """Public URL of a published post."""
    r = _get(f"{API}/{media_id}?"
             + urllib.parse.urlencode({"fields": "permalink", "access_token": access_token}))
    return r.get("permalink", "")
