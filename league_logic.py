from __future__ import annotations

import difflib
from collections import defaultdict
from typing import Any

TIME_BUCKETS = {
    "5:00pm": "early",
    "5:45pm": "early",
    "6:30pm": "prime",
    "7:15pm": "prime",
    "8:00pm": "late",
}
DEFAULT_SLOTS = list(TIME_BUCKETS)
DEFAULT_COURTS = ["Court 1", "Court 2"]
DEFAULT_RATING = 1500
K_FACTOR = 32


def compute_rating_delta(team_a_rating: float, team_b_rating: float, team_a_score: int, team_b_score: int) -> tuple[float, float]:
    """Return rating deltas for team A and team B following a standard Elo-style update."""
    if team_a_score == team_b_score:
        return 0.0, 0.0

    expected_a = 1 / (1 + 10 ** ((team_b_rating - team_a_rating) / 400))
    actual_a = 1.0 if team_a_score > team_b_score else 0.0
    delta_a = round(K_FACTOR * (actual_a - expected_a), 2)
    return delta_a, -delta_a


def apply_match_result(players: dict[str, float], team_a: list[str], team_b: list[str], score_a: int, score_b: int) -> dict[str, float]:
    """Apply a match result to the player ratings stored by player name.

    Ratings stay fractional so repeated updates don't leak points to rounding.
    """
    if not team_a or not team_b:
        return players

    team_a_rating = sum(players.get(player, DEFAULT_RATING) for player in team_a) / len(team_a)
    team_b_rating = sum(players.get(player, DEFAULT_RATING) for player in team_b) / len(team_b)
    delta_a, delta_b = compute_rating_delta(team_a_rating, team_b_rating, score_a, score_b)

    for player in team_a:
        players[player] = round(players.get(player, DEFAULT_RATING) + delta_a, 2)
    for player in team_b:
        players[player] = round(players.get(player, DEFAULT_RATING) + delta_b, 2)
    return players


def validate_teams(team_a: list[str], team_b: list[str]) -> str | None:
    """Return an error message if the two teams can't be a valid match, else None."""
    if not team_a or not team_b:
        return "Pick at least one player for each team."
    if len(team_a) != len(team_b):
        return "Teams must be the same size."
    if len(set(team_a)) != len(team_a) or len(set(team_b)) != len(team_b):
        return "The same person can't fill two spots on one team."
    overlap = set(team_a) & set(team_b)
    if overlap:
        return f"A player can't be on both teams: {', '.join(sorted(overlap))}."
    return None


def compute_time_fairness(schedule: list[dict[str, Any]] | dict[str, Any]) -> dict[str, int | dict[str, int]]:
    """Count how many matches fall into each time bucket."""
    counts = {"early": 0, "prime": 0, "late": 0}
    slot_counts: dict[str, int] = defaultdict(int)
    entries = schedule if isinstance(schedule, list) else [schedule] if isinstance(schedule, dict) else []

    for match in entries:
        if not isinstance(match, dict):
            continue
        slot = str(match.get("time_slot") or match.get("time") or "5:00pm")
        bucket = TIME_BUCKETS.get(slot, "early")
        counts[bucket] += 1
        slot_counts[slot] += 1
    return {"early": counts["early"], "prime": counts["prime"], "late": counts["late"], "slot_counts": dict(slot_counts)}


def _bucket_count(history: dict[str, dict[str, int]], player: str, bucket: str) -> int:
    return history.get(player, {}).get(bucket, 0)


def _partner_count(history: dict[str, dict[str, int]], a: str, b: str) -> int:
    return history.get(a, {}).get("partners", {}).get(b, 0)


def _choose_teams(group: list[str], history: dict[str, dict[str, int]]) -> tuple[list[str], list[str]]:
    """Split a rating-sorted group of four into teams, avoiding repeat partners.

    The first option is the rating-balanced split; later options only win if
    they repeat fewer past partnerships.
    """
    g = group
    options = [
        ([g[0], g[3]], [g[1], g[2]]),
        ([g[0], g[2]], [g[1], g[3]]),
        ([g[0], g[1]], [g[2], g[3]]),
    ]
    return min(
        options,
        key=lambda o: _partner_count(history, o[0][0], o[0][1]) + _partner_count(history, o[1][0], o[1][1]),
    )


