# Media Mimic

A **theater-themed** media library manager and launcher for Windows. Scans your local media folders, enriches titles with IMDb data via the OMDb API, and opens your selection directly in VLC — all wrapped in a dark velvet-and-gold Qt GUI.

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![PySide6](https://img.shields.io/badge/PySide6-6.11.1-red)
![VLC](https://img.shields.io/badge/requires-VLC-green)

---

## Features

### 🔍 Smart Library Scanning
- Recursively scans categorized media folders (Movies, TV, Anime, etc.)
- Ignores blacklisted directories and hidden/system files via configurable rules in `settings.py`
- Filters titles live as you type in the search bar

### 🎬 Poster Display & Card UI
- Downloads and caches movie/series posters from IMDb
- Falls back to a default poster when an image is unavailable
- Cards display: poster, IMDb rating, year, runtime, watch-time estimate, genre, and truncated plot synopsis

### 📺 Episode Audit (TV / Anime)
- Pulls the full episode list per season from IMDb
- Compares against video files detected on disk
- Shows a completeness badge per title:
  - ✔ **Complete** — all episodes accounted for
  - ⬆ **Upgrades available** — episodes missing from local collection
  - ✗ **No data** — not yet fetched

### ⏱️ Watch-Time Tracking
- Movies: runtime from IMDb
- TV series: per-episode runtime × number of local video files
- Displayed in human-friendly format (`2h 15m`)

### 🚀 VLC Integration
- Detects whether VLC is running before attempting playback
- Enqueues the title's folder into the existing VLC instance (playlist-enqueue)
- Paths are configurable for both VLC and your media root

### ⚙️ Self-Contained Settings
- Edit `settings.py` through a built-in Qt modal — comments and blank lines are preserved
- Atomically rewrites only the values you change

### 🛠️ Collection Tool (Web)
- A companion HTML/JS web app (`_collection_tool/`) for tracking manual collection progress
- Persists input to `localStorage`
- Status-coded entries with copy support

### 🔊 Debug-Friendly
- Redirects `stdout`/`stderr` to `/dev/null` under `pythonw.exe` so silent failures don't crash the app
- Debug prints for VLC launch paths

---

## Architecture

```
Osyra/media_mimic/
├── main.py                 # Entry point, Qt GUI, card grid, detail panels
├── requirements.txt        # Python deps (pinned)
├── settings.py.example     # Example config — copy to settings.py
├── zen_launcher.bat        # Windows launcher: venv check, pythonw.exe, detach
├── core/
│   ├── paths.py            # Project-root-relative Path helper
│   ├── library.py          # Scan titles, posters, ratings, watch time, episode audit
│   ├── omdb_client.py      # Cached OMDb API client + clean_title()
│   ├── settings_io.py      # Read/write settings.py preserving comments
│   ├── enrich.py           # CLI enrichment runner (writes _cache/report.json)
│   └── title_overrides.py  # Folder-name → OMDb title fixes for illegal chars
├── _collection_tool/
│   ├── index.html          # Standalone web UI
│   ├── script.js           # Status-flag logic, localStorage sync
│   ├── style.css           # Layout + colors
│   ├── theme.css           # Dark theme variables
│   └── version.js          # Version constant (2026.06.08@09.00)
├── assets/
│   ├── icon.png            # App icon (PNG fallback)
│   └── icon.ico            # Windows taskbar icon
├── posters/                # Downloaded posters live here (gitignored except placeholder)
├── _cache/                 # OMDb response cache (gitignored)
└── venv/                   # Python virtual environment (gitignored)
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| GUI | PySide6 (Qt 6 for Python) |
| Threading | `QThread` + `QObject` worker pattern for non-blocking OMDb fetches |
| HTTP | `urllib` (stdlib) — zero external HTTP deps |
| Cache | Local JSON file (`_cache/omdb_cache.json`) |
| Video | `subprocess` → VLC with shell-escaped paths |
| Web tool | Vanilla HTML/CSS/JS, no build step |
| Launcher | Batch file with venv sanity checks |

---

## Getting Started

### Prerequisites

- **Python 3.9+**
- **VLC Media Player** installed at the path set in `settings.py`
- **VLC running** in the background before clicking Play (the app enqueues to the existing instance)

### 1. Clone

```bash
git clone https://github.com/KastienDevOp/media_mimic.git
cd media_mimic
```

### 2. Set Up Virtual Environment

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
```

### 3. Configure

Copy the example settings file and edit it:

```bash
cp settings.py.example settings.py
```

Edit `settings.py`:

```python
window_title = "Media Mimic"
app_icon = "icon.png"
media_path = "Z:/"                          # <-- your media root
poster_path = "posters"
default_poster = "default.jpg"
blacklisted_directories = ["$RECYCLE.BIN", "System Volume Information", "#media_mimic"]
blacklisted_starting_characters = ["_"]
omdb_api_key = "YOUR_OMDB_KEY_HERE"          # <-- free tier at omdbapi.com
```

> **Note:** `vlc_path` is hardcoded in `main.py` (`C:/Program Files/VideoLAN/VLC/vlc.exe`). Update it there if your VLC lives elsewhere, or patch the launcher to read it from `settings.py`.

### 4. First Run

Option A — launcher (recommended):
```bash
zen_launcher.bat
```

Option B — manual:
```bash
venv\Scripts\pythonw.exe main.py
```

On first launch, the app will show a splash overlay while scanning your library. Cards build in the background.

### 5. Fetch Online Data

Click **⚙ Settings** → **Fetch Online Data** to pull ratings, posters, watch times, and episode data from IMDb.

- Free OMDb tier: **1,000 requests/day**, resets at midnight UTC.
- A live countdown is shown in the fetch modal.
- Check **Force re-fetch** to bypass the local cache.

---

## Settings Reference

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `window_title` | `str` | `"Media Mimic"` | Title bar text |
| `app_icon` | `str` | `"icon.png"` | Relative path to app icon |
| `media_path` | `str` | `"Z:/"` | Root folder containing category subfolders |
| `vlc_path` | `str` | `"C:/Program Files/VideoLAN/VLC/vlc.exe"` | VLC executable |
| `poster_path` | `str` | `"posters"` | Folder for downloaded posters |
| `default_poster` | `str` | `"default.jpg"` | Fallback poster image |
| `blacklisted_directories` | `list` | see above | Folder names to skip entirely |
| `blacklisted_starting_characters` | `list` | `["_"]` | Prefixes that hide folders |
| `omdb_api_key` | `str` | `""` | OMDb API key (required for all online data) |

---

## OMDb API Notes

- **Cache first**: Every `lookup_title` and season/episode call is cached to `_cache/omdb_cache.json`. Offline browsing works for previously-fetched titles.
- **Rate limits**: The free tier is 1,000 req/day. The GUI surfaces a UTC countdown so you know exactly when you can fetch again.
- **Cache busting**: Use the **Force re-fetch** checkbox or the **⟳** button on an individual card's detail panel.

---

## CLI Enrichment

Run the full enrichment pipeline without the GUI:

```bash
python core/enrich.py
```

Process a single title (substring match):
```bash
python core/enrich.py "American Dad"
```

Outputs a JSON report to `_cache/report.json`.

---

## How Cards Work

1. `library.scan_titles()` walks `media_path/` and yields `(category, title, title_path)`.
2. `omdb_client.cached_info(title)` pulls the cached (or freshly-fetched) OMDb dict without hitting the network.
3. `library.get_rating()`, `library.total_watch_minutes()`, and `library.episode_audit()` enrich that dict.
4. Cards are `QPushButton` subclasses arranged in a `QGridLayout` per category.
5. Search filters reflow the grid live by hiding/showing individual cards and empty category headers.

---

## Troubleshooting

**"VLC Not Found"**
- Make sure VLC is running *before* you click Play.
- Verify `vlc_path` in `main.py` matches your VLC install location.

**"OMDb rejected the request"**
- You hit the 1,000 req/day ceiling. Wait for midnight UTC, or upgrade to a paid OMDb tier.
- Double-check your `omdb_api_key` in `settings.py`.

**No posters loading**
- Confirm the `posters/` folder is writable.
- Ensure `omdb_api_key` is set and you have remaining API quota.
- Check that your folder names match IMDb titles (see `title_overrides.py` for known fixes).

**Cards show "✗ No data"**
- The title hasn't been fetched yet. Open Settings → Fetch Online Data.
- If a title still shows "No data" after fetching, add an entry to `core/title_overrides.py` with the correct OMDb name.

---

## Contributing

Branches are short-lived. PRs should be scoped and self-contained.

```bash
git checkout -b feat/your-thing
# work, test, then:
git commit -am "feat: describe your change"
git push -u origin feat/your-thing
```

Open a PR against `main`.

---

## License

MIT — use it, break it, fix it however you want.
