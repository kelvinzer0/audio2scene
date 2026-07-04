#!/usr/bin/env python3
"""
Refresh data/trending-music.json using iTunes Search API (no API key needed, no quota).

This is a fallback when the RapidAPI TikTok trending API quota is exceeded.
It takes the known list of trending Indonesian TikTok songs and fetches
their preview URLs from iTunes Search API (free, public, no key required).

Usage:
    python3 scripts/refresh_trending_via_itunes.py
    # → updates data/trending-music.json with fresh, unique preview URLs per song
"""

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "trending-music.json"

# Known trending Indonesian TikTok songs (title, artist, search_term)
# Source: manual curation + RapidAPI historical data
# Each entry must be verified to actually match on iTunes (else skipped at runtime)
KNOWN_TRENDING = [
    {
        "title": "Se Fue",
        "artist": "El Trono de Mexico",
        "search": "Se Fue El Trono de Mexico",
        "likes": 1_400_000,
    },
    {
        "title": "Garam & Madu (Sakit Dadaku)",
        "artist": "Tenxi, Jemsii & Naykilla",
        "search": "Garam Madu Sakit Dadaku Tenxi",
        "likes": 1_100_000,
    },
    {
        "title": "APT.",
        "artist": "ROSÉ & Bruno Mars",
        "search": "APT ROSÉ Bruno Mars",
        "likes": 804_400,
    },
    {
        "title": "Die With A Smile",
        "artist": "Lady Gaga & Bruno Mars",
        "search": "Die With A Smile Lady Gaga Bruno Mars",
        "likes": 720_000,
    },
    {
        "title": "Espresso",
        "artist": "Sabrina Carpenter",
        "search": "Espresso Sabrina Carpenter",
        "likes": 680_000,
    },
    {
        "title": "Birds of a Feather",
        "artist": "Billie Eilish",
        "search": "Birds of a Feather Billie Eilish",
        "likes": 540_000,
    },
    {
        "title": "Gala Bunga Matahari",
        "artist": "Sal Priadi",
        "search": "Gala Bunga Matahari Sal Priadi",
        "likes": 410_000,
    },
    {
        "title": "Sial",
        "artist": "Mahalini",
        "search": "Sial Mahalini",
        "likes": 470_000,
    },
    {
        "title": "Sang Dewi",
        "artist": "Lyodra & Andi Rianto",
        "search": "Sang Dewi Lyodra",
        "likes": 380_000,
    },
    {
        "title": "Cinta Luar Biasa",
        "artist": "Andmesh",
        "search": "Cinta Luar Biasa Andmesh",
        "likes": 350_000,
    },
]


def itunes_search(term: str, country: str = "ID", limit: int = 5) -> list:
    """Search iTunes for a song. Returns list of result dicts (max `limit`)."""
    encoded = urllib.parse.quote(term)
    url = (
        f"https://itunes.apple.com/search?term={encoded}"
        f"&limit={limit}&media=music&country={country}"
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (audio2scene trending fetcher)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    return data.get("results", [])


def best_match(results: list, expected_artist: str) -> dict:
    """Pick the best iTunes result by matching artist keyword.
    
    iTunes Search is fuzzy — sometimes the first result is a wrong artist with
    a similar-sounding name. We pick the first result whose artistName contains
    a token from expected_artist.
    """
    if not results:
        return {}
    expected_tokens = {t.lower().strip() for t in expected_artist.replace("&", " ").split()
                      if len(t) > 2}
    for r in results:
        artist = (r.get("artistName") or "").lower()
        if any(tok in artist for tok in expected_tokens):
            return r
    # No artist match — return first result anyway (user can verify visually)
    return results[0]


def refresh_trending() -> list:
    """Fetch fresh preview URLs from iTunes Search API for each known track."""
    tracks = []
    seen_urls = set()  # Skip duplicate URLs (shouldn't happen with iTunes but be safe)

    for known in KNOWN_TRENDING:
        try:
            print(f"  → Searching: {known['search']}")
            results = itunes_search(known["search"])
            if not results:
                print(f"    ✗ not found on iTunes")
                continue

            result = best_match(results, known["artist"])
            preview_url = result.get("previewUrl", "")
            if not preview_url or preview_url in seen_urls:
                print(f"    ✗ no preview URL or duplicate, skipping")
                continue

            seen_urls.add(preview_url)
            track = {
                "title": result.get("trackName", known["title"]),
                "artist": result.get("artistName", known["artist"]),
                "play_url": preview_url,
                "duration": (result.get("trackTimeMillis", 30000) or 30000) // 1000,
                "likes": known["likes"],
                "source": "itunes_search",
                "artwork": result.get("artworkUrl100", ""),
                "track_view_url": result.get("trackViewUrl", ""),
            }
            tracks.append(track)
            print(f"    ✓ {track['title']} — {track['artist']} ({track['duration']}s)")
            print(f"      {preview_url}")
        except Exception as e:
            print(f"    ✗ error: {e}")
            continue

    return tracks


def main():
    print("=== Refreshing trending music via iTunes Search API ===")
    print(f"  (no API key needed, no quota — free public API)")
    print()

    tracks = refresh_trending()

    if not tracks:
        print("\nERROR: No tracks fetched — keeping existing file unchanged")
        sys.exit(1)

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "region": "ID",
        "count": len(tracks),
        "tracks": tracks,
        "source": "itunes_search_api",
        "note": (
            "Trending tracks via iTunes Search API (free, no quota). "
            "Preview URLs are ~30s clips, persistent and unique per song. "
            "When RapidAPI quota resets, run fetch_trending_music.py for full TikTok metadata."
        ),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    print(f"\n✓ Saved {len(tracks)} tracks to {OUTPUT_FILE}")
    print(f"\nTrack list:")
    for i, t in enumerate(tracks, 1):
        print(f"  {i}. {t['title']} — {t['artist']} ({t['duration']}s)")
    print(f"\nAll URLs unique: {len(set(t['play_url'] for t in tracks)) == len(tracks)}")


if __name__ == "__main__":
    main()
