# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

MillerLite® BeerLeagueBaseball — an auto-generated weekly recap dashboard for a 14-team Yahoo
Fantasy Baseball league. Python/Streamlit backend + a single-file vanilla JS/HTML frontend,
Yahoo Fantasy API v2 for league data, and the Anthropic API for AI-written articles.

The git repo root is this `weekly_recap/` directory, not the parent Obsidian vault folder.

For product scope/roadmap see `REQUIREMENTS.md`. For a point-in-time bug/tech-debt audit see
`REVIEW.md` (dated — verify findings against current code before trusting line numbers).

## Credentials

Never store secrets in this directory in plaintext — it lives inside iCloud Drive and syncs to
Apple's servers. Two credential paths exist:

- **Local dev**: macOS Keychain, service name `fantasy_recap` (see `credentials.py`,
  `setup_keys.py`). `credentials.get_secret()` checks Keychain first, then falls back to
  `os.environ`. The Yahoo OAuth token is also stored in Keychain as JSON, not on disk.
- **CI (GitHub Actions)**: environment variables from repo secrets — `YAHOO_CLIENT_ID`,
  `YAHOO_CLIENT_SECRET`, `YAHOO_REFRESH_TOKEN`, `YAHOO_LEAGUE_KEY`, `ANTHROPIC_API_KEY`,
  `DISCORD_WEBHOOK_URL`. Handled by `ci_auth.py` (no browser, no Keychain).

Running Yahoo-authenticated scripts locally requires pulling secrets out of Keychain into env
vars first:

```bash
YAHOO_CLIENT_ID=$(security find-generic-password -s "fantasy_recap" -a "YAHOO_CLIENT_ID" -w) \
YAHOO_CLIENT_SECRET=$(security find-generic-password -s "fantasy_recap" -a "YAHOO_CLIENT_SECRET" -w) \
YAHOO_REFRESH_TOKEN=$(python3 -c "from credentials import get_oauth_token; print(get_oauth_token()['refresh_token'])") \
ANTHROPIC_API_KEY=$(security find-generic-password -s "fantasy_recap" -a "ANTHROPIC_API_KEY" -w) \
python3 ci_runner.py --mode <MODE> --season <YEAR>
```

## Commands

```bash
# Run the dashboard locally
streamlit run app.py

# CI pipeline runner — same script GitHub Actions invokes
python3 ci_runner.py --mode full            # trades + recap
python3 ci_runner.py --mode trades          # trade detection only
python3 ci_runner.py --mode recap --week N  # weekly recap article (omit --week for latest)
python3 ci_runner.py --mode preview --season YYYY
python3 ci_runner.py --mode draft --season YYYY
python3 ci_runner.py --mode draft_recap --season YYYY
# add --force to regenerate an article that already exists, --dry-run to skip writes

# One-off data backfill (historical seasons)
python3 backfill.py --year 2024 --weeks 1-24
python3 backfill.py --year 2024 --draft        # draft results only
python3 backfill.py --year 2024 --adp          # ADP snapshot
python3 backfill.py --year 2024 --divisions    # division names
python3 backfill.py --year 2024 --headshots    # MLB headshot cache
python3 backfill.py --year 2024 --stats        # advanced stats (Fangraphs)

# Auxiliary/maintenance scripts (run manually, not part of CI)
python3 fetch_logos.py           # team logos -> data/team_logos.json
python3 fetch_league_logo.py     # league logo -> data/league_logo.json
python3 get_league_history.py    # list all Yahoo leagues on this account
python3 setup_keys.py            # one-time: store secrets in macOS Keychain
python3 get_refresh_token.py     # print stored refresh token (to seed GH Actions secret)
python3 bootstrap.py --season YYYY  # one-time: seed season_history.json / records.json

# There is no test suite in this repo.
```

There are two Python dependency files: `requirements.txt` (Streamlit Cloud app only —
kept minimal for fast deploys) and `requirements-ci.txt` (everything, used by GitHub Actions
and local backfill/ci_runner work).

## Architecture

**Two independent pipelines feed the same `data/` JSON files:**

