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

    # Determine current season and latest week
    available_seasons = sorted(k for k in league_data if isinstance(k, int))
    current_season = available_seasons[-1] if available_seasons else 2026

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

components.html(html_content, height=1400, scrolling=True)
