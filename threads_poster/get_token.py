"""One-shot helper to obtain and store the long-lived Threads token.

Run it with no arguments: it prints the authorization URL, then waits for you to
paste the FULL redirect URL the browser landed on, exchanges it for a long-lived
token, and saves it. The whole flow is a single process, so the app credentials
loaded from the environment are used consistently for both steps.

  get-token            print URL, wait for the pasted redirect URL, store token
  get-token '<url>'    non-interactive: use the given redirect URL (or bare code)

Set THREADS_REDIRECT_URI=https://localhost/ so the browser redirects to a URL
you can simply copy in full -- nothing needs to listen on localhost.
"""

import sys
import time

from . import auth, config, threads


def main() -> int:
    cfg = config.load()
    args = sys.argv[1:]

    if args:
        raw = args[0]
    else:
        print(threads.authorize_url(cfg.app_id, cfg.redirect_uri))
        print(
            f"\nOpen the URL above in a browser and approve. It will redirect to\n"
            f"{cfg.redirect_uri}?code=... -- the page won't load (nothing listens\n"
            "there), that's fine. Copy the WHOLE redirect URL from the address bar.\n",
            file=sys.stderr,
        )
        try:
            raw = input("Paste the full redirect URL here: ").strip()
        except EOFError:
            raw = ""
        if not raw:
            print("No URL entered; aborted.", file=sys.stderr)
            return 1

    code = auth.code_from_input(raw)
    now = int(time.time())
    tok = auth.fetch_and_store(cfg, code, now)
    days = tok.expires_in(now) // 86400
    print(f"Saved long-lived token to {cfg.token_path} (user {tok.user_id}, expires in ~{days}d)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
