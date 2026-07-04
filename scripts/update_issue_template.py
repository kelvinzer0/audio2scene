#!/usr/bin/env python3
"""
Update issue template YAML dengan trending music dari data/trending-music.json.

CI workflow akan run script ini setelah fetch trending, lalu commit perubahan.
User akan langsung lihat trending tracks sebagai dropdown options di issue form.
"""

import json
import re
from pathlib import Path

TEMPLATE_FILE = Path(__file__).resolve().parent.parent / ".github" / "ISSUE_TEMPLATE" / "video-generator.yml"
TRENDING_FILE = Path(__file__).resolve().parent.parent / "data" / "trending-music.json"


def update_template():
    if not TRENDING_FILE.exists():
        print("  [warn] trending-music.json not found — skipping template update")
        return False

    if not TEMPLATE_FILE.exists():
        print("  [warn] video-generator.yml not found — skipping template update")
        return False

    trending = json.loads(TRENDING_FILE.read_text())
    tracks = trending.get("tracks", [])

    if not tracks:
        print("  [warn] no tracks in trending-music.json — skipping template update")
        return False

    # Build dropdown options
    options = ["        - 🚫 Tidak pakai trending — saya punya URL sendiri"]
    for i, track in enumerate(tracks[:15]):  # max 15 tracks
        title = track.get("title", "Unknown")[:50]
        artist = track.get("artist", "Unknown")[:30]
        likes = track.get("likes", 0)
        likes_str = f"{likes/1_000_000:.1f}M" if likes >= 1_000_000 else f"{likes/1_000:.0f}K"
        options.append(f'        - {i+1}. {title} — {artist} ({likes_str})')

    # Read current template
    content = TEMPLATE_FILE.read_text()

    # Find and replace the trending_music dropdown options section
    pattern = r'(id: trending_music.*?description:.*?options:\n)([\s\S]*?)(\n    validations:)'
    
    new_options = "\n".join(options) + "\n"
    new_content = re.sub(pattern, r'\1' + new_options + r'\3', content, count=1, flags=re.DOTALL)

    if new_content == content:
        print("  [warn] could not find options section to replace — skipping")
        return False

    # Also update description with fetch date
    fetch_date = trending.get("fetched_at", "unknown")[:10]
    new_content = new_content.replace(
        "Pilih dari lagu TikTok trending Indonesia (updated daily by CI).",
        f"Pilih dari lagu TikTok trending Indonesia (updated: {fetch_date})."
    )

    TEMPLATE_FILE.write_text(new_content)
    print(f"  ✓ Updated issue template with {len(tracks[:15])} trending tracks")
    print(f"  ✓ Options:")
    for opt in options[1:4]:
        print(f"    {opt.strip()}")
    if len(options) > 4:
        print(f"    ... and {len(options) - 4} more")
    return True


if __name__ == "__main__":
    print("=== Updating issue template with trending music ===")
    updated = update_template()
    if updated:
        print("\n✓ Issue template updated — users will see trending tracks in dropdown")
    else:
        print("\n✗ Template not updated")
