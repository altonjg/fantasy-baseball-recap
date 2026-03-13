# BeerLeagueBaseball — Product Requirements Document

**Project:** MillerLite® BeerLeagueBaseball Weekly Recap Dashboard
**Stack:** Python · Streamlit · Yahoo Fantasy API · Anthropic API · GitHub Actions
**Last Updated:** 2026-03-12
**Status:** Active development — design mockup complete, data integration in progress

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

## 5. API Landscape & Integration Roadmap

### 🔴 High Value

#### 5.1 MLB Stats API *(free, official — not yet integrated)*
> `statsapi.mlb.com` — no API key required

| Data Available | Use Case |
|---------------|----------|
| Real MLB player stats (career + season) | Draft hindsight grades, trade analysis |
| Official player headshots | Team cards, player profiles |
| Game-by-game logs | "Player X went 4-for-4 the week you traded him away" |
| Injury / transaction history | Context for add/drop moves |
| Team standings & schedules | Real baseball context in articles |
| Minor league stats | Waiver wire scouting |

**Priority: #1 to integrate.** Free, official, and unlocks player photos + real stats for draft and trade retrospectives.

#### 5.2 Claude / Anthropic API *(already integrated ✅)*
Currently powering weekly recaps. Expansion opportunities:
- Trade Wire articles ("Who won this trade?")
- Draft grade narratives per team
- Power rankings blurbs
- Season award write-ups
- End-of-season retrospectives

---

### 🟡 Medium Value

#### 5.3 Pybaseball — Baseball Reference / FanGraphs *(not yet integrated)*
> Python library wrapping both sites. No official API needed.

| Data Available | Use Case |
|---------------|----------|
| Advanced stats (WAR, wRC+, FIP, xFIP) | Deeper draft/trade analysis |
| Statcast data (exit velocity, spin rate) | Nerdy breakdowns for engaged leagues |
| Historical player comps | "Player X is having an Aaron Judge–type season" |

**Note:** Good for serious analysis features. Can layer on top of MLB Stats API.

#### 5.4 FantasyPros Rankings API *(free tier available)*
> Fantasy-specific rankings and projections

| Data Available | Use Case |
|---------------|----------|
| Weekly player rankings | Waiver wire recommendations |
| Rest-of-season projections | Trade value at time of trade |
| ADP (average draft position) | Draft grade baseline |
| Expert consensus rankings | "Was this a reach?" draft analysis |

**Open question:** Do we use the free public ADP pages (scrapeable) or pursue a paid API key?

#### 5.5 Weather API — OpenWeatherMap *(free tier)*
> Game-day weather at MLB stadiums

| Data Available | Use Case |
|---------------|----------|
| Historical weather on game dates | "Freeman's slugging dipped — 3 cold-weather games in Chicago" |
| Game-day conditions | Retroactive context for pitcher struggles |

**Nice personality add** for AI-generated articles.

---

### 🟢 Nice to Have

#### 5.6 Discord Webhooks *(deferred — already discussed)*
Post weekly recap and trade alerts directly to league Discord channel. Free, simple setup. Gets content in front of league members automatically rather than relying on them visiting the dashboard.

#### 5.7 Slack API
Same concept as Discord. Rich message formatting for weekly recap cards and trade alerts.

#### 5.8 Google Sheets API
Export standings/stats to a shared sheet for league members who prefer spreadsheets. Also useful as a data backup beyond JSON files.

#### 5.9 SendGrid / Mailgun *(email)*
Send HTML recap emails to all 14 managers. Free tiers are generous enough for a 14-person league. Could be used for:
- Weekly recap email
- Trade alert emails ("Breaking: A trade just happened")

---

### Recommended Integration Priority

| Priority | API | Reason |
|----------|-----|--------|
| 1 | **MLB Stats API** | Free, official, unlocks player photos + real stats for draft/trade analysis |
| 2 | **FantasyPros ADP** | Gives draft grading baseline without computing ADP from scratch |
| 3 | **Discord Webhooks** | Gets content in front of league members automatically |
| 4 | **Pybaseball** | Advanced stats layer for engaged audience |
| 5 | **Weather API** | Article personality, low effort |
| 6 | **Email (SendGrid)** | Reach members who don't check the dashboard |

---

## 6. Data Pipeline (Current)

| Source | What it provides | How accessed |
|--------|-----------------|--------------|
| Yahoo Fantasy API | Live standings, scores, rosters, transactions, draft | `yahoo_client.py` via OAuth |
| Anthropic API | AI-generated articles, recaps, trade analysis | `recap_generator.py` |
| GitHub Actions | Scheduled runs — trade detection (4h), weekly recap (Mon 11 AM UTC) | `.github/workflows/update.yml` |

---

## 7. Technical Constraints

- **Frontend:** Pure HTML/CSS/JS in a single `design_mockup.html` file, served via `st.components.v1.html()` in Streamlit
- **Charts:** Pure SVG — no external charting libraries
- **Icons:** Font Awesome 6.5.0 free tier only
- **No emojis** — all accolades/badges use FA icons
- **Team logos:** Yahoo CDN URLs, lazy-replaced on DOMContentLoaded
- **Deployment:** Streamlit Cloud, auto-deploys on push to `main`

---

## 8. Design System

| Token | Value |
|-------|-------|
| Background | `#0a1628` |
| Card | `#111e35` |
| Gold | `#f0c040` |
| Muted | `#8895a7` |
| Border | `rgba(255,255,255,0.08)` |
| Font (body) | Inter |
| Font (display) | Oswald |
