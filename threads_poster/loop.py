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

from . import draft, publish, state, threads, token_store
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


def _resolve_images(cfg, dc: Discourse, posts) -> None:
    """Turn each post's raw refs into public URLs Threads can fetch: resolve
    `upload://` short-urls via Discourse, keep full URLs, make relative absolute.
    Unresolvable refs are dropped with a warning."""
    refs = {r for p in posts for r in p.images if r.startswith("upload://")}
    mapping = dc.lookup_upload_urls(sorted(refs)) if refs else {}
    for p in posts:
        urls = []
        for r in p.images:
            u = r if r.startswith("http") else mapping.get(r)
            if not u:
                log(f"image ref unresolved, dropping: {r}")
                continue
            if u.startswith("//"):
                u = "https:" + u
            elif u.startswith("/"):
                u = cfg.discourse_url.rstrip("/") + u
            urls.append(u)
        p.images = urls


def _published_line(cfg, permalink: str) -> str:
    """The 'Threads Published' line inserted inside the draft's details block: an
    internal link to the index page (creates a backlink there) + the post URL."""
    idx = cfg.published_index_url
    if idx:
        if idx.startswith("/"):
            idx = cfg.discourse_url.rstrip("/") + idx
        return f"[:white_check_mark: Threads Published]({idx}): {permalink}"
    return f":white_check_mark: Threads Published: {permalink}"


def _mark_published(cfg, dc: Discourse, token: str, tid: int, post_id: int, raw: str,
                    media_ids: list[str]) -> None:
    """Edit the draft comment in place: flag the details summary with a green
    check (so a collapsed view shows it's published) and insert the published
    line above the post text. Best-effort -- publishing already succeeded."""
    if not cfg.link_back or not media_ids:
        return
    try:
        permalink = threads.get_permalink(media_ids[0], token)
        line = _published_line(cfg, permalink)
        # Literal emoji in the details summary: Discourse does NOT cook :shortcodes:
        # inside a details title, but renders a real emoji char fine.
        opening = f'[details="{cfg.draft_label}"]'
        if opening in raw:
            new_raw = raw.replace(
                opening, f'[details="✅ {cfg.draft_label}"]\n\n{line}', 1
            )
        else:
            new_raw = f"{line}\n\n{raw}"
        dc.update_post(post_id, new_raw)
        log(f"topic {tid}: marked draft comment published")
    except Exception as e:
        log(f"topic {tid}: published, but marking the draft failed: {e}")


def process_topic(cfg, dc: Discourse, tok: token_store.Token, topic: dict) -> None:
    tid = topic["id"]
    tags = set(topic.get("tags") or [])
    if cfg.published_tag in tags:
        return  # already published
    if cfg.draft_tag not in tags:
        return  # draft not ready

    post = draft.find_draft_post(topic, cfg.draft_label)
    if post is None:
        return  # no Threads draft comment on this topic
    if not draft.is_liked(post):
        return  # not approved yet -- waiting for a like

    raw = dc.get_post_raw(post["id"])  # only now that it's approved
    posts = draft.parse_posts(raw)
    if not posts:
        log(f"topic {tid}: draft comment has no fenced posts, skipping")
        return
    _resolve_images(cfg, dc, posts)

    total_imgs = sum(len(p.images) for p in posts)
    log(f"topic {tid}: approved, publishing {len(posts)} post(s), {total_imgs} image(s)")
    if cfg.dry_run:
        for i, p in enumerate(posts, 1):
            extra = ("\n  images: " + ", ".join(p.images)) if p.images else ""
            log(f"[dry-run] topic {tid} post {i}/{len(posts)} ({len(p.text)} chars):\n{p.text}{extra}")
        return

    # Throttle: at most one publish per min_publish_interval, so a burst of likes
    # goes out spaced apart. The draft stays approved+untagged and is picked up on
    # a later pass once the window elapses.
    now = int(time.time())
    since = now - state.last_publish(cfg.state_path)
    if since < cfg.min_publish_interval:
        log(f"topic {tid}: approved but throttled; next publish in ~{(cfg.min_publish_interval - since) // 60}m")
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
            state.record_publish(cfg.state_path, int(time.time()))
            _mark_published(cfg, dc, tok.access_token, tid, post["id"], raw, e.published)
            log(f"topic {tid}: PARTIAL publish ({len(e.published)} live) then failed: {e}. "
                f"Tagged {cfg.published_tag} to avoid re-posting; finish the remainder manually.")
        else:
            log(f"topic {tid}: publish failed, nothing posted -- will retry next pass: {e}")
        return

    # Full success -> tag AFTER posting so a failed publish never marks a topic
    # published (the tiny crash window between last post and tagging is the only
    # residual duplicate risk).
    dc.set_tags(tid, sorted(tags | {cfg.published_tag}))
    state.record_publish(cfg.state_path, int(time.time()))
    _mark_published(cfg, dc, tok.access_token, tid, post["id"], raw, media_ids)
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
    log(f"up. {scope} every {cfg.poll_interval}s, <=1 publish/{cfg.min_publish_interval}s, "
        f"crossreshare_to_ig={cfg.crossreshare_to_ig}, dry_run={cfg.dry_run}")
    while True:
        try:
            tok = _maybe_refresh(cfg, _load_token(cfg))
            run_once(cfg, dc, tok)
        except SystemExit as e:
            log(str(e))  # e.g. no token yet; keep looping so it recovers
        except Exception as e:
            log(f"pass error: {e}")
        time.sleep(cfg.poll_interval)
