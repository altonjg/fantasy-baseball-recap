"""
MillerLite® BeerLeagueBaseball — Weekly Recap Dashboard
Serves the interactive HTML design mockup via Streamlit.
"""

from pathlib import Path
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

html_file = Path(__file__).parent / "design_mockup.html"
html_content = html_file.read_text(encoding="utf-8")

components.html(html_content, height=900, scrolling=True)
