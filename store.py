"""Where the league's data lives.

Documents are small JSON values keyed by name (players, results, teams, season,
contacts). Locally they're files under data/; when Supabase credentials are
present in the Streamlit secrets (or the SUPABASE_URL / SUPABASE_KEY environment
variables) they live in one Postgres table instead, so every viewer of the
published app sees and edits the same data.

Supabase setup (SQL editor):
    create table league_kv (key text primary key, value jsonb not null);
    alter table league_kv enable row level security;   -- no policies: only the service key can read/write
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

DOCUMENTS = ("players", "results", "teams", "season", "contacts")
DEFAULTS: dict[str, Any] = {"players": [], "results": [], "teams": {}, "season": [], "contacts": []}
TABLE = "league_kv"


class LocalStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.description = f"local files in {data_dir.name}/"

    def get_all(self) -> dict[str, Any]:
        out = {}
        for name in DOCUMENTS:
            path = self.data_dir / f"{name}.json"
            out[name] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else DEFAULTS[name]
        return out

    def get(self, name: str) -> Any:
        return self.get_all()[name]

    def put(self, name: str, value: Any) -> None:
        self.data_dir.mkdir(exist_ok=True)
        path = self.data_dir / f"{name}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(value, indent=2), encoding="utf-8")
        tmp.replace(path)


class SupabaseStore:
    def __init__(self, url: str, key: str, timeout: float = 15):
        self.endpoint = f"{url.rstrip('/')}/rest/v1/{TABLE}"
        self.headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        self.timeout = timeout
        self.description = "Supabase database"

    def get_all(self) -> dict[str, Any]:
        response = requests.get(self.endpoint, params={"select": "key,value"}, headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        rows = {row["key"]: row["value"] for row in response.json()}
        return {name: rows.get(name, DEFAULTS[name]) for name in DOCUMENTS}

    def get(self, name: str) -> Any:
        response = requests.get(
            self.endpoint, params={"select": "value", "key": f"eq.{name}"}, headers=self.headers, timeout=self.timeout
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0]["value"] if rows else DEFAULTS[name]

    def put(self, name: str, value: Any) -> None:
        response = requests.post(
            self.endpoint,
            params={"on_conflict": "key"},
            headers={**self.headers, "Prefer": "resolution=merge-duplicates,return=minimal", "Content-Type": "application/json"},
            data=json.dumps({"key": name, "value": value}),
            timeout=self.timeout,
        )
        response.raise_for_status()


def _secret(name: str) -> str | None:
    try:
        import streamlit as st

        section = st.secrets.get("supabase")
        if section and section.get(name):
            return str(section[name])
    except Exception:  # no secrets file
        pass
    return os.environ.get(f"SUPABASE_{name.upper()}") or None


def get_store(data_dir: Path) -> LocalStore | SupabaseStore:
    url, key = _secret("url"), _secret("key")
    if url and key:
        return SupabaseStore(url, key)
    return LocalStore(data_dir)
