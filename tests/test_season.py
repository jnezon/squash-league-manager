from collections import Counter
from datetime import date

from season import (
    GAME_SLOTS,
    build_season,
    games_per_player,
    regenerate,
    round_robin_rounds,
    team_meeting_counts,
    weekly_standings,
    tuesdays,
)

TEAMS = {
    "Catalin": [f"C{i}" for i in range(9)],
    "Alfredo": [f"A{i}" for i in range(9)],
    "Tania": [f"T{i}" for i in range(10)],
    "Anna": [f"N{i}" for i in range(9)],
}
DATES = tuesdays(date(2026, 10, 6), date(2026, 12, 29))


def test_tuesdays_cover_october_to_december():
    assert len(DATES) == 13
    assert DATES[0] == date(2026, 10, 6) and DATES[-1] == date(2026, 12, 29)
    assert all(d.weekday() == 1 for d in DATES)


def test_round_robin_matches_the_spreadsheet_rotation():
    rounds = round_robin_rounds(list(TEAMS))
    assert rounds[0] == [("Catalin", "Alfredo"), ("Anna", "Tania")]
    assert rounds[1] == [("Catalin", "Tania"), ("Alfredo", "Anna")]
    assert rounds[2] == [("Catalin", "Anna"), ("Tania", "Alfredo")]


def test_every_team_pair_meets_equally_often():
    weeks = build_season(TEAMS, DATES, regular_weeks=12)
    counts = team_meeting_counts(weeks)
    assert len(counts) == 6
    assert set(counts.values()) == {4}


def test_each_week_everyone_plays_at_most_once_and_slots_dont_collide():
    for week in build_season(TEAMS, DATES, regular_weeks=12):
        if week["kind"] != "regular":
            continue
        players = [p for g in week["games"] for p in g["players"]]
        assert len(players) == len(set(players))
        keys = [(g["time_slot"], g["court"]) for g in week["games"]]
        assert len(keys) == len(set(keys)) == 8
        for g in week["games"]:
            assert g["time_slot"] in GAME_SLOTS
            assert len(g["team_a"]) == len(g["team_b"]) == 2
            assert set(g["teams"]) in [set(m) for m in week["matchups"]]


def test_games_and_byes_are_shared_fairly_across_the_season():
    weeks = build_season(TEAMS, DATES, regular_weeks=12)
    played = games_per_player(weeks)
    for team, members in TEAMS.items():
        counts = [played.get(p, 0) for p in members]
        assert max(counts) - min(counts) <= 1, (team, counts)


def test_partners_rotate_and_rarely_repeat():
    weeks = build_season(TEAMS, DATES, regular_weeks=12)
    partners = Counter()
    for week in weeks:
        for g in week["games"]:
            for side in (g["team_a"], g["team_b"]):
                partners[frozenset(side)] += 1
    # 12 weeks, 9-player teams (36 possible pairs): nobody should be stuck with one partner
    assert max(partners.values()) <= 2


def test_time_buckets_are_balanced_per_player():
    weeks = build_season(TEAMS, DATES, regular_weeks=12)
    prime = Counter()
    total = Counter()
    for week in weeks:
        for g in week["games"]:
            for p in g["players"]:
                total[p] += 1
                if g["time_slot"] in ("6:30pm", "7:15pm"):
                    prime[p] += 1
    for p in total:
        # prime is half of the slots; nobody should be frozen out of or locked into it
        assert 0.2 <= prime[p] / total[p] <= 0.8, p


def test_kept_week_is_preserved_and_seeds_history():
    first = build_season(TEAMS, DATES, regular_weeks=12)[0]
    kept = {**first, "locked": True}
    again = build_season(TEAMS, DATES, regular_weeks=12, kept_weeks=[kept])
    assert again[0] == kept
    assert set(team_meeting_counts(again).values()) == {4}


def test_regular_weeks_must_be_a_multiple_of_rounds_to_be_equal():
    counts = team_meeting_counts(build_season(TEAMS, DATES, regular_weeks=9))
    assert set(counts.values()) == {3}


def _week_with_results(weeks, index, scores):
    """Fake results for one week: scores[i] = (score_a, score_b) for that week's i-th game."""
    week = weeks[index]
    return [
        {"date": week["date"], "team_a": g["team_a"], "team_b": g["team_b"], "score_a": a, "score_b": b}
        for g, (a, b) in zip(week["games"], scores)
    ]


