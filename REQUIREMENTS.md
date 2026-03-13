# BeerLeagueBaseball — Product Requirements Document

**Project:** MillerLite® BeerLeagueBaseball Weekly Recap Dashboard
**Stack:** Python · Streamlit · Yahoo Fantasy API · Anthropic API · GitHub Actions
**Last Updated:** 2026-03-12

---

## 1. Overview

A fully interactive weekly recap dashboard for a 14-team fantasy baseball league. The app auto-generates editorial content, visualizations, and stats from live Yahoo Fantasy data, presented in a polished sports-media aesthetic (Miller Lite navy/gold palette).

---

## 2. Current Implementation

### 2.1 Navigation
- [x] Persistent top tab bar: **Home · This Week · Season · News · All Time**
- [x] Sidebar: sticky, scrollable — Season/Week selectors, Standings, Streak Watch
- [x] All Time page: separate view with its own sidebar (Champions, Win Leaders)

### 2.2 Home Tab
- [x] **Score Ticker** — horizontal scrollable row of all weekly matchup results
- [x] **Leaders Bar** — Best Record, Most PF, Fewest PA, Power #1, League Leader, Luckiest Team
- [x] **Featured Article Card** — headline, byline, preview text, "Read Full Recap" CTA
- [x] **Standings** — American League / National League split
- [x] **Power Rankings** — with movement arrows and form indicators

### 2.3 This Week Tab
- [x] **Recap** inner tab — full AI-generated article with sidebar quick stats & awards
- [x] **Matchups** inner tab — score cards with category wins, manager names, accolade chips
- [x] **Transactions** inner tab — trade and waiver wire activity

### 2.4 Season Tab
- [x] **Standings** inner tab — full 14-team table with PCT bars and division breakdown
- [x] **Savant** inner tab:
  - Baseball Savant–style heat map (win rates by category, filterable/sortable)
  - Actual vs Expected record (luck index)
  - Radar chart (5-team overlay, toggleable)
- [x] **Pennant Race** inner tab — bump chart showing weekly rank movement, team toggles
- [x] **Momentum** inner tab — rolling momentum bars (Season / L8 / L4 windows, sortable)
- [x] **Playoff Probability** inner tab — line chart with playoff/bubble/missed filters
- [x] **Streaks** inner tab — win/loss streak table with form pills

### 2.5 All Time Tab
- [x] **History** inner tab — season-by-season toggle (All Time / 2025 / 2024 / 2023) with playoff finish badges
- [x] **Head-to-Head** inner tab — H2H win matrix with spotlight and filter controls
- [x] **Trophy Case** inner tab — championship history
- [x] **Awards Archive** inner tab — historical weekly/season awards

### 2.6 News Tab
- [x] Full AI-generated weekly recap article
- [x] Trade articles and transaction commentary

### 2.7 Sidebar Enhancements
- [x] Streak Watch — Hot/Cold teams with streak counts
- [x] Scrollable, sticky sidebar

### 2.8 Accolades & Badges
- [x] Accolade chips on matchup cards (HR King, Hot Hand, K Machine, etc.)
- [x] Form pills (W/L dot indicators)
- [x] Playoff finish badges (Champion, Runner-Up, 3rd Place, Semifinal, Quarterfinal)

---

## 3. Planned Features

### 3.1 ALCS / NLCS Playoff Branding *(discussed, not yet implemented)*
Map playoff rounds to MLB-style naming conventions, consistent with the existing AL/NL division structure:

| Round | Label |
|-------|-------|
| Wild Card / Play-in | Wild Card Series |
| Quarterfinals | ALDS / NLDS |
| Semifinals | ALCS / NLCS |
| Championship | World Series |

- Apply labels to: score ticker cards, matchup cards, pennant race chart, accolade chips, All Time history badges
- Add a **Playoff Bracket** visual (bracket tree showing each round's results)

### 3.2 Draft Analysis Tab *(discussed, not yet implemented)*
New tab under **Season** or standalone **Draft** tab.

**Data sources:**
- Yahoo Fantasy API — actual draft picks, round, position, team
- FantasyPros ADP — consensus average draft position (public pages or v2 API if key available)

**Features:**
- **ADP vs Actual** scatter chart — steal/bust quadrants by pick slot
- **Draft Grade Cards** — per-team letter grade with AI-generated blurb
- **Best/Worst Picks** — "Steal of the Draft" and "Biggest Bust" accolades
- **Positional Value** — which teams won each position group at the draft
- **Round-by-Round Heat Map** — value added by round and pick slot

**Open questions:**
- Do we have a FantasyPros API key, or use public ADP pages?
- Is 2025 draft data available through Yahoo API, or was the league on a different platform?

---

## 4. Items to Discuss

> *Use this section to capture new feature ideas, open questions, and design decisions before implementation.*

### 4.1 *(Open)* — Additional features TBD
*Awaiting discussion with stakeholder.*

---

## 5. Data Pipeline

| Source | What it provides | How accessed |
|--------|-----------------|--------------|
| Yahoo Fantasy API | Live standings, scores, rosters, transactions, draft | `yahoo_client.py` via OAuth |
| FantasyPros | ADP, expert rankings, projections | Public pages (scrape) or v2 API key |
| Anthropic API | AI-generated articles, recaps, trade analysis | `recap_generator.py` |
| GitHub Actions | Scheduled runs — trade detection (4h), weekly recap (Mon 11 AM UTC) | `.github/workflows/update.yml` |

---

## 6. Technical Constraints

- **Frontend:** Pure HTML/CSS/JS in a single `design_mockup.html` file, served via `st.components.v1.html()` in Streamlit
- **Charts:** Pure SVG — no external charting libraries
- **Icons:** Font Awesome 6.5.0 free tier only
- **No emojis** — all accolades/badges use FA icons
- **Team logos:** Yahoo CDN URLs, lazy-replaced on DOMContentLoaded
- **Deployment:** Streamlit Cloud, auto-deploys on push to `main`

---

## 7. Design System

| Token | Value |
|-------|-------|
| Background | `#0a1628` |
| Card | `#111e35` |
| Gold | `#f0c040` |
| Muted | `#8895a7` |
| Border | `rgba(255,255,255,0.08)` |
| Font (body) | Inter |
| Font (display) | Oswald |
