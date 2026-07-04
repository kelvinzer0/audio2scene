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
from datetime import datetime, timezone
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
        "User-Agent": "Mozilla/5.0",
    })
    
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    
    return data


def parse_music_list(api_response):
    """Parse API response into clean list of trending tracks.
    
    API response structure:
    {
      "data": {
        "stats": [
          {
            "music": {
              "title": "...",
              "url": "https://v77.tiktokcdn-eu.com/...",  # direct MP3 stream URL
              "creator": "...",
              "cover": "...",
              "duration": 58,
              "reposts": 1400000,
              "musicUrl": "https://www.tiktok.com/music/...",
              "downloadLink": "https://audio-ssl.itunes.apple.com/...",
              "recognitionTitle": "Se Fue",
              "recognitionAuthor": "El Trono de Mexico",
            },
            "calculations": { "plays": ..., "likes": ... }
          }
        ]
      }
    }
    """
    tracks = []
    
    # Navigate: data.stats[].music
    data = api_response.get("data", {})
    stats = data.get("stats", [])
    
    for stat in stats:
        music = stat.get("music")
        if not music or not isinstance(music, dict):
            continue
        
        calc = stat.get("calculations")
        if not calc or not isinstance(calc, dict):
            calc = {}
        
        track = {
            "title": music.get("recognitionTitle") or music.get("title", "Unknown"),
            "original_title": music.get("title", ""),
            "artist": music.get("recognitionAuthor") or music.get("creator", "Unknown"),
            "creator": music.get("creator", ""),
            "play_url": music.get("url", ""),  # TikTok CDN direct MP3 stream
            "tiktok_url": music.get("musicUrl", ""),
            "download_url": music.get("downloadLink", ""),
            "cover": music.get("cover", ""),
            "duration": music.get("duration", 0),
            "likes": calc.get("likes", music.get("reposts", 0)),
            "plays": calc.get("plays", 0),
            "position": stat.get("positionInChart", 0),
            "id": music.get("id", ""),
        }
        
        # Prefer play_url (TikTok CDN), fallback to download_url (Apple preview)
        if not track["play_url"] and track["download_url"]:
            track["play_url"] = track["download_url"]
        
        # Skip tracks without any playable URL
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
            "fetched_at": datetime.now(timezone.utc).isoformat(),
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
