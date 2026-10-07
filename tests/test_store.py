import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from store import DEFAULTS, LocalStore, SupabaseStore


def test_local_store_roundtrip_and_defaults(tmp_path):
    store = LocalStore(tmp_path / "data")
    assert store.get_all() == DEFAULTS
    store.put("results", [{"a": 1}])
    assert store.get("results") == [{"a": 1}]
    assert store.get("teams") == {}


class FakeSupabase(BaseHTTPRequestHandler):
    rows: dict = {}
    seen_headers: dict = {}

    def log_message(self, *args):
        pass

    def _send(self, payload, code=200):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        FakeSupabase.seen_headers = dict(self.headers)
        url = urlparse(self.path)
        assert url.path == "/rest/v1/league_kv"
        query = parse_qs(url.query)
        if "key" in query:
            name = query["key"][0].removeprefix("eq.")
            return self._send([{"value": self.rows[name]}] if name in self.rows else [])
        self._send([{"key": k, "value": v} for k, v in self.rows.items()])

    def do_POST(self):
        FakeSupabase.seen_headers = dict(self.headers)
        assert "on_conflict=key" in self.path
        assert "merge-duplicates" in self.headers["Prefer"]
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.rows[body["key"]] = body["value"]
        self._send([], 201)


@pytest.fixture
def supabase():
    FakeSupabase.rows = {}
    server = HTTPServer(("127.0.0.1", 0), FakeSupabase)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield SupabaseStore(f"http://127.0.0.1:{server.server_port}", "service-key")
    server.shutdown()


def test_supabase_store_roundtrip(supabase):
    assert supabase.get_all() == DEFAULTS
    supabase.put("teams", {"Catalin": ["A", "B"]})
    supabase.put("teams", {"Catalin": ["A", "B", "C"]})  # upsert replaces
    assert supabase.get("teams") == {"Catalin": ["A", "B", "C"]}
    assert supabase.get("results") == []
    assert supabase.get_all()["teams"] == {"Catalin": ["A", "B", "C"]}
    assert FakeSupabase.seen_headers["apikey"] == "service-key"
    assert FakeSupabase.seen_headers["Authorization"] == "Bearer service-key"
