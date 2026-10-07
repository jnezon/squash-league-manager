# Squash House League Manager

Streamlit app for the Tuesday doubles team league: builds the season schedule
(every team plays every other team equally), rotates partners/opponents/time
slots using player history and ratings, records scores and subs, and keeps
weekly team standings. Password-protected.

## Run on a laptop (no setup beyond Python)

```bash
pip install -r requirements.txt
./start.sh          # then open http://127.0.0.1:8501
```

Data lives in `data/*.json` (git-ignored: it holds names and emails). Restart
`start.sh` after changing code - Streamlit does not reload imported modules.

First-time data load from the league spreadsheet:

```bash
python3 import_contacts.py "Tuesday Doubles Team League - Fall 2026.xlsx"   # teams, roster, contacts
python3 generate_season.py                                                  # full Tuesday calendar
```

## Publish a shared site (Streamlit Community Cloud + Supabase)

1. **Supabase** (free): create a project, open the SQL editor and run
   ```sql
   create table league_kv (key text primary key, value jsonb not null);
   alter table league_kv enable row level security;
   ```
2. Put the project URL and the `service_role` key in `.streamlit/secrets.toml`
   (see `.streamlit/secrets.example.toml`), then upload your data once:
   `python3 push_data.py`
3. Push this repo to GitHub (use a **private** repo) and create the app on
   share.streamlit.io pointing at `app.py`.
4. In the app's **Settings > Secrets**, paste the same `password` and
   `[supabase]` values as your local secrets file.

With Supabase credentials present the app reads/writes the shared database;
without them it uses local files. The password is never in the source.

## Tests

```bash
pip install pytest && python3 -m pytest
```

## Layout

- `app.py` UI · `auth.py` password gate · `store.py` local/Supabase storage
- `season.py` season engine + standings · `league_logic.py` ratings, subs, emails
- `import_contacts.py`, `generate_season.py`, `push_data.py` data tools
