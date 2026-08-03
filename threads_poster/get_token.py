"""One-shot helper to obtain and store the long-lived Threads token.

  get-token                 print the authorization URL to open in a browser
  get-token '<url>'         take the FULL redirect URL the browser landed on
                            (or a bare code), exchange it for a long-lived token,
                            and save it to the token file

Set THREADS_REDIRECT_URI=https://localhost/ so the browser redirects to a URL
you can simply copy in full -- nothing needs to listen on localhost.
"""

import sys
import time

from . import auth, config, threads


def main() -> int:
    cfg = config.load()
    args = sys.argv[1:]

    if not args:
        print(threads.authorize_url(cfg.app_id, cfg.redirect_uri))
        print(
            "\nOpen this URL in a browser and approve. The browser will redirect "
            f"to\n{cfg.redirect_uri}?code=... -- copy that WHOLE redirect URL and run:\n\n"
            "  get-token '<paste the whole redirect URL>'",
            file=sys.stderr,
        )
        return 0

    code = auth.code_from_input(args[0])
    tok = auth.fetch_and_store(cfg, code, int(time.time()))
    days = tok.expires_in(int(time.time())) // 86400
    print(f"Saved long-lived token to {cfg.token_path} (user {tok.user_id}, expires in ~{days}d)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