def test_weekly_standings_accumulate_week_by_week():
    weeks = build_season(TEAMS, DATES, regular_weeks=12)
    # week 1: Catalin beats Alfredo 4-0 games; Tania and Anna split 2-2 (draw)
    first = weeks[0]
    results = []
    for g in first["games"]:
        if set(g["teams"]) == {"Catalin", "Alfredo"}:
            sa, sb = (21, 10) if g["teams"][0] == "Catalin" else (10, 21)
        else:
            idx = [x for x in first["games"] if set(x["teams"]) == {"Tania", "Anna"}].index(g)
            sa, sb = (21, 15) if idx % 2 == 0 else (15, 21)
        results.append({"date": first["date"], "team_a": g["team_a"], "team_b": g["team_b"], "score_a": sa, "score_b": sb})
    snaps = weekly_standings(results, TEAMS, weeks)
    assert len(snaps) == 1
    rows = {r["Team"]: r for r in snaps[0]["rows"]}
    assert rows["Catalin"]["Match pts"] == 2 and rows["Catalin"]["Games won"] == 4
    assert rows["Alfredo"]["L"] == 1 and rows["Alfredo"]["Match pts"] == 0
    assert rows["Tania"]["D"] == rows["Anna"]["D"] == 1
    assert rows["Catalin"]["Position"] == 1 and rows["Alfredo"]["Position"] == 4

    # week 2 adds on top of week 1
    more = _week_with_results(weeks, 1, [(21, 5)] * len(weeks[1]["games"]))
    snaps = weekly_standings(results + more, TEAMS, weeks)
    assert [s["date"] for s in snaps] == [weeks[0]["date"], weeks[1]["date"]]
    assert snaps[1]["rows"][0]["Matches"] >= 1


def test_incomplete_match_counts_games_but_not_match_points():
    weeks = build_season(TEAMS, DATES, regular_weeks=12)
    game = weeks[1]["games"][0]
    partial = [{"date": weeks[1]["date"], "team_a": game["team_a"], "team_b": game["team_b"], "score_a": 21, "score_b": 3}]
    rows = {r["Team"]: r for r in weekly_standings(partial, TEAMS, weeks)[0]["rows"]}
    winner = game["teams"][0]
    assert rows[winner]["Games won"] == 1 and rows[winner]["Match pts"] == 0 and rows[winner]["Matches"] == 0


def test_pairs_and_opponents_follow_ratings():
    teams = {"X": [f"x{i}" for i in range(8)], "Y": [f"y{i}" for i in range(8)],
             "Z": [f"z{i}" for i in range(8)], "W": [f"w{i}" for i in range(8)]}
    ratings = {f"{t}{i}": 1500 + 40 * i for t in "xyzw" for i in range(8)}
    week = build_season(teams, DATES, regular_weeks=12, ratings=ratings)[0]
    for g in week["games"]:
        mean = lambda side: sum(ratings[p] for p in side) / 2
        assert abs(mean(g["team_a"]) - mean(g["team_b"])) <= 120


def test_regenerate_keeps_past_weeks_and_replaces_future():
    weeks = build_season(TEAMS, DATES, regular_weeks=12)
    again = regenerate(weeks, TEAMS, from_date=DATES[3], regular_weeks=12)
    assert again[:3] == weeks[:3]
    assert [w["date"] for w in again] == [w["date"] for w in weeks]
    assert set(team_meeting_counts(again).values()) == {4}


def test_outside_sub_game_is_void_but_lets_the_match_finish():
    weeks = build_season(TEAMS, DATES, regular_weeks=12)
    week = weeks[1]
    x, y = week["matchups"][0]
    games = [g for g in week["games"] if set(g["teams"]) == {x, y}]
    results = []
    for i, g in enumerate(games):
        results.append({
            "date": week["date"], "teams": g["teams"], "team_a": g["team_a"], "team_b": g["team_b"],
            "score_a": 21, "score_b": 10, "counts": i != 0,   # first game had an outside sub
        })
    rows = {r["Team"]: r for r in weekly_standings(results, TEAMS, weeks)[0]["rows"]}
    first = games[0]["teams"][0]
    assert rows[first]["Games won"] == len(games) - 1   # the void game doesn't score
    assert rows[first]["Matches"] == 1 and rows[first]["W"] == 1


def test_league_sub_from_another_team_counts_for_the_scheduled_team():
    weeks = build_season(TEAMS, DATES, regular_weeks=12)
    week = weeks[1]
    g = week["games"][0]
    outsider = next(p for t, m in TEAMS.items() if t not in g["teams"] for p in m)
    side_a = [outsider, g["team_a"][1]]
    result = {"date": week["date"], "teams": g["teams"], "team_a": side_a, "team_b": g["team_b"],
              "score_a": 21, "score_b": 3, "counts": True}
    rows = {r["Team"]: r for r in weekly_standings([result], TEAMS, weeks)[0]["rows"]}
    assert rows[g["teams"][0]]["Games won"] == 1
