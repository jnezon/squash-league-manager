"""Build data/season.json: every Tuesday from the start date through the end date.

Usage: python3 generate_season.py [--regular-weeks 12] [--start 2026-10-06] [--end 2026-12-29]

Week 1 is taken as already emailed (data/week1_emailed.json) and stays locked.
Re-running replaces data/season.json, so use the app's "Regenerate upcoming
weeks" button instead once real results exist.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from season import build_season, locked_week, team_meeting_counts, tuesdays

DATA_DIR = Path(__file__).resolve().parent / "data"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--regular-weeks", type=int, default=12)
    parser.add_argument("--start", default="2026-10-06")
    parser.add_argument("--end", default="2026-12-29")
    args = parser.parse_args()

    teams = json.loads((DATA_DIR / "teams.json").read_text(encoding="utf-8"))
    players = json.loads((DATA_DIR / "players.json").read_text(encoding="utf-8"))
    ratings = {p["name"]: float(p["rating"]) for p in players if isinstance(p, dict)}
    dates = tuesdays(date.fromisoformat(args.start), date.fromisoformat(args.end))

    kept = []
    emailed = DATA_DIR / "week1_emailed.json"
    if emailed.exists():
        first = list(teams)
        matchups = [(first[0], first[1]), (first[3], first[2])]
        kept.append(locked_week(dates[0], json.loads(emailed.read_text(encoding="utf-8")), teams, matchups))

    weeks = build_season(teams, dates, args.regular_weeks, ratings, kept_weeks=kept)
    (DATA_DIR / "season.json").write_text(json.dumps(weeks, indent=2), encoding="utf-8")
    print(f"{len(weeks)} Tuesdays, {args.regular_weeks} regular weeks; meetings per team pair:")
    for (x, y), n in sorted(team_meeting_counts(weeks).items()):
        print(f"  {x} vs {y}: {n}")


if __name__ == "__main__":
    main()
