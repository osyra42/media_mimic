# Media Mimic

A desktop launcher for your local media library. Browse titles as theater-style
cards enriched with IMDb data (via OMDb), then hand playback off to VLC.

## Run

Double-click `zzz_launcher.bat`. It checks the venv, Python version, and
dependencies, then starts the app windowless.

## First-time setup

```
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

Copy `settings.py.example` to `settings.py` and set `media_path`, and your OMDb
API key (free at https://www.omdbapi.com/apikey.aspx).

## Usage

- **Search** — filter titles from the bar at the top.
- **Click a card** — opens the detail view with a Play button.
- **⚙ Settings** — edit settings, open the Collection Tool, and fetch online
  data (posters, ratings, watch time, episodes).

Playback requires VLC to be open.

## Layout

- `main.py` — the app
- `core/` — library scan, OMDb client, settings I/O
- `assets/` — icon, default poster
- `posters/`, `_cache/` — downloaded posters and OMDb cache
