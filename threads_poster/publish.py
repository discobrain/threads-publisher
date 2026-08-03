"""Publish a list of post bodies to Threads as a single thread.

Each post is a two-step Graph call: create a container, then publish it. Posts
after the first are chained under the previous published post via reply_to_id.
The root post also cross-reshares to Instagram Stories when enabled.

A freshly created container may need a moment before it can be published, so
publish is retried a few times.
"""

import time

from . import threads

_PUBLISH_RETRIES = 5
_PUBLISH_BACKOFF = 3  # seconds between publish attempts


def log(msg: str) -> None:
    print(f"[threads-poster] {msg}", flush=True)


def _publish_with_retry(user_id: str, token: str, creation_id: str) -> dict:
    last = None
    for attempt in range(1, _PUBLISH_RETRIES + 1):
        try:
            return threads.publish_container(user_id, token, creation_id)
        except RuntimeError as e:  # container not processed yet -> wait and retry
            last = e
            if attempt < _PUBLISH_RETRIES:
                time.sleep(_PUBLISH_BACKOFF)
    raise RuntimeError(f"publish failed after {_PUBLISH_RETRIES} attempts: {last}")


def publish_thread(
    user_id: str,
    token: str,
    posts: list[str],
    *,
    crossreshare_to_ig: bool = True,
    dark_mode: bool = False,
) -> list[str]:
    """Publish posts in order, chaining replies. Returns the published media ids.
    crossreshare_to_ig applies to the ROOT post only (one Story per thread)."""
    media_ids: list[str] = []
    reply_to: str | None = None
    for i, text in enumerate(posts):
        root = i == 0
        container = threads.create_container(
            user_id,
            token,
            text,
            reply_to_id=reply_to,
            crossreshare_to_ig=(root and crossreshare_to_ig),
            dark_mode=dark_mode,
        )
        if root and crossreshare_to_ig:
            status = container.get("crossreshare_to_ig_status", "unknown")
            log(f"crossreshare_to_ig_status={status}")
            if status == "FAILED":
                log("IG Story cross-reshare FAILED (thread still publishes); "
                    "check the Threads account has a linked Instagram account")
        media = _publish_with_retry(user_id, token, container["id"])
        media_ids.append(media["id"])
        reply_to = media["id"]
        log(f"published post {i + 1}/{len(posts)} -> {media['id']}")
    return media_ids
