"""
Scans the media drive the same way main.py does, and provides the
per-title enrichment features (poster, rating, watch time, episode audit)
backed by OMDb / IMDb data.
"""

import os
import re
import urllib.request
from pathlib import Path

import settings
import omdb_client

VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".flv", ".webm", ".mpg", ".mpeg", ".ts"}

# Matches SxxExx / 1x02 / "Episode 3" style names to detect which episodes exist.
_EP_PATTERNS = [
    re.compile(r"s(\d{1,2})[ ._-]*e(\d{1,3})", re.I),
    re.compile(r"(\d{1,2})x(\d{1,3})"),
]


def _is_listed(name):
    return (
        not name.startswith(tuple(settings.blacklisted_starting_characters))
        and name not in settings.blacklisted_directories
    )


def scan_titles():
    """
    Yield (category, title, title_path) for every title on the drive,
    honouring the same blacklist rules as the GUI.
    """
    root = settings.media_path
    if not (os.path.exists(root) and os.path.isdir(root)):
        return
    for category in sorted(os.listdir(root)):
        cat_path = os.path.join(root, category)
        if not (os.path.isdir(cat_path) and _is_listed(category)):
            continue
        for title in sorted(os.listdir(cat_path)):
            title_path = os.path.join(cat_path, title)
            if os.path.isdir(title_path) and _is_listed(title):
                yield category, title, title_path


def video_files(title_path):
    """All video files under a title folder, recursively."""
    out = []
    for dirpath, _dirs, files in os.walk(title_path):
        for f in files:
            if Path(f).suffix.lower() in VIDEO_EXTS:
                out.append(os.path.join(dirpath, f))
    return out


def local_episodes(title_path):
    """
    Detect which (season, episode) numbers exist on disk based on filenames.
    Returns a set of (season, episode) tuples.
    """
    found = set()
    for path in video_files(title_path):
        name = os.path.basename(path)
        for pat in _EP_PATTERNS:
            m = pat.search(name)
            if m:
                found.add((int(m.group(1)), int(m.group(2))))
                break
    return found


# ----- Feature 6: poster from IMDb -------------------------------------------

def download_poster(title, info=None):
    """
    Download the IMDb poster for `title` into settings.poster_path/<title>.jpg.
    Returns the saved path, or None if unavailable. Skips if already present.
    """
    dest = Path(settings.poster_path) / f"{title}.jpg"
    if dest.exists():
        return dest
    if info is None:
        info = omdb_client.lookup_title(title)
    url = info.get("Poster", "")
    if not url or url == "N/A":
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)
    return dest


# ----- Feature 4: rating -----------------------------------------------------

def get_rating(info):
    r = info.get("imdbRating", "N/A")
    return r if r and r != "N/A" else None


# ----- Feature 5: watch time -------------------------------------------------

def parse_runtime_minutes(info):
    """OMDb runtime looks like '22 min'. Returns int minutes or None."""
    m = re.search(r"(\d+)", info.get("Runtime", "") or "")
    return int(m.group(1)) if m else None


def total_watch_minutes(info, title_path):
    """
    Estimate total watch time. For a movie, that's its runtime. For a series,
    it's per-episode runtime x number of local episode files.
    """
    per = parse_runtime_minutes(info)
    if per is None:
        return None
    if info.get("Type") == "series":
        count = len(video_files(title_path))
        return per * count if count else None
    return per


def format_duration(minutes):
    if minutes is None:
        return "unknown"
    h, m = divmod(int(minutes), 60)
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


# ----- Features 1-3: episode list + missing audit ----------------------------

def episode_audit(info, title_path):
    """
    For a series: pull the full episode list from IMDb (Feature 1) and compare
    against the drive by TOTAL COUNT (Feature 2), flagging how many appear to be
    missing (Feature 3).

    Count-based comparison is used deliberately: many libraries number seasons
    differently from IMDb (e.g. American Dad's production vs aired ordering), so
    exact SxxExx matching produces false "missing" hits. Counting total video
    files vs total IMDb episodes is robust to that renumbering.

    Returns dict with imdb_total / on_disk / missing_count, or None for non-series.
    """
    if info.get("Type") != "series":
        return None
    total_seasons = info.get("totalSeasons", "0")
    if not total_seasons or total_seasons == "N/A":
        return None

    imdb_eps = omdb_client.get_all_episodes(info["imdbID"], total_seasons)
    # Exclude "episode 0" specials so counts line up with typical rips.
    imdb_total = len([e for e in imdb_eps if e["episode"] > 0])
    on_disk = len(video_files(title_path))
    missing_count = max(0, imdb_total - on_disk)
    return {
        "imdb_total": imdb_total,
        "on_disk": on_disk,
        "missing_count": missing_count,
        "complete": missing_count == 0,
        "episodes": imdb_eps,
    }
