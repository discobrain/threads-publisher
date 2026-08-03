# threads-poster

Publishes approved Discourse drafts to **Threads**. It's the *publisher*
counterpart to `postmaker` (the drafter): once a draft is approved, this tool
posts it, optionally cross-resharing the thread to the linked Instagram account
as a Story.

Discourse is the source of truth; nothing is stored locally except the access
token.

## Configure

- **Secrets** → environment (`.env`): the Threads app credentials and the
  Discourse API creds. See `.env.example`.
- **Structure** → `threads_poster.toml`: post character limit, poll cadence,
  where the token is stored.

## Dev shell

The repo ships a Nix flake and a `.envrc`. With direnv, `cd`-ing in loads the
dev shell and your `.env` automatically:

```sh
cp .env.example .env    # fill in the Threads app credentials (plain KEY=value)
direnv allow            # loads the flake dev shell + .env (see .envrc)
```

No direnv? Use the flake directly:

```sh
nix develop                       # dev shell with the tools on PATH
set -a; source .env; set +a       # load secrets into the shell
```

## Get an access token

The Threads app id/secret are needed **only** to issue the token. Refreshing it
and posting afterwards use the token alone.

1. In the Meta App, register `https://localhost/` as a redirect URI, and set
   `THREADS_REDIRECT_URI=https://localhost/` in `.env`.
2. Print the authorization URL:

   ```sh
   get-token
   ```

3. Open that URL in a browser and approve. The browser redirects to
   `https://localhost/?code=...` — nothing listens there, so the page won't
   load; that's expected. Copy the **whole** address-bar URL.
4. Exchange it for a long-lived token (stored in `.threads-token.json`):

   ```sh
   get-token 'https://localhost/?code=PASTE_THE_WHOLE_URL'
   ```

The token lasts ~60 days. Refresh it before it expires, and inspect it anytime:

```sh
threads-poster refresh   # extend the long-lived token by another ~60 days
threads-poster token     # show status (value masked)
```

Or run the flake app without entering the shell:

```sh
nix run .#get-token
nix run . -- token
```

## Run

Publishing (poll Discourse for approved drafts, post to Threads, optional
Instagram cross-reshare) — coming next.

Requirements: Nix with flakes enabled. Runtime is Python stdlib only; no
external packages.
