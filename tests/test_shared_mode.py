import json

from streamlit.testing.v1 import AppTest

from tests.test_store import FakeSupabase, supabase  # noqa: F401  (fixture)

DATA = {
    "players": [{"name": n, "rating": 1500.0} for n in ["A1", "A2", "B1", "B2"]],
    "teams": {"Alpha": ["A1", "A2"], "Beta": ["B1", "B2"]},
    "results": [],
    "contacts": [],
    "season": [{
        "date": "2099-01-05", "kind": "regular", "locked": False, "matchups": [["Alpha", "Beta"]],
        "byes": [],
        "games": [{"time_slot": "5:45pm", "court": "Court 1", "teams": ["Alpha", "Beta"],
                   "team_a": ["A1", "A2"], "team_b": ["B1", "B2"], "players": ["A1", "A2", "B1", "B2"]}],
    }],
}


def test_published_app_reads_and_writes_the_shared_database(supabase):
    FakeSupabase.rows.update(json.loads(json.dumps(DATA)))
    at = AppTest.from_file("../app.py", default_timeout=60)
    at.secrets["password"] = "pw"
    at.secrets["supabase"] = {"url": supabase.endpoint.split("/rest/")[0], "key": "service-key"}
    at.run()
    assert not at.tabs  # locked until the password is entered
    at.text_input[0].input("pw"); at.button[0].click().run()
    assert not at.exception and len(at.tabs) == 6

    # score the one scheduled game through the UI
    game_picker = next(s for s in at.selectbox if s.label == "Scheduled game")
    game_picker.select(game_picker.options[1]).run()
    next(b for b in at.button if b.label == "Apply result").click().run()
    assert not at.exception

    saved = FakeSupabase.rows
    assert len(saved["results"]) == 1 and saved["results"][0]["teams"] == ["Alpha", "Beta"]
    ratings = {p["name"]: p["rating"] for p in saved["players"]}
    assert ratings["A1"] > 1500 > ratings["B1"]
