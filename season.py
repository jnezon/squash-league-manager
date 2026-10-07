"""Season engine for the Tuesday doubles team league.

Four teams meet in a rotating round robin: every Tuesday each team plays one
other team, and over every three regular weeks each team plays each of the
others exactly once. Inside a team match, players are paired into doubles
pairs (4 games, one per time slot, on one court). Partners, opponents, time
slots and sit-outs all rotate using a running history.
"""
from __future__ import annotations

import itertools
from collections import Counter
from datetime import date, timedelta
from typing import Any, Iterator

from league_logic import DEFAULT_RATING, TIME_BUCKETS

GAME_SLOTS = ["5:45pm", "6:30pm", "7:15pm", "8:00pm"]
COURTS = ["Court 1", "Court 2"]
# How many of the four game slots fall in each bucket, so "fair" means proportional.
BUCKET_SLOTS = {"early": 1, "prime": 2, "late": 1}

Game = dict[str, Any]
Week = dict[str, Any]
History = dict[str, dict[str, Any]]


def tuesdays(start: date, end: date) -> list[date]:
    """Every Tuesday from ``start`` through ``end`` inclusive."""
    day = start + timedelta(days=(1 - start.weekday()) % 7)
    days = []
    while day <= end:
        days.append(day)
        day += timedelta(days=7)
    return days


