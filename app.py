"""
MillerLite® BeerLeagueBaseball — Weekly Recap Dashboard
Loads all local JSON data and injects it into the interactive HTML dashboard.
"""

from pathlib import Path
import json
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="BeerLeagueBaseball Recap",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Strip all Streamlit chrome so the HTML fills the viewport cleanly
st.markdown("""
<style>
  #MainMenu, header, footer { display: none !important; }
  section[data-testid="stSidebar"] { display: none !important; }
  .block-container { padding: 0 !important; max-width: 100% !important; }
  [data-testid="stAppViewContainer"] { padding: 0 !important; }
  /* Remove the 16px flex gap that pushes the dashboard iframe down */
  .stVerticalBlock { gap: 0 !important; row-gap: 0 !important; }
  /* Kill the Streamlit top decoration bar */
  [data-testid="stDecoration"] { display: none !important; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def load_league_data() -> tuple[dict, int, int]:
    """
    Load all available season/week JSON data into a single dict.
    Returns (league_data, current_season, current_week).

    league_data shape:
      {
        2025: {
          1: { ...week_01.json... },
          ...
          24: { ...week_24.json... },
          "articles": { "week_24_recap": {...}, ... },
          "draft": { ...draft_order.json... }
        },
        2026: { ... }
      }
    """
    data_dir = Path(__file__).parent / "data"
    league_data: dict = {}

    for year_dir in sorted(data_dir.iterdir()):
        if not (year_dir.is_dir() and year_dir.name.isdigit()):
            continue
        season = int(year_dir.name)
        league_data[season] = {}

        # Weekly data files
        for wf in sorted(year_dir.glob("week_*.json")):
            try:
                week_num = int(wf.stem.split("_")[1])
                league_data[season][week_num] = json.loads(wf.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Articles
        articles_dir = year_dir / "articles"
        if articles_dir.exists():
            league_data[season]["articles"] = {}
            for af in sorted(articles_dir.glob("*.json")):
                try:
                    league_data[season]["articles"][af.stem] = json.loads(af.read_text(encoding="utf-8"))
                except Exception:
                    pass

        # Draft order
        draft_file = year_dir / "draft_order.json"
        if draft_file.exists():
            try:
                league_data[season]["draft"] = json.loads(draft_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Draft results (actual picks, populated by backfill.py --draft after the draft)
        draft_results_file = year_dir / "draft_results.json"
        if draft_results_file.exists():
            try:
                league_data[season]["draft_results"] = json.loads(draft_results_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # ADP snapshot (populated by backfill.py --adp)
        adp_file = year_dir / "adp_snapshot.json"
        if adp_file.exists():
            try:
                league_data[season]["adp"] = json.loads(adp_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Advanced stats — Fangraphs WAR/wRC+/FIP (populated by backfill.py --stats)
        stats_file = year_dir / "advanced_stats.json"
        if stats_file.exists():
            try:
                league_data[season]["advanced_stats"] = json.loads(stats_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Division names (populated by backfill.py --divisions)
        divisions_file = year_dir / "divisions.json"
        if divisions_file.exists():
            try:
                div_data = json.loads(divisions_file.read_text(encoding="utf-8"))
                team_divisions = div_data.get("team_divisions", {})
                # Patch division_name into every week's standings for this season
                for week_key, week_val in league_data[season].items():
                    if not isinstance(week_key, int) or not isinstance(week_val, dict):
                        continue
                    for team in week_val.get("standings", []):
                        if team.get("team_key") in team_divisions:
                            team["division_name"] = team_divisions[team["team_key"]]
                league_data[season]["divisions"] = div_data.get("divisions", {})
            except Exception:
                pass

    # Global MLB player headshot cache (populated by backfill.py --headshots)
    mlb_players_file = data_dir / "mlb_players.json"
    if mlb_players_file.exists():
        try:
            league_data["mlb_players"] = json.loads(mlb_players_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Team logos map (name → url, populated by fetch_logos.py)
    team_logos_file = data_dir / "team_logos.json"
    if team_logos_file.exists():
        try:
            league_data["team_logos"] = json.loads(team_logos_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # League logo (populated by fetch_league_logo.py)
    league_logo_file = data_dir / "league_logo.json"
    if league_logo_file.exists():
        try:
            league_data["league_logo"] = json.loads(league_logo_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Determine current season — find the latest season that has at least one
    # regular season week (not is_playoffs) with actual points scored.
    # This handles: (a) Yahoo returning all-zero standings, (b) pre-season
    # folders with only playoff/junk data, (c) seasons not yet started.
    available_seasons = sorted(k for k in league_data if isinstance(k, int))

    current_season = available_seasons[-1] if available_seasons else 2025
    for season in reversed(available_seasons):
        weeks = sorted(k for k in league_data.get(season, {}) if isinstance(k, int))
        found = False
        for wk in reversed(weeks):
            matchups = league_data[season][wk].get("matchups", [])
            regular = [m for m in matchups
                       if not m.get("is_playoffs") and not m.get("is_consolation")]
            if regular and any(
                t.get("points", 0) > 0
                for m in regular for t in m.get("teams", [])
            ):
                found = True
                break
        if found:
            current_season = season
            break

    season_weeks = sorted(
        k for k in league_data.get(current_season, {}) if isinstance(k, int)
    )
    current_week = season_weeks[-1] if season_weeks else 1

    return league_data, current_season, current_week


league_data, current_season, current_week = load_league_data()

# Build the data injection script — inlined before </head>
data_script = f"""<script>
window.LEAGUE_DATA   = {json.dumps(league_data)};
window.CURRENT_SEASON = {current_season};
window.CURRENT_WEEK   = {current_week};
</script>"""

html_file = Path(__file__).parent / "dashboard.html"
html_content = html_file.read_text(encoding="utf-8")
html_content = html_content.replace("</head>", data_script + "\n</head>", 1)

components.html(html_content, height=820, scrolling=False)
