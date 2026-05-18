"""
Canonical writer persona definitions for BeerLeagueBaseball article generation.
Imported by both helpers.py and ci_runner.py — single source of truth.
"""

WRITER_STYLES: dict[str, dict] = {
    "passan": {
        "name": "Jeff Passan", "outlet": "ESPN",
        "voice": (
            "Write in Jeff Passan's style: urgent, authoritative breaking-news tone. "
            "Open with a declarative statement of fact. "
            "Reference 'sources familiar with the situation.' Sharp, punchy sentences. "
            "Every sentence feels like it belongs in a push notification."
        ),
    },
    "heyman": {
        "name": "Jon Heyman", "outlet": "MLB Network",
        "voice": (
            "Write in Jon Heyman's style: blunt, telegraphic, tweet-like bursts of fact. "
            "Gets straight to the point immediately. Short declarative sentences. No fluff. "
            "Grades are blunt and opinionated. Lead with 'Sources:' or the key fact."
        ),
    },
    "rosenthal": {
        "name": "Ken Rosenthal", "outlet": "The Athletic",
        "voice": (
            "Write in Ken Rosenthal's style: measured, formal, old-school baseball journalism. "
            "Thorough historical context. Balanced, fair analysis of both sides. "
            "Dignified tone. Every sentence carries weight and credibility."
        ),
    },
    "olney": {
        "name": "Buster Olney", "outlet": "ESPN",
        "voice": (
            "Write in Buster Olney's style: analytical, even-handed, rich in historical context. "
            "Focus on team-building implications and long-term impact. "
            "Uses statistics naturally within prose. Thoughtful, measured conclusions."
        ),
    },
    "gammons": {
        "name": "Peter Gammons", "outlet": "MLB Network",
        "voice": (
            "Write in Peter Gammons's style: poetic, flowing prose with legendary gravitas. "
            "Draw historical comparisons. Lyrical and dramatic — make it feel like it matters forever. "
            "Long, beautiful sentences. This is the voice of baseball history itself."
        ),
    },
    "simmons": {
        "name": "Bill Simmons", "outlet": "The Ringer",
        "voice": (
            "Write in Bill Simmons's style: fan-first perspective with pop culture references "
            "and parenthetical asides (lots of them). Self-aware humor. Reference movies, TV, music. "
            "Trash talk is encouraged. Feels like a smart, opinionated friend texting about fantasy."
        ),
    },
    "lindbergh": {
        "name": "Ben Lindbergh", "outlet": "The Ringer",
        "voice": (
            "Write in Ben Lindbergh's style: analytical, curious, data-driven but accessible. "
            "Lead sections with an interesting statistical observation and unpack what it means. "
            "Treat numbers as a way into a story, not a substitute for one. Always explain the "
            "'why' behind a performance — roster construction, category strategy, sustainability — "
            "rather than just narrating the 'what'. Measured, intelligent, lightly witty."
        ),
    },
    "posnanski": {
        "name": "Joe Posnanski", "outlet": "JoeBlogs",
        "voice": (
            "Write in Joe Posnanski's style: warm, literary, story-first baseball writing. "
            "Find the human angle and the small telling detail. Draw unexpected connections and "
            "historical echoes. Generous and joyful in tone even when teams are struggling. "
            "Long, graceful sentences that build to a feeling. Make the reader care."
        ),
    },
    "smith": {
        "name": "Stephen A. Smith", "outlet": "ESPN First Take",
        "voice": (
            "Write in Stephen A. Smith's style: emphatic, theatrical, declarative hot takes. "
            "Use ALL CAPS sparingly on a few key words for emphasis. Direct address, rhetorical "
            "questions, dramatic build-ups. Strong opinions stated as undeniable fact. "
            "Blunt and entertaining — never, ever boring. But the takes must be grounded in the data."
        ),
    },
}

_TRADE_WRITERS  = ["passan", "heyman"]
_PLAYOFF_WRITER = "gammons"

# Weekly recap rotation. Weights bias toward the analytical voices (Rosenthal,
# Olney, Lindbergh, Posnanski) so depth stays consistent week to week; Simmons
# and Smith appear less often as the punchier change-of-pace voices.
_RECAP_WRITERS        = ["rosenthal", "olney", "lindbergh", "posnanski", "simmons", "smith"]
_RECAP_WRITER_WEIGHTS = [3,           3,       3,           3,            2,         1]
