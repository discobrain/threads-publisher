"""CLI.

Auth (manual OAuth flow -- do this once, then refresh periodically):

  threads-poster auth-url        print the URL to open in a browser to grant access
  threads-poster auth <code>     exchange the ?code=... from the redirect for a
                                 long-lived token and save it to the token file
  threads-poster refresh         refresh the stored long-lived token (~60d -> +60d)
  threads-poster token           show stored token status (value masked)

Publish (poll Discourse for liked drafts, post them to Threads):

  threads-poster run             poll forever, publish approved drafts
  threads-poster once            a single pass, then exit
  threads-poster show <id>       read-only: show a topic's draft, like, parsed posts
"""

import sys
import time

from . import auth, config, draft, loop, threads, token_store
from .discourse import Discourse


def _cmd_auth_url(cfg: config.Config) -> int:
    print(threads.authorize_url(cfg.app_id, cfg.redirect_uri))
    print(
        "\nOpen this in a browser, approve, then copy the `code` value from the\n"
        "redirect URL (it looks like <redirect_uri>?code=XXXXX#_) and run:\n\n"
        "  threads-poster auth <code>",
        file=sys.stderr,
    )
    return 0


def _cmd_auth(cfg: config.Config, code: str) -> int:
    now = int(time.time())
    tok = auth.fetch_and_store(cfg, auth.code_from_input(code), now)
    days = tok.expires_in(now) // 86400
    print(f"Saved long-lived token to {cfg.token_path} (user {tok.user_id}, expires in ~{days}d)")
    return 0


def _cmd_refresh(cfg: config.Config) -> int:
    tok = token_store.load(cfg.token_path)
    if tok is None:
        print(f"No token at {cfg.token_path}; run `auth` first.", file=sys.stderr)
        return 1
    res = threads.refresh_long_lived(tok.access_token)
    now = int(time.time())
    new = token_store.Token(
        access_token=res["access_token"],
        user_id=tok.user_id,
        expires_at=now + int(res.get("expires_in", 0)),
        obtained_at=now,
    )
    token_store.save(cfg.token_path, new)
    days = new.expires_in(now) // 86400
    print(f"Refreshed; expires in ~{days}d")
    return 0


def _cmd_token(cfg: config.Config) -> int:
    tok = token_store.load(cfg.token_path)
    if tok is None:
        print(f"No token at {cfg.token_path}; run `auth-url` then `auth <code>`.")
        return 1
    now = int(time.time())
    left = tok.expires_in(now)
    masked = tok.access_token[:6] + "..." + tok.access_token[-4:]
    state = "EXPIRED" if left <= 0 else f"~{left // 86400}d left"
    print(f"user={tok.user_id} token={masked} ({state})")
    return 0


def _cmd_show(cfg: config.Config, topic_id: int) -> int:
    dc = Discourse(cfg.discourse_url, cfg.discourse_api_key, cfg.discourse_api_username)
    topic = dc.get_topic(topic_id)
    tags = sorted(topic.get("tags") or [])
    print(f"topic {topic_id}: {topic.get('title')!r}  tags={tags}")
    print(f"draft_tag={cfg.draft_tag} present={cfg.draft_tag in tags}  "
          f"published_tag={cfg.published_tag} present={cfg.published_tag in tags}")
    post = draft.find_draft_post(topic, cfg.draft_label)
    if post is None:
        print(f"no [details=\"{cfg.draft_label}\"] draft comment found")
        return 0
    raw = dc.get_post_raw(post["id"])
    posts = draft.parse_posts(raw)
    total_imgs = sum(len(p.images) for p in posts)
    print(f"draft comment: post_id={post['id']} liked={draft.is_liked(post)} "
          f"parts={len(posts)} image_refs={total_imgs}")
    for i, p in enumerate(posts, 1):
        extra = ("\n  image refs: " + ", ".join(p.images)) if p.images else ""
        print(f"\n--- part {i}/{len(posts)} ({len(p.text)} chars) ---\n{p.text}{extra}")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "help"
    rest = argv[1:]

    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0

    needs_discourse = cmd in ("run", "once", "show")
    cfg = config.load(discourse_required=needs_discourse)

    if cmd == "auth-url":
        return _cmd_auth_url(cfg)
    if cmd == "auth":
        if not rest:
            print("usage: threads-poster auth <code>", file=sys.stderr)
            return 2
        return _cmd_auth(cfg, rest[0])
    if cmd == "refresh":
        return _cmd_refresh(cfg)
    if cmd == "token":
        return _cmd_token(cfg)
    if cmd == "run":
        loop.run(cfg)
        return 0
    if cmd == "once":
        dc = Discourse(cfg.discourse_url, cfg.discourse_api_key, cfg.discourse_api_username)
        loop.run_once(cfg, dc, loop._maybe_refresh(cfg, loop._load_token(cfg)))
        return 0
    if cmd == "show":
        if not rest:
            print("usage: threads-poster show <topic_id>", file=sys.stderr)
            return 2
        return _cmd_show(cfg, int(rest[0]))

    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
