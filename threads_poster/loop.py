"""Poll loop: publish approved Threads drafts, mark them published.

Per pass, for every topic tagged `<key>-draft` and not yet `<key>-published`:
  - find the Threads draft comment and check it carries a LIKE (approval)
  - parse the fenced posts and publish them as a thread (root cross-reshared to
    Instagram Stories)
  - tag the topic `<key>-published`

The published tag is set BEFORE posting (tag-first), matching postmaker: for an
irreversible public post, never risk a duplicate on the next pass. A publish
error after tagging is logged loudly -- remove the tag to retry that topic.

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

    # Tag-first: mark published before posting so a crash can't double-post.
    dc.set_tags(tid, sorted(tags | {cfg.published_tag}))
    user_id = tok.user_id or "me"
    try:
        publish.publish_thread(
            user_id,
            tok.access_token,
            posts,
            crossreshare_to_ig=cfg.crossreshare_to_ig,
            dark_mode=cfg.crossreshare_dark_mode,
        )
        log(f"topic {tid}: published")
    except Exception as e:
        log(f"topic {tid}: PUBLISH FAILED after tagging {cfg.published_tag} -- "
            f"remove that tag to retry. Error: {e}")


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
