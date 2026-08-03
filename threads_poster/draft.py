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

_FENCE = re.compile(r"```md\n(.*?)\n```", re.DOTALL)
_LIKE_ACTION_ID = 2


def find_draft_post(topic: dict, label: str) -> dict | None:
    """The network's draft comment, matched via its already-rendered details
    summary in the topic JSON -- no extra API call per comment (the raw is only
    fetched later, once the draft is approved). Returns the post dict or None."""
    marker = f">{label}</summary>"
    for p in (topic.get("post_stream") or {}).get("posts") or []:
        if marker in (p.get("cooked") or ""):
            return p
    return None


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
