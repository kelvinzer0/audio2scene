#!/usr/bin/env python3
"""
Fetch trending TikTok music from RapidAPI and save to data/trending-music.json.

API: tiktok-most-trending-and-viral-content.p.rapidapi.com
Free tier: 1000 requests/day

Usage:
    python3 scripts/fetch_trending_music.py
    # → writes data/trending-music.json
"""

import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

API_KEY = os.environ.get("RAPIDAPI_KEY", "")
API_HOST = "tiktok-most-trending-and-viral-content.p.rapidapi.com"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "trending-music.json"


def fetch_trending_music(sound_type="Original", sorting="likes", days=7, order="desc", artist_location="ID", category="121"):
    """Fetch trending TikTok music from RapidAPI."""
    url = (
        f"https://{API_HOST}/music"
        f"?soundType={sound_type}&sorting={sorting}&days={days}"
        f"&order={order}&artistLocation={artist_location}&category={category}"
    )
    
    req = urllib.request.Request(url, headers={
        "Content-Type": "application/json",
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": API_KEY,
    })
    
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    
    return data


def parse_music_list(api_response):
    """Parse API response into clean list of trending tracks."""
    tracks = []
    
    # API response format varies — try common keys
    items = api_response if isinstance(api_response, list) else api_response.get("data", api_response.get("results", []))
    
    for item in items:
        if not isinstance(item, dict):
            continue
        
        track = {
            "title": item.get("title") or item.get("music_title") or item.get("name", "Unknown"),
            "artist": item.get("author") or item.get("artist") or item.get("author_name", "Unknown"),
            "play_url": item.get("play_url") or item.get("music_url") or item.get("url", ""),
            "cover": item.get("cover") or item.get("cover_large") or item.get("thumbnail", ""),
            "duration": item.get("duration", 0),
            "likes": item.get("likes") or item.get("digg_count", 0),
            "plays": item.get("plays") or item.get("play_count", 0),
            "id": item.get("id") or item.get("music_id", ""),
        }
        
        # Skip tracks without play URL
        if track["play_url"]:
            tracks.append(track)
    
    return tracks


def main():
    if not API_KEY:
        print("ERROR: RAPIDAPI_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)
    
    print("=== Fetching trending TikTok music (Indonesia) ===")
    
    try:
        raw = fetch_trending_music()
        print(f"API response keys: {list(raw.keys()) if isinstance(raw, dict) else f'list of {len(raw)}'}")
        
        tracks = parse_music_list(raw)
        print(f"Parsed {len(tracks)} tracks")
        
        if not tracks:
            print("WARNING: No tracks found. Saving raw response for debugging.")
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            (OUTPUT_DIR / "trending-music-raw.json").write_text(
                json.dumps(raw, indent=2, ensure_ascii=False)
            )
            sys.exit(0)
        
        # Build output
        output = {
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "region": "ID",
            "count": len(tracks),
            "tracks": tracks,
        }
        
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
        
        print(f"\n✓ Saved {len(tracks)} tracks to {OUTPUT_FILE}")
        print(f"\nTop 5:")
        for i, t in enumerate(tracks[:5]):
            print(f"  {i+1}. {t['title']} — {t['artist']} ({t['likes']:,} likes)")
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
