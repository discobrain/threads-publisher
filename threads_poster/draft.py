"""Read the Threads draft out of a Discourse topic.

The drafter (postmaker) posts one comment per network, wrapping the ready posts
in a details block and each post in a ```md fence:

    [details="Threads"]

    ```md
    first post text
    ```
    `42/500`

    ```md
    second post text
    ```

    [/details]

Approval is a LIKE on that comment (Discourse action id 2). We never depend on
the surrounding prose -- only the fenced post bodies, in order.
"""

import re

from .discourse import Discourse

_FENCE = re.compile(r"```md\n(.*?)\n```", re.DOTALL)
_LIKE_ACTION_ID = 2


def find_draft_post(dc: Discourse, topic: dict, label: str) -> tuple[dict | None, str]:
    """Return (post_object, raw_markdown) for the network's draft comment, or
    (None, "") if the topic has no such comment yet."""
    marker = f'[details="{label}"]'
    for p in (topic.get("post_stream") or {}).get("posts") or []:
        raw = dc.get_post_raw(p["id"])
        if marker in raw:
            return p, raw
    return None, ""


def is_liked(post: dict) -> bool:
    """True once anyone has liked the draft comment -- the approval signal."""
    for action in post.get("actions_summary") or []:
        if action.get("id") == _LIKE_ACTION_ID and (action.get("count") or 0) > 0:
            return True
    return bool(post.get("like_count"))


def parse_posts(raw: str) -> list[str]:
    """Ordered post bodies, one per ```md fence, verbatim."""
    return [m.group(1) for m in _FENCE.finditer(raw)]


def has_images(raw: str) -> bool:
    """Whether the draft carries image markup we don't publish yet."""
    return "![" in raw
