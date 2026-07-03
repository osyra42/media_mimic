"""
Media Mimic enrichment tool.

Runs all six IMDb features from the project notes over your whole library:
  1. Pull the full episode list from IMDb for each show
  2. Compare against what's on the hard drive
  3. Flag any missing episodes
  4. Record IMDb ratings per title
  5. Estimate watch time per title
  6. Download the poster image from IMDb

Usage:
    python enrich.py            # process everything, write _cache/report.json
    python enrich.py "American Dad"   # process a single title (substring match)
"""

import json
import sys
from pathlib import Path

# Allow running as `python core/enrich.py` from anywhere: put both this dir
# (for sibling modules) and the project root (for settings.py) on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import library
import omdb_client
from paths import project_path

REPORT_PATH = project_path("_cache") / "report.json"


def process(category, title, title_path):
    row = {"category": category, "title": title}
    try:
        info = omdb_client.lookup_title(title)
    except omdb_client.OMDbError as e:
        row["error"] = str(e)
        print(f"  ! {title}: {e}")
        return row

    row["imdb_id"] = info.get("imdbID")
    row["type"] = info.get("Type")

    # Feature 4: rating
    row["rating"] = library.get_rating(info)

    # Feature 5: watch time
    minutes = library.total_watch_minutes(info, title_path)
    row["watch_minutes"] = minutes
    row["watch_time"] = library.format_duration(minutes)

    # Feature 6: poster
    try:
        poster = library.download_poster(title, info)
        row["poster"] = str(poster) if poster else None
    except Exception as e:
        row["poster_error"] = str(e)

    # Features 1-3: episode audit
    audit = library.episode_audit(info, title_path)
    if audit is not None:
        row["episodes_total"] = audit["imdb_total"]
        row["episodes_on_disk"] = audit["on_disk"]
        row["episodes_missing"] = audit["missing_count"]
        row["complete"] = audit["complete"]

    _print_row(row)
    return row


def _print_row(row):
    line = f"  {row['title']}  [{row.get('type', '?')}]  rating={row.get('rating') or '-'}  watch={row.get('watch_time')}"
    print(line)
    if "episodes_total" in row:
        flag = "COMPLETE" if row["complete"] else f"{row['episodes_missing']} MISSING"
        print(f"      episodes: {row['episodes_on_disk']}/{row['episodes_total']} on disk  ->  {flag}")


def main():
    filter_term = sys.argv[1].lower() if len(sys.argv) > 1 else None
    results = []
    for category, title, title_path in library.scan_titles():
        if filter_term and filter_term not in title.lower():
            continue
        print(f"[{category}] {title}")
        results.append(process(category, title, title_path))

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nReport written to {REPORT_PATH}  ({len(results)} titles)")


if __name__ == "__main__":
    main()