def _choose_sitting_out(names: list[str], count: int, history: dict[str, dict[str, int]]) -> list[str]:
    """Pick who sits out: whoever has sat out least so far (roster order breaks ties)."""
    if count <= 0:
        return []
    order = sorted(range(len(names)), key=lambda i: (_bucket_count(history, names[i], "byes"), i))
    return [names[i] for i in order[:count]]


def build_match_schedule(
    players: list[str],
    history: dict[str, dict[str, Any]] | None = None,
    time_slots: list[str] | None = None,
    ratings: dict[str, float] | None = None,
    courts: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build match groups of four.

    - Players are grouped by rating so each match is competitive; each group is
      split into two balanced teams (strongest + weakest vs. middle two).
    - If the player count isn't a multiple of four (or exceeds court capacity),
      whoever has sat out least sits out; see ``players_sitting_out``.
    - Each group goes to the free (slot, court) whose time bucket its players
      have used least in ``history``; no two matches share a slot and court.
    """
    names = list(dict.fromkeys(players))
    if len(names) < 4:
        return []

    history = history or {}
    ratings = ratings or {}
    slots = time_slots or DEFAULT_SLOTS
    court_names = courts or DEFAULT_COURTS
    capacity = len(slots) * len(court_names)

    match_count = min(len(names) // 4, capacity)
    sitting_out = set(_choose_sitting_out(names, len(names) - match_count * 4, history))
    playing = [name for name in names if name not in sitting_out]

    playing.sort(key=lambda name: -ratings.get(name, DEFAULT_RATING))
    groups = [playing[i : i + 4] for i in range(0, len(playing), 4)]

    taken: set[tuple[str, str]] = set()
    slot_load: dict[str, int] = defaultdict(int)
    matches: list[dict[str, Any]] = []

    for group in groups:
        def cost(slot_index: int) -> tuple[int, int, int]:
            slot = slots[slot_index]
            bucket = TIME_BUCKETS.get(slot, "early")
            return (sum(_bucket_count(history, p, bucket) for p in group), slot_load[slot], slot_index)

        for slot_index in sorted(range(len(slots)), key=cost):
            slot = slots[slot_index]
            court = next((c for c in court_names if (slot, c) not in taken), None)
            if court is not None:
                break
        else:  # unreachable: match_count <= capacity
            break

        team_a, team_b = _choose_teams(group, history)
        taken.add((slot, court))
        slot_load[slot] += 1
        matches.append({
            "time_slot": slot,
            "court": court,
            "players": group,
            "team_a": team_a,
            "team_b": team_b,
        })

    matches.sort(key=lambda m: (slots.index(m["time_slot"]), court_names.index(m["court"])))
    return matches


def players_sitting_out(players: list[str], schedule: list[dict[str, Any]]) -> list[str]:
    """Players on the roster who aren't in any scheduled match."""
    scheduled = {p for match in schedule if isinstance(match, dict) for p in match.get("players", [])}
    return [p for p in players if p not in scheduled]


def record_schedule_history(
    history: dict[str, dict[str, int]],
    schedule: list[dict[str, Any]],
    roster: list[str],
) -> dict[str, dict[str, int]]:
    """Add a played schedule's time buckets (and byes) to the running history."""
    for match in schedule:
        if not isinstance(match, dict):
            continue
        bucket = TIME_BUCKETS.get(str(match.get("time_slot")), "early")
        for player in match.get("players", []):
            entry = history.setdefault(player, {})
            entry[bucket] = entry.get(bucket, 0) + 1
        for team in (match.get("team_a", []), match.get("team_b", [])):
            for player in team:
                for mate in team:
                    if mate != player:
                        partners = history.setdefault(player, {}).setdefault("partners", {})
                        partners[mate] = partners.get(mate, 0) + 1
    for player in players_sitting_out(roster, schedule):
        entry = history.setdefault(player, {})
        entry["byes"] = entry.get("byes", 0) + 1
    return history


def apply_substitutions(
    team_a: list[str],
    team_b: list[str],
    subs: dict[str, str],
    league_players: list[str],
) -> tuple[list[str], list[str], list[dict[str, Any]], bool]:
    """Swap scheduled players for their substitutes.

    ``subs`` maps a scheduled player to the person who actually played. Returns
    the actual sides, a record of each swap, and whether anyone from outside
    the league played (such a game doesn't count toward the scoreboard).
    """
    league = set(league_players)
    replacement = {old: new.strip() for old, new in subs.items() if new and new.strip()}
    records = [{"for": old, "sub": new, "outside": new not in league} for old, new in replacement.items()]
    actual_a = [replacement.get(p, p) for p in team_a]
    actual_b = [replacement.get(p, p) for p in team_b]
    return actual_a, actual_b, records, any(r["outside"] for r in records)


def compute_records(results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Win/loss/draw and points for/against per player from recorded results.

    Games with an outside-the-league sub (``counts`` false) are left out.
    """
    records: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0, "draws": 0, "pf": 0, "pa": 0})
    for result in results:
        if not result.get("counts", True):
            continue
        score_a, score_b = int(result.get("score_a", 0)), int(result.get("score_b", 0))
        for team, own, other in ((result.get("team_a", []), score_a, score_b), (result.get("team_b", []), score_b, score_a)):
            for player in team:
                rec = records[player]
                rec["wins" if own > other else "losses" if own < other else "draws"] += 1
                rec["pf"] += own
                rec["pa"] += other
    return dict(records)


def match_contact_to_roster(contact_name: str, roster: list[str]) -> str | None:
    """Map a spreadsheet contact name to a roster player, or None.

    Handles "Team Catalin"-style captain rows (unique first-name match) and
    small spelling differences (fuzzy match); never guesses between ties.
    """
    name = contact_name.strip()
    if name in roster:
        return name
    lowered = {r.lower(): r for r in roster}
    if name.lower() in lowered:
        return lowered[name.lower()]
    if name.lower().startswith("team "):
        first = name[5:].strip().lower()
        hits = [r for r in roster if r.split()[0].lower() == first]
        return hits[0] if len(hits) == 1 else None
    close = difflib.get_close_matches(name.lower(), list(lowered), n=2, cutoff=0.85)
    if len(close) == 1 or (len(close) == 2 and difflib.SequenceMatcher(None, name.lower(), close[0]).ratio() - difflib.SequenceMatcher(None, name.lower(), close[1]).ratio() > 0.05):
        return lowered[close[0]]
    return None


def build_two_week_email(week_label: str, scores: list[dict[str, Any]], standings: list[str] | None = None) -> str:
    """Create a summary email string for the next two-week league update."""
    lines = [
        f"Subject: {week_label} league update",
        "",
        "Hi everyone,",
        "",
        f"Here is the summary for {week_label}.",
        "",
    ]

    if not scores:
        lines.append("- No results recorded yet.")
    for item in scores:
        team = item.get("team", "Team")
        opponent = item.get("opponent", "Opponent")
        score = item.get("score", 0)
        opponent_score = item.get("opponent_score", 0)
        lines.append(f"- {team} {score} - {opponent_score} {opponent}")

    if standings:
        lines.extend(["", "Team standings", *[f"- {row}" for row in standings]])

    lines.extend(
        [
            "",
            "Next steps",
            "- Review the current rankings and any matchup changes before the next Tuesday.",
            "- Keep the 5:00 PM and 8:00 PM slots balanced across the league.",
            "- Send score corrections before the final two-day reminder.",
            "",
            "Thanks,",
            "League Admin",
        ]
    )
    return "\n".join(lines)