1. **CI pipeline (production)** — `ci_runner.py`, driven by `.github/workflows/update.yml` and
   `draft_day.yml`. Auth via `ci_auth.py`. Modes: `trades` (every 4h during season), `recap`
   (Monday 11:00 UTC), `preview`, `draft`, `draft_recap`, `backfill`. Each mode writes JSON
   into `data/{season}/` and the workflow commits+pushes it back to `main`
   (`git pull --rebase -X ours` then push, using the `GITHUB_TOKEN`).
2. **Legacy local pipeline** — `main.py` (posts to Discord via `discord_poster.py`), using
   `auth.py`'s browser-based OAuth. Not invoked by CI or the dashboard. Discord integration is
   intentionally out of scope going forward — don't propose extending it.

**Article generation (`ci_runner.py`) is a two-pass Claude call:**
- Pass 1: Claude produces a planning JSON (waiver highlights, power rankings, notable
  storylines, records) from raw week data.
- Pass 2: Claude writes the full article using the Pass 1 plan plus a pre-computed
  `league_leaders_text` block (real per-category leaders computed in Python) injected as
  ground truth — this exists specifically to stop the model from hallucinating stat claims.
- Output is parsed from XML tags (`<headline>`, `<body>`, etc.), not JSON, for reliability.
- When `--week N` is passed and `data/{season}/week_0N.json` already exists, that stored file
  is used instead of re-fetching from Yahoo — Yahoo's transactions endpoint only returns the
  ~30 most recent transactions league-wide, so re-fetching an old week loses its transaction
  history permanently.

**Dashboard rendering (`app.py` + `dashboard.html`):**
- `app.py` is a thin Streamlit shell: `load_league_data()` walks `data/{year}/` and assembles
  one big `league_data` dict (weeks, articles, draft results, ADP, advanced stats, divisions,
  MLB headshot cache, logos), then inlines it as `window.LEAGUE_DATA` (plus
  `CURRENT_SEASON`/`CURRENT_WEEK`) into `dashboard.html` and renders it via
  `components.html(..., height=3000, scrolling=False)`.
- `dashboard.html` is a single ~7,500-line file containing all CSS/HTML/JS for the entire UI
  (tabs, charts, heatmaps, article modals) — there is no build step or module system. A JS
  `ResizeObserver` posts `streamlit:setFrameHeight` to adjust the iframe height at runtime.
  Any dashboard UI change means editing this one file directly.
  Current design system: near-black `--bg:#09090f`, cream `--text:#f0ead6`, gold `--gold:#e2b44a`,
  Playfair Display for headlines, Barlow Condensed for nav/labels.
- `app_legacy.py` is a superseded Streamlit implementation kept for reference; the live app is
  `app.py`.
- `pages/1_All_Time.py` is the one real Streamlit multi-page route (All-Time history), separate
  from `dashboard.html` and using its own charts via `helpers.py`.
- `helpers.py` holds shared computation (standings, streaks, power rankings, luck ratings,
  season/weekly awards) used mainly by `pages/1_All_Time.py`. It also has a duplicate,
  currently-unused `WRITER_STYLES` dict and article-generation functions that target an old
  Claude model — treat those as dead code, not a second source of truth for the active pipeline
  in `ci_runner.py`.

**Data layout** — one directory per season under `data/`:
```
data/{year}/week_{NN}.json         # matchups, standings, category stats, transactions
data/{year}/articles/*.json        # generated recap/preview/trade/draft_recap articles
data/{year}/draft_order.json       # pre-draft order
data/{year}/draft_results.json     # actual picks (backfill.py --draft)
data/{year}/adp_snapshot.json      # ADP data (backfill.py --adp)
data/{year}/advanced_stats.json    # Fangraphs WAR/wRC+/FIP (backfill.py --stats)
data/{year}/divisions.json         # team -> division map (backfill.py --divisions)
data/{year}/season_history.json, records.json   # seeded once by bootstrap.py
data/mlb_players.json              # global MLB player ID/headshot cache
data/team_logos.json, league_logo.json
```

**Player data (`mlb_stats.py`)** — resolves Yahoo player names to MLB Stats API
(`statsapi.mlb.com`, no key required) player IDs and headshot URLs, with a local disk cache
(`.mlb_cache/`) to avoid repeated lookups.

**Deployment**: Streamlit Community Cloud, auto-deploys on push to `main`. The dashboard app
only needs `requirements.txt`; the CI/backfill scripts need `requirements-ci.txt`.
