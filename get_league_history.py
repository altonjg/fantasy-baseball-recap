"""
Fetch all Yahoo Fantasy Baseball leagues you've ever been in.
Run:  python get_league_history.py
"""

from auth import YahooOAuth
import credentials
import requests

BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"

def get_all_leagues():
    client_id     = credentials.get_secret("YAHOO_CLIENT_ID")
    client_secret = credentials.get_secret("YAHOO_CLIENT_SECRET")
    oauth = YahooOAuth(client_id, client_secret)
    session = oauth.get_session()

    # Fetch all baseball games (seasons) the user has participated in
    url = f"{BASE_URL}/users;use_login=1/games;game_codes=mlb/leagues"
    resp = session.get(url, params={"format": "json"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()["fantasy_content"]

    users = data.get("users", {})
    user = users.get("0", {}).get("user", [{}])[1]
    games = user.get("games", {})

    print(f"\n{'Season':<10} {'League Name':<40} {'League Key':<20}")
    print("-" * 72)

    for i in range(games.get("count", 0)):
        game_data = games.get(str(i), {}).get("game", [{}])
        game_info = game_data[0] if isinstance(game_data[0], dict) else {}
        season = game_info.get("season", "?")

        if len(game_data) < 2:
            continue
        second = game_data[1]
        # second can be a dict with "leagues" key, or directly a list
        if isinstance(second, dict):
            leagues = second.get("leagues", {})
        else:
            continue

        if isinstance(leagues, list):
            league_list = leagues
        else:
            league_list = [leagues.get(str(j), {}) for j in range(leagues.get("count", 0))]

        for item in league_list:
            league = item.get("league", [{}])
            info = league[0] if isinstance(league, list) else league
            name = info.get("name", "Unknown")
            key  = info.get("league_key", "?")
            print(f"{season:<10} {name:<40} {key:<20}")

if __name__ == "__main__":
    get_all_leagues()
