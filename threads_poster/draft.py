"""Read the Threads draft out of a Discourse topic.

The drafter (postmaker) posts one comment per network, wrapping the ready posts
in a details block. Each post is a ```md fence with the post text, optionally
followed by a char-count line and image markup for that post:

    [details="Threads"]

    ```md
    first post text
    ```
    `42/500`
    ![](upload://a.jpeg)

    ```md
    second post text
    ```

    [/details]

Approval is a LIKE on that comment (Discourse action id 2). Post text comes from
the fences; each post's images are the `![](ref)` that follow its fence (before
the next fence). Refs are raw Discourse `upload://` short-urls (or full URLs);
resolving them to public URLs happens in the caller via the Discourse API.
"""

import re
from dataclasses import dataclass, field

_FENCE = re.compile(r"```md\n(.*?)\n```", re.DOTALL)
_IMG_MD = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_SUMMARY = re.compile(r"<summary>(.*?)</summary>", re.DOTALL)
_TOPIC = re.compile(r"^[ \t>]*Topic:[ \t]*#?(.+?)[ \t]*$", re.MULTILINE | re.IGNORECASE)
_LIKE_ACTION_ID = 2


@dataclass
class Post:
    text: str
    images: list[str] = field(default_factory=list)


def find_draft_post(topic: dict, label: str) -> dict | None:
    """The network's draft comment, matched via its already-rendered details
    summary in the topic JSON -- no extra API call per comment. Discourse renders
    the summary with surrounding whitespace, so match on the stripped text. A
    published draft's summary is prefixed (e.g. "✅ Threads") and won't match --
    which is fine, it's tagged published and skipped anyway."""
    for p in (topic.get("post_stream") or {}).get("posts") or []:
        if any(s.strip() == label for s in _SUMMARY.findall(p.get("cooked") or "")):
            return p
    return None


def is_liked(post: dict) -> bool:
    """True once anyone has liked the draft comment -- the approval signal."""
    for action in post.get("actions_summary") or []:
        if action.get("id") == _LIKE_ACTION_ID and (action.get("count") or 0) > 0:
            return True
    return bool(post.get("like_count"))


def parse_topic(raw: str) -> str | None:
    """A `Topic: <tag>` line outside the fenced post text -> its topic_tag, or
    None. Optional -- absent means no topic tag (existing behaviour unchanged)."""
    m = _TOPIC.search(_FENCE.sub("", raw))
    return m.group(1).strip() if m else None


def parse_posts(raw: str) -> list[Post]:
    """Ordered posts: each fence's text plus the image refs that follow it."""
    fences = list(_FENCE.finditer(raw))
    posts = []
    for i, m in enumerate(fences):
        end = fences[i + 1].start() if i + 1 < len(fences) else len(raw)
        refs = _IMG_MD.findall(raw[m.end():end])
        posts.append(Post(text=m.group(1), images=refs))
    return posts