def round_robin_rounds(teams: list[str]) -> list[list[tuple[str, str]]]:
    """Circle-method rounds; for four teams the first team meets the others in listed order."""
    if len(teams) < 2 or len(teams) % 2:
        raise ValueError("Need an even number of teams (at least two).")
    ring = [teams[0]] + list(reversed(teams[1:]))
    size = len(ring)
    rounds = []
    for _ in range(size - 1):
        rounds.append([(ring[i], ring[size - 1 - i]) for i in range(size // 2)])
        ring = [ring[0], ring[-1]] + ring[1:-1]
    return rounds


def _matchings(items: list[str]) -> Iterator[list[tuple[str, str]]]:
    if not items:
        yield []
        return
    first, rest = items[0], items[1:]
    for i, partner in enumerate(rest):
        for tail in _matchings(rest[:i] + rest[i + 1 :]):
            yield [(first, partner)] + tail


def _count(history: History, player: str, key: str, other: str | None = None) -> int:
    entry = history.get(player, {})
    return entry.get(key, {}).get(other, 0) if other is not None else entry.get(key, 0)


def _pair_rating(ratings: dict[str, float], pair: tuple[str, str]) -> float:
    return sum(ratings.get(p, DEFAULT_RATING) for p in pair) / 2


def _split_byes(players: list[str], play_count: int, history: History) -> tuple[list[str], list[str]]:
    """Whoever has sat out least plays; roster order breaks ties."""
    order = sorted(range(len(players)), key=lambda i: (_count(history, players[i], "byes"), i))
    sitting = set(order[: len(players) - play_count])
    play = [p for i, p in enumerate(players) if i not in sitting]
    byes = [p for i, p in enumerate(players) if i in sitting]
    return play, byes


def _best_pairs(players: list[str], history: History, ratings: dict[str, float]) -> list[tuple[str, str]]:
    """Fewest repeat partnerships first; among equals, the most evenly matched pairs."""

    def key(matching: list[tuple[str, str]]) -> tuple[int, float]:
        repeats = sum(_count(history, a, "partners", b) for a, b in matching)
        strengths = [_pair_rating(ratings, pair) for pair in matching]
        return repeats, max(strengths) - min(strengths)

    return min(_matchings(players), key=key)


def build_team_match(
    team_x: str,
    players_x: list[str],
    team_y: str,
    players_y: list[str],
    court: str,
    history: History,
    ratings: dict[str, float],
) -> tuple[list[Game], list[str]]:
    """Doubles games for one team-vs-team match, plus the players who sit out."""
    game_count = min(len(GAME_SLOTS), len(players_x) // 2, len(players_y) // 2)
    if game_count == 0:
        return [], list(players_x) + list(players_y)

    play_x, byes_x = _split_byes(players_x, game_count * 2, history)
    play_y, byes_y = _split_byes(players_y, game_count * 2, history)
    pairs_x = _best_pairs(play_x, history, ratings)
    pairs_y = _best_pairs(play_y, history, ratings)

    best: tuple[float, tuple[int, ...], tuple[str, ...]] | None = None
    for order_y in itertools.permutations(range(game_count)):
        for slots in itertools.permutations(GAME_SLOTS, game_count):
            cost = 0.0
            for g in range(game_count):
                px, py = pairs_x[g], pairs_y[order_y[g]]
                cost += 5 * sum(_count(history, a, "opponents", b) for a in px for b in py)
                # 50 rating points of mismatch costs as much as one repeat opponent
                cost += abs(_pair_rating(ratings, px) - _pair_rating(ratings, py)) / 10
                bucket = TIME_BUCKETS[slots[g]]
                cost += 3 * sum(_count(history, p, bucket) / BUCKET_SLOTS[bucket] for p in (*px, *py))
            if best is None or cost < best[0]:
                best = (cost, order_y, slots)
    assert best is not None
    _, order_y, slots = best

    games = []
    for g in range(game_count):
        px, py = list(pairs_x[g]), list(pairs_y[order_y[g]])
        games.append({
            "time_slot": slots[g],
            "court": court,
            "teams": [team_x, team_y],
            "team_a": px,
            "team_b": py,
            "players": px + py,
        })
    games.sort(key=lambda game: GAME_SLOTS.index(game["time_slot"]))
    return games, byes_x + byes_y


def record_week_history(history: History, games: list[Game], bye_players: list[str]) -> History:
    """Fold a played week into the running history (slots, partners, opponents, byes)."""
    for game in games:
        bucket = TIME_BUCKETS.get(game["time_slot"], "early")
        side_a, side_b = game["team_a"], game["team_b"]
        for player in side_a + side_b:
            entry = history.setdefault(player, {})
            entry[bucket] = entry.get(bucket, 0) + 1
        for side, other in ((side_a, side_b), (side_b, side_a)):
            for player in side:
                entry = history.setdefault(player, {})
                for mate in side:
                    if mate != player:
                        partners = entry.setdefault("partners", {})
                        partners[mate] = partners.get(mate, 0) + 1
                for foe in other:
                    opponents = entry.setdefault("opponents", {})
                    opponents[foe] = opponents.get(foe, 0) + 1
    for player in bye_players:
        entry = history.setdefault(player, {})
        entry["byes"] = entry.get("byes", 0) + 1
    return history


def locked_week(
    day: date,
    games: list[Game],
    teams: dict[str, list[str]],
    matchups: list[tuple[str, str]],
) -> Week:
    """Wrap games that were already decided/communicated as a fixed week."""
    team_of = {p: name for name, members in teams.items() for p in members}
    played = {p for game in games for p in game["players"]}
    for game in games:
        side_teams = [team_of.get(game["team_a"][0]), team_of.get(game["team_b"][0])]
        game["teams"] = [t or "?" for t in side_teams]
    return {
        "date": day.isoformat(),
        "kind": "regular",
        "locked": True,
        "matchups": [list(m) for m in matchups],
        "games": games,
        "byes": [p for members in teams.values() for p in members if p not in played],
    }


def build_season(
    teams: dict[str, list[str]],
    dates: list[date],
    regular_weeks: int,
    ratings: dict[str, float] | None = None,
    kept_weeks: list[Week] | None = None,
) -> list[Week]:
    """Build every week in ``dates``; ``kept_weeks`` are used as-is and seed the history."""
    ratings = ratings or {}
    kept = {w["date"]: w for w in (kept_weeks or [])}
    rounds = round_robin_rounds(list(teams))
    history: History = {}
    for week in sorted(kept.values(), key=lambda w: w["date"]):
        record_week_history(history, week["games"], week["byes"])

    weeks: list[Week] = []
    for index, day in enumerate(dates):
        key = day.isoformat()
        if key in kept:
            weeks.append(kept[key])
            continue
        if index >= regular_weeks:
            weeks.append({"date": key, "kind": "playoff", "locked": False, "matchups": [], "games": [], "byes": []})
            continue
        matchups = rounds[index % len(rounds)]
        games: list[Game] = []
        byes: list[str] = []
        for court_index, (x, y) in enumerate(matchups):
            match_games, match_byes = build_team_match(
                x, teams[x], y, teams[y], COURTS[court_index % len(COURTS)], history, ratings
            )
            games += match_games
            byes += match_byes
        record_week_history(history, games, byes)
        weeks.append({
            "date": key,
            "kind": "regular",
            "locked": False,
            "matchups": [list(m) for m in matchups],
            "games": games,
            "byes": byes,
        })
    for week in kept.values():
        if week["date"] not in {w["date"] for w in weeks}:
            weeks.append(week)
    return sorted(weeks, key=lambda w: w["date"])


def team_meeting_counts(weeks: list[Week]) -> dict[tuple[str, str], int]:
    """How many regular-season weeks each pair of teams is scheduled to meet."""
    counts: Counter[tuple[str, str]] = Counter()
    for week in weeks:
        if week.get("kind") == "regular":
            for x, y in week["matchups"]:
                counts[tuple(sorted((x, y)))] += 1
    return dict(counts)


def games_per_player(weeks: list[Week]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for week in weeks:
        for game in week["games"]:
            counts.update(game["players"])
    return dict(counts)


def _teams_in_result(result: dict[str, Any], team_of: dict[str, str]) -> tuple[str, str] | None:
    side_a = {team_of.get(p) for p in result.get("team_a", [])}
    side_b = {team_of.get(p) for p in result.get("team_b", [])}
    if len(side_a) != 1 or len(side_b) != 1 or None in side_a | side_b or side_a == side_b:
        return None
    return next(iter(side_a)), next(iter(side_b))


def weekly_standings(
    results: list[dict[str, Any]],
    teams: dict[str, list[str]],
    weeks: list[Week],
    win_points: int = 2,
    draw_points: int = 1,
) -> list[dict[str, Any]]:
    """Cumulative team standings after each regular week that has results.

    A team match (all of one week's games between two teams) is won by the team
    that wins more of its games; it only earns match points once every
    scheduled game in it has a result. Games won and point difference are
    counted as results come in. Games between players of different teams than
    scheduled (or mixed teams) are skipped. Ranked by match points, then games
    won, then point difference. A game with an outside-the-league sub
    (``counts`` false) is played but doesn't score; it still lets the match finish.
    """
    team_of = {p: name for name, members in teams.items() for p in members}
    scheduled: Counter[tuple[str, frozenset[str]]] = Counter()
    for week in weeks:
        for game in week["games"]:
            if len(set(game.get("teams", []))) == 2:
                scheduled[(week["date"], frozenset(game["teams"]))] += 1

    by_date: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_date.setdefault(str(result.get("date")), []).append(result)

    totals = {
        name: {"Team": name, "Matches": 0, "W": 0, "D": 0, "L": 0, "Match pts": 0,
               "Games won": 0, "Games lost": 0, "Pts +/-": 0}
        for name in teams
    }
    snapshots: list[dict[str, Any]] = []
    for week in sorted(weeks, key=lambda w: w["date"]):
        week_results = by_date.get(week["date"], [])
        if week.get("kind") != "regular" or not week_results:
            continue
        matches: dict[frozenset[str], dict[str, Any]] = {}
        for result in week_results:
            # Games entered against the schedule carry their teams, so a league sub
            # from another team still counts for the team they played for.
            pair = tuple(result["teams"]) if result.get("teams") else _teams_in_result(result, team_of)
            if pair is None or pair[0] == pair[1] or not all(t in totals for t in pair):
                continue
            ta, tb = pair
            record = matches.setdefault(frozenset(pair), {"games": 0, ta: [0, 0], tb: [0, 0]})
            record["games"] += 1
            if not result.get("counts", True):
                continue  # outside sub: the game was played but doesn't score
            sa, sb = int(result.get("score_a", 0)), int(result.get("score_b", 0))
            record[ta][0] += sa > sb
            record[tb][0] += sb > sa
            record[ta][1] += sa - sb
            record[tb][1] += sb - sa
        for pair, record in matches.items():
            x, y = sorted(pair)
            for team, other in ((x, y), (y, x)):
                row = totals[team]
                row["Games won"] += record[team][0]
                row["Games lost"] += record[other][0]
                row["Pts +/-"] += record[team][1]
            if record["games"] >= scheduled.get((week["date"], pair), 0) > 0:
                for team, other in ((x, y), (y, x)):
                    row = totals[team]
                    row["Matches"] += 1
                    if record[team][0] > record[other][0]:
                        row["W"] += 1
                        row["Match pts"] += win_points
                    elif record[team][0] < record[other][0]:
                        row["L"] += 1
                    else:
                        row["D"] += 1
                        row["Match pts"] += draw_points
        ranked = sorted(
            (dict(row) for row in totals.values()),
            key=lambda r: (-r["Match pts"], -r["Games won"], -r["Pts +/-"], r["Team"]),
        )
        for position, row in enumerate(ranked, start=1):
            row["Position"] = position
        snapshots.append({"date": week["date"], "rows": ranked})
    return snapshots


def regenerate(
    weeks: list[Week],
    teams: dict[str, list[str]],
    from_date: date,
    regular_weeks: int,
    ratings: dict[str, float] | None = None,
) -> list[Week]:
    """Rebuild every week on/after ``from_date``; earlier weeks are kept as played."""
    dates = [date.fromisoformat(w["date"]) for w in weeks]
    kept = [w for w in weeks if date.fromisoformat(w["date"]) < from_date]
    return build_season(teams, dates, regular_weeks, ratings, kept_weeks=kept)
