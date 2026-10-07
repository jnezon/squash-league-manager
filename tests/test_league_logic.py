from league_logic import (
    apply_match_result,
    apply_substitutions,
    build_match_schedule,
    build_two_week_email,
    compute_rating_delta,
    compute_records,
    match_contact_to_roster,
    compute_time_fairness,
    players_sitting_out,
    record_schedule_history,
    validate_teams,
)


def test_rating_delta_raises_winner_rating():
    winner_delta, loser_delta = compute_rating_delta(1500, 1500, 21, 18)
    assert winner_delta > 0
    assert loser_delta < 0
    assert winner_delta == -loser_delta


def test_draw_changes_nothing():
    assert compute_rating_delta(1500, 1600, 20, 20) == (0.0, 0.0)


def test_ratings_conserve_points_over_many_matches():
    ratings = {n: 1500.0 for n in "ABCD"}
    for i in range(50):
        apply_match_result(ratings, ["A", "B"], ["C", "D"], 21 if i % 3 else 10, 15)
    assert abs(sum(ratings.values()) - 6000) < 0.5


def test_validate_teams():
    assert validate_teams(["A", "B"], ["C", "D"]) is None
    assert validate_teams(["A", "B"], ["B", "D"])
    assert validate_teams(["A"], ["C", "D"])
    assert validate_teams([], ["C"])


def _names(n):
    return [f"P{i:02d}" for i in range(n)]


def test_schedule_no_slot_court_collisions_and_no_duplicate_players():
    schedule = build_match_schedule(_names(30))
    keys = [(m["time_slot"], m["court"]) for m in schedule]
    assert len(keys) == len(set(keys))
    seen = [p for m in schedule for p in m["players"]]
    assert len(seen) == len(set(seen)) == 28
    assert all(len(m["players"]) == 4 for m in schedule)


def test_leftover_players_reported_and_rotated_by_byes():
    names = _names(30)
    first = build_match_schedule(names)
    out1 = players_sitting_out(names, first)
    assert len(out1) == 2
    history = record_schedule_history({}, first, names)
    out2 = players_sitting_out(names, build_match_schedule(names, history))
    assert not set(out1) & set(out2)


def test_groups_are_rating_ordered_and_teams_balanced():
    names = _names(8)
    ratings = {n: 1000 + 10 * i for i, n in enumerate(names)}
    schedule = build_match_schedule(names, ratings=ratings)
    top = next(m for m in schedule if "P07" in m["players"])
    assert set(top["players"]) == {"P04", "P05", "P06", "P07"}
    assert set(top["team_a"]) == {"P07", "P04"}
    assert set(top["team_b"]) == {"P06", "P05"}


def test_history_pushes_prime_hogs_out_of_prime():
    names = _names(8)
    hogs = {"P00", "P01", "P02", "P03"}
    history = {n: {"prime": 5} for n in hogs}
    schedule = build_match_schedule(names, history)
    hog_match = next(m for m in schedule if set(m["players"]) == hogs)
    assert compute_time_fairness([hog_match])["prime"] == 0


def test_capacity_limits_matches():
    schedule = build_match_schedule(_names(60))
    assert len(schedule) == 10


def test_too_few_players():
    assert build_match_schedule(_names(3)) == []


def test_two_week_email_contains_summary_and_next_steps():
    result = build_two_week_email(
        week_label="Week 5",
        scores=[
            {"team": "Team A", "score": 21, "opponent": "Team B", "opponent_score": 17},
            {"team": "Team C", "score": 18, "opponent": "Team D", "opponent_score": 21},
        ],
    )
    assert "Week 5" in result
    assert "Team A 21 - 17 Team B" in result
    assert "Next steps" in result


def test_email_with_no_scores_has_no_fake_results():
    assert "No results recorded yet" in build_two_week_email("Week 1", [])


def test_partner_rotation_avoids_repeat_partners():
    names = ["A", "B", "C", "D"]
    ratings = {"A": 1600, "B": 1550, "C": 1500, "D": 1450}
    history = {}
    seen = set()
    for _ in range(3):
        schedule = build_match_schedule(names, history, ratings=ratings)
        m = schedule[0]
        seen.add(frozenset(m["team_a"]))
        seen.add(frozenset(m["team_b"]))
        record_schedule_history(history, schedule, names)
    # three weeks, three different pairings -> all 6 distinct pairs used
    assert len(seen) == 6


def test_compute_records():
    results = [
        {"team_a": ["A", "B"], "team_b": ["C", "D"], "score_a": 21, "score_b": 15},
        {"team_a": ["A", "C"], "team_b": ["B", "D"], "score_a": 10, "score_b": 10},
    ]
    rec = compute_records(results)
    assert rec["A"] == {"wins": 1, "losses": 0, "draws": 1, "pf": 31, "pa": 25}
    assert rec["C"]["losses"] == 1 and rec["C"]["draws"] == 1


def test_match_contact_to_roster():
    roster = ["Carla Mendes", "Felix Thornbury", "Gary Marston", "Gary MacLeod", "Dana Whitfield"]
    assert match_contact_to_roster("Dana Whitfield", roster) == "Dana Whitfield"
    assert match_contact_to_roster("Team Carla", roster) == "Carla Mendes"
    assert match_contact_to_roster("Felix Thornbery", roster) == "Felix Thornbury"
    assert match_contact_to_roster("Team Gary", roster) is None  # ambiguous
    assert match_contact_to_roster("Stranger Person", roster) is None


def test_substitutions_league_and_outside():
    league = ["A", "B", "C", "D", "E"]
    a, b, recs, outside = apply_substitutions(["A", "B"], ["C", "D"], {"B": "E"}, league)
    assert (a, b, outside) == (["A", "E"], ["C", "D"], False)
    assert recs == [{"for": "B", "sub": "E", "outside": False}]
    a, b, recs, outside = apply_substitutions(["A", "B"], ["C", "D"], {"D": "Guest Player", "A": ""}, league)
    assert (a, b, outside) == (["A", "B"], ["C", "Guest Player"], True)


def test_records_skip_uncounted_games():
    results = [
        {"team_a": ["A"], "team_b": ["B"], "score_a": 21, "score_b": 5},
        {"team_a": ["A"], "team_b": ["B"], "score_a": 21, "score_b": 5, "counts": False},
    ]
    assert compute_records(results)["A"]["wins"] == 1


def test_email_includes_standings():
    text = build_two_week_email("Week 2", [], standings=["1. Catalin - 2 pts"])
    assert "Team standings" in text and "1. Catalin - 2 pts" in text
