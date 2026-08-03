"""Publish a list of posts to Threads as a single thread.

Each post is created as a container then published; posts after the first chain
under the previous published post via reply_to_id. A post with no images is a
TEXT container, with one image an IMAGE container, with several a CAROUSEL of
IMAGE items. The root post also cross-reshares to Instagram Stories when enabled.

Containers (especially image ones) need a moment to process, so we wait for
FINISHED before publishing.
"""

import time

from . import threads
from .draft import Post

_STATUS_TRIES = 20
_STATUS_DELAY = 3  # seconds between status checks


class PublishError(RuntimeError):
    """Raised when a thread doesn't fully publish. `published` holds the media
    ids that DID go live before the failure, so the caller can decide whether to
    mark the topic done (something is live -> don't re-post) or retry (nothing
    went live)."""

    def __init__(self, message: str, published: list[str]):
        super().__init__(message)
        self.published = published


def log(msg: str) -> None:
    print(f"[threads-poster] {msg}", flush=True)


def _await_ready(container_id: str, token: str) -> None:
    for _ in range(_STATUS_TRIES):
        status = threads.get_status(container_id, token)
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {container_id} status {status}")
        time.sleep(_STATUS_DELAY)
    # Timed out still IN_PROGRESS -> let publish try anyway.


def _build_container(user_id, token, post: Post, reply_to, topic_tag, crossreshare, dark) -> dict:
    common = dict(reply_to_id=reply_to, topic_tag=topic_tag,
                  crossreshare_to_ig=crossreshare, dark_mode=dark)
    if not post.images:
        return threads.create_container(user_id, token, media_type="TEXT", text=post.text, **common)
    if len(post.images) == 1:
        return threads.create_container(
            user_id, token, media_type="IMAGE", image_url=post.images[0],
            text=post.text or None, **common,
        )
    children = [
        threads.create_container(user_id, token, media_type="IMAGE", image_url=u,
                                 is_carousel_item=True)["id"]
        for u in post.images
    ]
    return threads.create_container(
        user_id, token, media_type="CAROUSEL", children=children, text=post.text or None, **common,
    )


def publish_thread(
    user_id: str,
    token: str,
    posts: list[Post],
    *,
    topic_tag: str | None = None,
    crossreshare_to_ig: bool = True,
    dark_mode: bool = False,
) -> list[str]:
    """Publish posts in order, chaining replies. Returns the published media ids.
    topic_tag and crossreshare_to_ig apply to the ROOT post only."""
    media_ids: list[str] = []
    reply_to: str | None = None
    for i, post in enumerate(posts):
        root = i == 0
        try:
            container = _build_container(
                user_id, token, post, reply_to,
                topic_tag if root else None, root and crossreshare_to_ig, dark_mode,
            )
            if root and crossreshare_to_ig:
                status = container.get("crossreshare_to_ig_status", "unknown")
                log(f"crossreshare_to_ig_status={status}")
            _await_ready(container["id"], token)
            media = threads.publish_container(user_id, token, container["id"])
        except RuntimeError as e:
            raise PublishError(f"post {i + 1}/{len(posts)}: {e}", media_ids) from e
        media_ids.append(media["id"])
        reply_to = media["id"]
        imgs = f", {len(post.images)} img" if post.images else ""
        log(f"published post {i + 1}/{len(posts)}{imgs} -> {media['id']}")
    return media_ids
