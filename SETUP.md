# Weekly Fantasy Baseball Recap — Setup Guide

## Quick Start (5 steps)

### 1. Install dependencies
```bash
cd weekly_recap
pip install -r requirements.txt
```

### 2. Create your .env file
```bash
cp .env.example .env
```
Then open `.env` and fill in each value (see below).

---

### 3. Get Yahoo credentials

1. Go to https://developer.yahoo.com/apps/ and sign in with your Yahoo account.
2. Click **"Create an App"**.
3. Fill in:
   - **App Name**: anything (e.g. "Fantasy Recap Bot")
   - **Application Type**: Installed Application
   - **Redirect URI(s)**: `oob`
   - **API Permissions**: check **Fantasy Sports → Read**
4. Click **Create App**.
5. Copy the **Client ID** (Consumer Key) → `YAHOO_CLIENT_ID` in `.env`
6. Copy the **Client Secret** (Consumer Secret) → `YAHOO_CLIENT_SECRET` in `.env`

**Finding your league key:**
- Open your Yahoo Fantasy league in a browser.
- The URL looks like: `https://baseball.fantasysports.yahoo.com/b1/123456`
- The number `123456` is your league ID.
- The game key for MLB 2025 is typically `458`. If you're unsure, run:
  ```bash
  python -c "
  from dotenv import load_dotenv; load_dotenv()
  from auth import setup_oauth
  from yahoo_client import _api_get, get_current_game_key
  sc = setup_oauth()
  print('Game key:', get_current_game_key(sc.get_session(), 'mlb'))
  "
  ```
- Set `YAHOO_LEAGUE_KEY=458.l.123456` in `.env`.

---

### 4. Get an Anthropic API key

1. Go to https://console.anthropic.com/
2. Create an account or sign in.
3. Navigate to **API Keys** and create a new key.
4. Set `ANTHROPIC_API_KEY` in `.env`.

---

### 5. Create a Discord webhook

1. Open your Discord server.
2. Go to **Server Settings → Integrations → Webhooks**.
3. Click **New Webhook**.
4. Choose the channel where recaps should post.
5. Click **Copy Webhook URL**.
6. Set `DISCORD_WEBHOOK_URL` in `.env`.

---

## Running the bot

```bash
# Recap last week and post to Discord
python main.py

# Recap a specific week
python main.py --week 12

# Generate recap but don't post (preview mode)
python main.py --dry-run

# Print raw API data for debugging
python main.py --print-data
```

**First run:** Your browser will open for Yahoo authorization.
Yahoo will show you a 7-character code — paste it back into the terminal.
The token is saved to `oauth_token.json` and refreshed automatically on subsequent runs.

---

## Automate it (run every Monday)

### macOS (launchd)
```bash
# Create a plist at ~/Library/LaunchAgents/com.fantasyrecap.plist
# with a StartCalendarInterval for Monday morning
```

### Any OS (cron)
```cron
# Run every Monday at 9 AM
0 9 * * 1 cd /path/to/weekly_recap && python main.py >> recap.log 2>&1
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `YAHOO_CLIENT_ID not set` | Check `.env` exists in the `weekly_recap/` folder |
| Yahoo returns 401 | Delete `oauth_token.json` and re-authorize |
| `league[1]` KeyError | Your `YAHOO_LEAGUE_KEY` format may be wrong — verify it |
| Discord returns 400 | Check the webhook URL is complete and hasn't been deleted |
| Top players missing | This endpoint may require an active season; it's skipped gracefully |

## File structure

```
weekly_recap/
├── auth.py              # Yahoo OAuth 2.0 (handles browser flow + token refresh)
├── yahoo_client.py      # Yahoo Fantasy API data fetching
├── recap_generator.py   # Claude Opus 4.6 recap generation (streaming)
├── discord_poster.py    # Discord webhook posting (handles long recaps)
├── main.py              # CLI entry point
├── requirements.txt
├── .env.example         # Template — copy to .env
├── .env                 # Your secrets (don't commit this)
├── oauth_token.json     # Auto-created on first auth run (don't commit this)
└── SETUP.md             # This file
```
