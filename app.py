from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import requests

import streamlit as st

from auth import require_login
from league_logic import (
    TIME_BUCKETS,
    apply_match_result,
    apply_substitutions,
    build_two_week_email,
    compute_records,
    validate_teams,
)
from store import get_store
from season import (
    COURTS,
    GAME_SLOTS,
    games_per_player,
    regenerate,
    team_meeting_counts,
    weekly_standings,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

NO_SUB = "(no sub)"
OUTSIDE_SUB = "Someone outside the league"


def normalize_players(raw: list) -> list[dict]:
    players = []
    for entry in raw:
        if isinstance(entry, str) and entry:
            players.append({"name": entry, "rating": 1500.0})
        elif isinstance(entry, dict) and entry.get("name"):
            players.append({"name": entry["name"], "rating": float(entry.get("rating", 1500))})
    return players


def ratings_of(players: list[dict]) -> dict[str, float]:
    return {p["name"]: float(p["rating"]) for p in players}


st.set_page_config(page_title="Squash House League Manager", layout="wide")
require_login()

store = get_store(DATA_DIR)
try:
    data = store.get_all()
except requests.RequestException as error:
    st.error(f"Couldn't reach the league database ({type(error).__name__}). Check the connection and refresh.")
    st.stop()
players = normalize_players(data["players"])
results: list[dict] = data["results"]
teams: dict[str, list[str]] = data["teams"]
season: list[dict] = data["season"]
contacts: list[dict] = data["contacts"]

st.title("Squash House League Manager")
st.sidebar.caption(f"Data: {store.description}")
if not teams or not season:
    st.error(
        "No teams or season found. From the project folder run: "
        'python3 import_contacts.py "<league spreadsheet.xlsx>", python3 generate_season.py, '
        'and (for the shared site) python3 push_data.py'
    )
    st.stop()

regular_weeks = sum(1 for w in season if w["kind"] == "regular")
today = date.today()
this_week = next((w for w in season if date.fromisoformat(w["date"]) >= today), season[-1])
team_of = {p: t for t, members in teams.items() for p in members}


def week_label(week: dict) -> str:
    day = date.fromisoformat(week["date"]).strftime("%a %b %-d")
    if week["kind"] != "regular":
        return f"{day} - playoffs"
    return f"{day} - " + ", ".join(f"{x} v {y}" for x, y in week["matchups"])


def regenerate_after(day: date) -> None:
    """Rebuild every week after ``day`` from the current ratings and history."""
    global season
    season = regenerate(season, teams, day + timedelta(days=1), regular_weeks, ratings_of(players))
    store.put("season", season)


with st.sidebar:
    st.header("League admin")
    st.caption("Upcoming weeks are rebuilt from ratings and history whenever a result is entered.")
    if st.button("Regenerate upcoming weeks", help="Keeps this week and earlier as they are."):
        regenerate_after(date.fromisoformat(this_week["date"]))
        st.success("Upcoming weeks rebuilt.")

    st.divider()
    st.subheader("Add player to a team")
    new_name = st.text_input("Name")
    new_team = st.selectbox("Team", list(teams))
    if st.button("Add player") and new_name.strip():
        cleaned = new_name.strip()
        if any(p["name"] == cleaned for p in players):
            st.warning("That player is already on the roster.")
        else:
            players.append({"name": cleaned, "rating": 1500.0})
            teams[new_team].append(cleaned)
            store.put("players", players)
            store.put("teams", teams)
            regenerate_after(date.fromisoformat(this_week["date"]))
            st.success(f"Added {cleaned} to Team {new_team}; upcoming weeks rebuilt.")

    st.divider()
    with st.expander("Danger zone"):
        confirm = st.checkbox("I understand this can't be undone")
        if st.button("Reset all ratings to 1500", disabled=not confirm):
            for p in players:
                p["rating"] = 1500.0
            store.put("players", players)
            st.success("Ratings reset.")

weeks_by_date = {w["date"]: w for w in season}
selected_date = st.selectbox(
    "Week",
    [w["date"] for w in season],
    index=[w["date"] for w in season].index(this_week["date"]),
    format_func=lambda d: week_label(weeks_by_date[d]) + ("  (this week)" if d == this_week["date"] else ""),
)
week = weeks_by_date[selected_date]
games = week["games"]
standings = weekly_standings(results, teams, season)
current_rows = standings[-1]["rows"] if standings else None

c1, c2, c3, c4 = st.columns(4)
c1.metric("Games this week", len(games))
c2.metric("Sitting out", len(week["byes"]))
c3.metric("Results recorded", len(results))
c4.metric("League leader", current_rows[0]["Team"] if current_rows and current_rows[0]["Match pts"] else "-")

tab_week, tab_season, tab_players, tab_score, tab_messages, tab_contacts = st.tabs(
    ["Week", "Season", "Players", "Enter score", "Messages", "Contacts"]
)

with tab_week:
    if week["kind"] != "regular":
        st.info("Playoff week - matchups are set from the standings once the regular season ends.")
    else:
        if week.get("locked"):
            st.caption("This week's games were already sent to players, so they're locked.")
        by_key = {(g["time_slot"], g["court"]): g for g in games}
        for slot in GAME_SLOTS:
            st.markdown(f"**{slot}** &nbsp; `{TIME_BUCKETS[slot]}`")
            for col, court in zip(st.columns(len(COURTS)), COURTS):
                game = by_key.get((slot, court))
                with col.container(border=True):
                    if not game:
                        st.caption(court)
                        st.write("-")
                    else:
                        st.caption(f"{court} - {' v '.join(game['teams'])}")
                        st.write(" & ".join(game["team_a"]))
                        st.caption("vs")
                        st.write(" & ".join(game["team_b"]))
        if week["byes"]:
            st.info(f"Sitting out this week: {', '.join(week['byes'])}")

with tab_season:
    st.subheader("Team standings")
    st.caption(
        "Match win = 2 pts, draw = 1. A match counts once all its games have results. "
        "Ties break on games won, then point difference. Games with an outside sub don't score."
    )
    if standings:
        after = st.selectbox(
            "Standings after",
            [s["date"] for s in standings],
            index=len(standings) - 1,
            format_func=lambda d: week_label(weeks_by_date[d]),
        )
        snapshot = next(s for s in standings if s["date"] == after)
        columns = ("Position", "Team", "Matches", "W", "D", "L", "Match pts", "Games won", "Games lost", "Pts +/-")
        st.dataframe([{k: r[k] for k in columns} for r in snapshot["rows"]], hide_index=True, width="stretch")

        points = {team: {} for team in teams}
        position = {team: {} for team in teams}
        for snap in standings:
            for r in snap["rows"]:
                points[r["Team"]][snap["date"]] = r["Match pts"]
                position[r["Team"]][snap["date"]] = r["Position"]
        st.markdown("**Match points by week**")
        st.line_chart(points)
        st.markdown("**Position by week**")
        st.dataframe(
            [
                {"Team": team, **{date.fromisoformat(d).strftime("%b %-d"): pos for d, pos in position[team].items()}}
                for team in teams
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("No results yet. Standings appear here after the first scores are entered.")

    st.subheader("Calendar")
    calendar = []
    for w in season:
        if w["kind"] != "regular":
            status = "Playoffs"
        elif w.get("locked"):
            status = "Locked"
        else:
            status = "Played" if any(r.get("date") == w["date"] for r in results) else "Upcoming"
        calendar.append({
            "Date": date.fromisoformat(w["date"]).strftime("%a %b %-d"),
            "Matchups": ", ".join(f"{x} v {y}" for x, y in w["matchups"]) or "-",
            "Games": len(w["games"]),
            "Status": status,
        })
    st.dataframe(calendar, hide_index=True, width="stretch")

    meetings = team_meeting_counts(season)
    st.caption(
        "Scheduled meetings per pair of teams (regular season): "
        + ", ".join(f"{x} v {y}: {n}" for (x, y), n in sorted(meetings.items()))
    )
    scheduled_games = games_per_player(season)
    if scheduled_games:
        spread = [scheduled_games.get(p, 0) for members in teams.values() for p in members]
        st.caption(f"Games scheduled per player this season: {min(spread)}-{max(spread)}.")

with tab_players:
    records = compute_records(results)
    st.dataframe(
        [
            {
                "Player": p["name"],
                "Team": team_of.get(p["name"], ""),
                "Rating": round(float(p["rating"])),
                "W": records.get(p["name"], {}).get("wins", 0),
                "L": records.get(p["name"], {}).get("losses", 0),
                "D": records.get(p["name"], {}).get("draws", 0),
                "Pts +/-": records.get(p["name"], {}).get("pf", 0) - records.get(p["name"], {}).get("pa", 0),
            }
            for p in sorted(players, key=lambda p: -float(p["rating"]))
        ],
        hide_index=True,
        width="stretch",
    )

with tab_score:
    st.caption(f"Scores are recorded against: {week_label(week)}")
    labels = {
        f"{g['time_slot']} {g['court']}: {' & '.join(g['team_a'])} vs {' & '.join(g['team_b'])}": g for g in games
    }
    choice = st.selectbox("Scheduled game", ["Custom"] + list(labels))
    preset = labels.get(choice)
    names = sorted(p["name"] for p in players)
    league_names = [p["name"] for p in players]
    outside_used = False
    sub_records: list[dict] = []

    if preset:
        scheduled = preset["team_a"] + preset["team_b"]
        pool = [NO_SUB] + [n for n in names if n not in scheduled] + [OUTSIDE_SUB]
        subs: dict[str, str] = {}
        with st.expander("Substitutes"):
            st.caption(
                "A sub from another team counts for the team they filled in for. "
                "A game with someone from outside the league is recorded but doesn't count on the scoreboard."
            )
            for player_name in scheduled:
                key = f"{selected_date}_{choice}_{player_name}"
                pick = st.selectbox(f"{player_name} replaced by", pool, key=f"sub_{key}")
                if pick == OUTSIDE_SUB:
                    typed = st.text_input(f"Name of outside sub for {player_name}", key=f"out_{key}").strip()
                    subs[player_name] = typed or f"Outside sub for {player_name}"
                elif pick != NO_SUB:
                    subs[player_name] = pick
        team_a, team_b, sub_records, outside_used = apply_substitutions(
            preset["team_a"], preset["team_b"], subs, league_names
        )
        st.write(f"**{' & '.join(team_a)}**  vs  **{' & '.join(team_b)}**")
        if outside_used:
            st.warning("An outside sub played, so this game will be recorded but won't count on the scoreboard.")
    else:
        team_a = st.multiselect("Team A", names, key=f"ta_{selected_date}")
        team_b = st.multiselect("Team B", names, key=f"tb_{selected_date}")

    sc1, sc2 = st.columns(2)
    score_a = sc1.number_input("Team A score", min_value=0, max_value=99, value=21)
    score_b = sc2.number_input("Team B score", min_value=0, max_value=99, value=18)

    team_error = validate_teams(team_a, team_b)
    if team_error and (team_a or team_b):
        st.caption(team_error)
    if st.button("Apply result", type="primary", disabled=bool(team_error)):
        counts = not outside_used
        latest = store.get_all()  # others may have entered scores since this page loaded
        players = normalize_players(latest["players"])
        results = latest["results"]
        if counts:
            rating_map = ratings_of(players)
            apply_match_result(rating_map, team_a, team_b, int(score_a), int(score_b))
            for p in players:
                p["rating"] = float(rating_map.get(p["name"], p["rating"]))
            store.put("players", players)
        result = {
            "date": selected_date,
            "team_a": team_a,
            "team_b": team_b,
            "score_a": int(score_a),
            "score_b": int(score_b),
            "counts": counts,
        }
        if preset:
            result["teams"] = preset["teams"]
        if sub_records:
            result["subs"] = sub_records
        results.append(result)
        store.put("results", results)
        regenerate_after(date.fromisoformat(selected_date))
        st.success(
            "Result recorded; ratings and standings updated, and upcoming weeks rebuilt."
            if counts
            else "Result recorded, but not counted on the scoreboard (outside sub)."
        )
        st.rerun()

with tab_messages:
    email_scores = [
        {
            "team": " / ".join(r.get("team_a", [])),
            "opponent": " / ".join(r.get("team_b", [])),
            "score": int(r.get("score_a", 0)),
            "opponent_score": int(r.get("score_b", 0)),
        }
        for r in results[-8:]
        if r.get("counts", True)
    ]
    standing_lines = (
        [f"{r['Position']}. {r['Team']} - {r['Match pts']} pts ({r['Games won']} games won)" for r in current_rows]
        if current_rows
        else None
    )
    label = st.text_input("Email label", value=date.fromisoformat(selected_date).strftime("Week of %b %-d"))
    st.subheader("Update email")
    st.code(build_two_week_email(label, email_scores, standings=standing_lines), language="text")
    st.subheader("Two-day reminder")
    st.code(
        "League reminder: Tuesday matches run 5:00 PM to 8:00 PM across the two courts. "
        "Please confirm your availability and score entry by Monday night. "
        "Time slots rotate for fairness so no one always gets the best or worst times.",
        language="text",
    )

with tab_contacts:
    if not contacts:
        st.info('No contacts yet. Run: python3 import_contacts.py "<league spreadsheet.xlsx>"')
    else:
        playing_teams = {t for pair in week["matchups"] for t in pair}
        week_players = {p for t in playing_teams for p in teams.get(t, [])}
        query = st.text_input("Search contacts").strip().lower()
        shown = [c for c in contacts if query in c["name"].lower() or query in c["email"].lower()]
        st.dataframe(
            [
                {
                    "Name": c["name"],
                    "Email": c["email"],
                    "Team": team_of.get(c.get("roster_name") or "", ""),
                    "In this week's matches": "Yes" if c.get("roster_name") in week_players else "",
                }
                for c in shown
            ],
            hide_index=True,
            width="stretch",
        )
        week_emails = sorted({c["email"] for c in contacts if c.get("roster_name") in week_players})
        st.caption(f"{len(contacts)} contacts; {len(week_emails)} on teams playing this week.")
        st.text_area("Emails for this week (paste into Bcc)", "; ".join(week_emails), height=100)
        missing = sorted(week_players - {c.get("roster_name") for c in contacts})
        if missing:
            st.warning(f"No contact found for: {', '.join(missing)}")
