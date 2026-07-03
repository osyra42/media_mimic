"""
Shared OMDb API client for Media Mimic.

OMDb (https://www.omdbapi.com/) exposes real IMDb data: ratings, runtime,
per-season episode lists, and poster URLs. It's the single source that covers
all six features from the project notes.

Responses are cached to a local JSON file so repeated runs don't burn the
free-tier 1000-requests/day limit.

Get a free key at https://www.omdbapi.com/apikey.aspx and put it in settings.py:
    omdb_api_key = "your-key-here"
"""

import json
import urllib.parse
import urllib.request

import settings
from paths import project_path

API_URL = "https://www.omdbapi.com/"
CACHE_PATH = project_path("_cache") / "omdb_cache.json"


class OMDbError(Exception):
    pass


def _api_key():
    key = getattr(settings, "omdb_api_key", "").strip()
    if not key:
        raise OMDbError(
            "No OMDb API key set. Get a free key at "
            "https://www.omdbapi.com/apikey.aspx and add "
            'omdb_api_key = "..." to settings.py'
        )
    return key


def _load_cache():
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


_cache = _load_cache()


def _request(params, cache_key, force=False):
    """Make a cached OMDb request. Returns the parsed JSON dict.
    When `force` is True, bypass the cached value and re-fetch from the API
    (the fresh result still overwrites the cache)."""
    if not force and cache_key in _cache:
        return _cache[cache_key]

    query = dict(params)
    query["apikey"] = _api_key()
    url = API_URL + "?" + urllib.parse.urlencode(query)

    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise OMDbError(f"Network error contacting OMDb: {e}")

    if data.get("Response") == "False":
        # Don't cache "not found" so a later fix/retry can succeed.
        error = data.get("Error", "Unknown OMDb error")
        raise OMDbError(error)

    _cache[cache_key] = data
    _save_cache(_cache)
    return data


def clean_title(name):
    """
    Strip common release-folder cruft so a directory name matches IMDb.
    e.g. 'American Dad (2005) [1080p]' -> 'American Dad'

    If the raw folder name has an entry in title_overrides, that exact query
    string is used instead (handles apostrophes, '&', and alternate titles
    that folder names can't represent).
    """
    import re

    try:
        import title_overrides
        override = title_overrides.OVERRIDES.get(name.strip())
        if override:
            return override
    except ImportError:
        pass

    name = re.sub(r"\[[^\]]*\]", "", name)          # [1080p], [DUB]
    name = re.sub(r"\([^)]*\)", "", name)            # (2005)
    name = re.sub(r"\b(720p|1080p|2160p|x264|x265|bluray|web-?dl)\b", "", name, flags=re.I)
    name = name.replace(".", " ").replace("_", " ")
    return " ".join(name.split()).strip()


def lookup_title(name, kind=None, force=False):
    """
    Look up a movie/series by title name. Returns the OMDb detail dict
    (includes imdbID, imdbRating, Runtime, Poster, Type, totalSeasons, ...).
    `kind` can be 'movie' or 'series' to disambiguate.
    `force` re-fetches from the API even if a cached value exists.
    """
    title = clean_title(name)
    params = {"t": title, "plot": "short"}
    if kind:
        params["type"] = kind
    cache_key = f"t::{title}::{kind or ''}"
    return _request(params, cache_key, force=force)


def cached_info(name, kind=None):
    """Return the cached OMDb dict for `name` WITHOUT any network call, or
    None if it hasn't been fetched yet. Used by the GUI to render cards from
    already-fetched data."""
    title = clean_title(name)
    return _cache.get(f"t::{title}::{kind or ''}")


def get_season(imdb_id, season, cached_only=False):
    """Return the episode list for one season of a series. With cached_only,
    return None instead of making a network call when it isn't cached."""
    cache_key = f"s::{imdb_id}::{season}"
    if cached_only:
        return _cache.get(cache_key)
    params = {"i": imdb_id, "Season": str(season)}
    return _request(params, cache_key)


def get_all_episodes(imdb_id, total_seasons, cached_only=False):
    """
    Return a flat list of episodes across all seasons:
    [{'season': 1, 'episode': 1, 'title': '...', 'imdbID': '...'}, ...]
    With cached_only, only already-cached seasons contribute (no network).
    """
    episodes = []
    for s in range(1, int(total_seasons) + 1):
        try:
            data = get_season(imdb_id, s, cached_only=cached_only)
        except OMDbError:
            continue
        if data is None:
            continue
        for ep in data.get("Episodes", []):
            episodes.append(
                {
                    "season": s,
                    "episode": int(ep.get("Episode", 0) or 0),
                    "title": ep.get("Title", ""),
                    "imdbID": ep.get("imdbID", ""),
                    "rating": ep.get("imdbRating", ""),
                }
            )
    return episodes
