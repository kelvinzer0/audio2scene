#!/usr/bin/env python3
"""
Parse GitHub issue body (from video-generator template) into data.json.

Usage:
    python3 scripts/issue_to_datajson.py --issue-body issue.txt --output data.json

The issue template uses GitHub issue forms (YAML), so the body is structured
as markdown with labeled sections. This script extracts field values.
"""

import argparse
import json
import re
import sys
from pathlib import Path


def parse_issue_body(body: str) -> dict:
    """Parse GitHub issue form body into data.json dict."""
    data = {}

    # GitHub issue forms format: ### Field Label\n\nvalue\n\n
    fields = {
        "music": r"###\s*🎵 Music URL.*?\n\n(.+?)(?:\n\n|\Z)",
        "screen": r"###\s*📐 Screen Resolution.*?\n\n(.+?)(?:\n\n|\Z)",
        "duration": r"###\s*⏱️ Duration.*?\n\n(.+?)(?:\n\n|\Z)",
        "font": r"###\s*🔤 Font.*?\n\n(.+?)(?:\n\n|\Z)",
        "logo": r"###\s*🏢 Logo URL.*?\n\n(.+?)(?:\n\n|\Z)",
        "symbol": r"###\s*🔖 Symbol.*?\n\n(.+?)(?:\n\n|\Z)",
        "text": r"###\s*✏️ Text Scenes.*?\n\n([\s\S]+?)(?:\n\n###|\Z)",
        "videos": r"###\s*🎥 Video URLs.*?\n\n([\s\S]+?)(?:\n\n###|\Z)",
        "images": r"###\s*🖼️ Image URLs.*?\n\n([\s\S]+?)(?:\n\n###|\Z)",
        "quality": r"###\s*🎯 Render Quality.*?\n\n(.+?)(?:\n\n|\Z)",
    }

    quality_scale = {
        "Fast": "0.25",
        "Standard": "0.5",
        "HQ": "1.0",
    }

    for key, pattern in fields.items():
        match = re.search(pattern, body, re.DOTALL)
        if match:
            value = match.group(1).strip()
            if not value or value == "_No response_":
                continue

            if key in ("text", "videos", "images"):
                # Multi-line: split by newline, filter empty
                items = []
                for line in value.split("\n"):
                    line = line.strip()
                    if not line or line.startswith("#") or line == "_No response_":
                        continue
                    # Extract URL from <img src="..."> tags (GitHub pastes images as HTML)
                    img_match = re.search(r'src="(https?://[^"]+)"', line)
                    if img_match:
                        items.append(img_match.group(1))
                    elif line.startswith("http"):
                        items.append(line)
                    elif key == "text":
                        items.append(line)
                if key == "text":
                    data["text"] = items
                elif key == "videos":
                    data["videos"] = items
                elif key == "images":
                    data["images"] = items
            elif key == "quality":
                # Extract scale from quality dropdown
                for q, s in quality_scale.items():
                    if q in value:
                        data["_render_scale"] = s
                        break
            else:
                data[key] = value

    return data


def main():
    parser = argparse.ArgumentParser(description="Parse GitHub issue body into data.json")
    parser.add_argument("--issue-body", required=True, help="Path to file containing issue body text")
    parser.add_argument("--output", "-o", default="data.json", help="Output data.json path")
    args = parser.parse_args()

    body = Path(args.issue_body).read_text()
    data = parse_issue_body(body)

    # Remove internal fields
    render_scale = data.pop("_render_scale", "0.5")

    # Validate required fields
    if "music" not in data:
        print("ERROR: music URL is required", file=sys.stderr)
        sys.exit(1)
    if "text" not in data or not data["text"]:
        print("ERROR: text scenes are required", file=sys.stderr)
        sys.exit(1)

    # Write data.json
    Path(args.output).write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"✓ Wrote {args.output}")
    print(f"  music: {data.get('music', 'N/A')[:60]}...")
    print(f"  text: {len(data.get('text', []))} scenes")
    print(f"  videos: {len(data.get('videos', []))}")
    print(f"  images: {len(data.get('images', []))}")
    print(f"  logo: {'yes' if data.get('logo') else 'no'}")
    print(f"  symbol: {'yes' if data.get('symbol') else 'no'}")
    print(f"  render_scale: {render_scale}")

    # Write render scale to separate file for CI
    Path(".render-scale").write_text(render_scale)
    print(f"✓ Wrote .render-scale = {render_scale}")


if __name__ == "__main__":
    main()
