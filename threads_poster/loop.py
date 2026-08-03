"""Poll loop: publish approved Threads drafts, mark them published.

Per pass, for every topic tagged `<key>-draft` and not yet `<key>-published`:
  - find the Threads draft comment and check it carries a LIKE (approval)
  - parse the fenced posts and publish them as a thread (root cross-reshared to
    Instagram Stories)
  - tag the topic `<key>-published`

The published tag is set AFTER a successful publish, so a rejected post (bad
text, a gated feature, rate limit) never marks a topic published -- it just
retries next pass. If a multi-post thread fails partway, whatever already went
live is enough to tag the topic (so those posts are never duplicated) and the
remainder is left for manual finishing.

State lives in Discourse tags + the like; nothing is stored locally beyond the
access token.
"""

import time

from . import draft, publish, threads, token_store
from .discourse import Discourse

REFRESH_BEFORE = 7 * 86400  # refresh the long-lived token when <7 days remain


def log(msg: str) -> None:
    print(f"[threads-poster] {msg}", flush=True)


def _load_token(cfg) -> token_store.Token:
    tok = token_store.load(cfg.token_path)
    if tok is None:
        raise SystemExit(f"No token at {cfg.token_path}; run get-token first.")
    return tok


def _maybe_refresh(cfg, tok: token_store.Token) -> token_store.Token:
    now = int(time.time())
    if tok.expires_in(now) > REFRESH_BEFORE:
        return tok
    log(f"token has ~{tok.expires_in(now) // 86400}d left; refreshing")
    res = threads.refresh_long_lived(tok.access_token)
    new = token_store.Token(
        access_token=res["access_token"],
        user_id=tok.user_id,
        expires_at=now + int(res.get("expires_in", 0)),
        obtained_at=now,
    )
    token_store.save(cfg.token_path, new)
    return new


def _in_scope(cfg, topic: dict) -> bool:
    return cfg.category_id is None or topic.get("category_id") == cfg.category_id


def _published_comment(permalink: str, n: int) -> str:
    if n > 1:
        return f"_🧵 Published to Threads ({n} posts): {permalink}_\n"
    return f"_🧵 Published to Threads: {permalink}_\n"


def _link_back(cfg, dc: Discourse, token: str, tid: int, media_ids: list[str]) -> None:
    """Best-effort: comment the published post's URL back into the topic."""
    if not cfg.link_back or not media_ids:
        return
    try:
        permalink = threads.get_permalink(media_ids[0], token)
        if permalink:
            dc.create_post(tid, _published_comment(permalink, len(media_ids)))
            log(f"topic {tid}: linked published post back in Discourse")
    except Exception as e:
        log(f"topic {tid}: published, but link-back comment failed: {e}")


def process_topic(cfg, dc: Discourse, tok: token_store.Token, topic: dict) -> None:
    tid = topic["id"]
    tags = set(topic.get("tags") or [])
    if cfg.published_tag in tags:
        return  # already published
    if cfg.draft_tag not in tags:
        return  # draft not ready

    post, raw = draft.find_draft_post(dc, topic, cfg.draft_label)
    if post is None:
        return  # no Threads draft comment on this topic
    if not draft.is_liked(post):
        return  # not approved yet -- waiting for a like

    posts = draft.parse_posts(raw)
    if not posts:
        log(f"topic {tid}: draft comment has no fenced posts, skipping")
        return
    if draft.has_images(raw):
        log(f"topic {tid}: draft has image markup; posting text only (images unsupported)")

    log(f"topic {tid}: approved, publishing {len(posts)} post(s)")
    if cfg.dry_run:
        for i, p in enumerate(posts, 1):
            log(f"[dry-run] topic {tid} post {i}/{len(posts)} ({len(p)} chars):\n{p}")
        return

    user_id = tok.user_id or "me"
    try:
        media_ids = publish.publish_thread(
            user_id,
            tok.access_token,
            posts,
            crossreshare_to_ig=cfg.crossreshare_to_ig,
            dark_mode=cfg.crossreshare_dark_mode,
        )
    except publish.PublishError as e:
        if e.published:
            # Some posts are already live -> mark done so we never re-post them;
            # the rest need finishing by hand.
            dc.set_tags(tid, sorted(tags | {cfg.published_tag}))
            _link_back(cfg, dc, tok.access_token, tid, e.published)
            log(f"topic {tid}: PARTIAL publish ({len(e.published)} live) then failed: {e}. "
                f"Tagged {cfg.published_tag} to avoid re-posting; finish the remainder manually.")
        else:
            log(f"topic {tid}: publish failed, nothing posted -- will retry next pass: {e}")
        return

    # Full success -> tag AFTER posting so a failed publish never marks a topic
    # published (the tiny crash window between last post and tagging is the only
    # residual duplicate risk).
    dc.set_tags(tid, sorted(tags | {cfg.published_tag}))
    _link_back(cfg, dc, tok.access_token, tid, media_ids)
    log(f"topic {tid}: published")


def run_once(cfg, dc: Discourse, tok: token_store.Token) -> None:
    for t in dc.topics_with_tag(cfg.draft_tag):
        if not _in_scope(cfg, t):
            continue
        try:
            process_topic(cfg, dc, tok, dc.get_topic(t["id"]))
        except Exception as e:  # one bad topic shouldn't kill the pass
            log(f"topic {t.get('id')}: error: {e}")


def run(cfg) -> None:
    dc = Discourse(cfg.discourse_url, cfg.discourse_api_key, cfg.discourse_api_username)
    scope = f"tag='{cfg.draft_tag}'"
    if cfg.category_id is not None:
        scope += f" category={cfg.category_id}"
    log(f"up. {scope} every {cfg.poll_interval}s, crossreshare_to_ig={cfg.crossreshare_to_ig}, "
        f"dry_run={cfg.dry_run}")
    while True:
        try:
            tok = _maybe_refresh(cfg, _load_token(cfg))
            run_once(cfg, dc, tok)
        except SystemExit as e:
            log(str(e))  # e.g. no token yet; keep looping so it recovers
        except Exception as e:
            log(f"pass error: {e}")
        time.sleep(cfg.poll_interval)
