"""Copy this machine's league data (data/*.json) into the shared Supabase database.

Usage: python3 push_data.py [--force]

Needs the [supabase] url/key in .streamlit/secrets.toml (or SUPABASE_URL /
SUPABASE_KEY). Refuses to overwrite a database that already has results unless
--force, so a stray re-run can't wipe live scores.
"""
from __future__ import annotations

import sys
from pathlib import Path

from store import DOCUMENTS, LocalStore, SupabaseStore, get_store

DATA_DIR = Path(__file__).resolve().parent / "data"


def main(force: bool) -> None:
    remote = get_store(DATA_DIR)
    if not isinstance(remote, SupabaseStore):
        sys.exit("No Supabase credentials found (see .streamlit/secrets.example.toml).")
    if remote.get("results") and not force:
        sys.exit("The shared database already has results. Re-run with --force to overwrite everything.")
    local = LocalStore(DATA_DIR).get_all()
    for name in DOCUMENTS:
        remote.put(name, local[name])
        print(f"pushed {name}")
    print("Done. The published app now shows this data.")


if __name__ == "__main__":
    main("--force" in sys.argv[1:])
