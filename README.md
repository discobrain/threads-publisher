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
   `THREADS_REDIRECT_URI=https://localhost/` in `.env` (with the real
   `THREADS_APP_ID` / `THREADS_APP_SECRET`, not the placeholders).
2. Run the helper — it prints the authorization URL and then waits:

   ```sh
   get-token
   ```

3. Open that URL in a browser and approve. The browser redirects to
   `https://localhost/?code=...` — nothing listens there, so the page won't
   load; that's expected. Copy the **whole** address-bar URL and paste it back
   at the prompt. The token is exchanged and stored in `.threads-token.json`.

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

The publisher polls Discourse and posts approved Threads drafts. A draft is the
`[details="Threads"]` comment postmaker leaves on a topic (tagged
`threads-draft`); you **approve it by liking that comment**. Each pass, for every
liked draft not yet tagged `threads-published`, it posts the fenced posts as a
thread — the root post is also cross-reshared to Instagram Stories — then tags
the topic `threads-published` so it's never posted twice.

Set the Discourse creds in `.env` (`DISCOURSE_URL`, `DISCOURSE_API_KEY`,
`DISCOURSE_API_USERNAME`); tune tags / cross-reshare in `threads_poster.toml`.

```sh
threads-poster show <topic_id>   # read-only: draft, whether it's liked, parsed posts
threads-poster once              # a single pass
threads-poster run               # poll forever (refreshes the token as it nears expiry)
THREADS_DRY_RUN=1 threads-poster once   # parse + print, don't post
```

Requirements: Nix with flakes enabled. Runtime is Python stdlib only; no
external packages. A valid token must exist (`get-token`); posting and token
refresh use the token alone (no app secret).
