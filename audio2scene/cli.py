#!/usr/bin/env python3
"""
audio2scene.cli
===============

Command-line entry point.

Examples:
    audio2scene music.mp3
    audio2scene music.mp3 --json
    audio2scene music.mp3 --csv
    audio2scene music.mp3 --txt
    audio2scene music.mp3 --pretty
    audio2scene music.mp3 -o labels.json
    audio2scene *.mp3            # batch processing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from . import __version__, detect
from .timeline import (
    segments_to_csv,
    segments_to_json,
    segments_to_pretty,
    segments_to_txt,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="audio2scene",
        description="AI-powered structural labeling for instrumental music.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  audio2scene music.mp3                 # default: pretty timeline to stdout
  audio2scene music.mp3 --json          # JSON output
  audio2scene music.mp3 --csv           # CSV output
  audio2scene music.mp3 --txt           # TXT (MM:SS Label) output
  audio2scene music.mp3 --pretty        # pretty timeline (default)
  audio2scene music.mp3 -o labels.json  # write to file
  audio2scene *.mp3                     # batch processing
""",
    )
    p.add_argument("input", nargs="+", help="Path(s) to audio file(s). Supports MP3/WAV/FLAC/OGG/AAC/M4A.")
    p.add_argument("--format", choices=["json", "csv", "txt", "pretty"], default="pretty",
                   help="Output format (default: pretty)")
    p.add_argument("--json", action="store_const", const="json", dest="format", help="Shorthand for --format json")
    p.add_argument("--csv", action="store_const", const="csv", dest="format", help="Shorthand for --format csv")
    p.add_argument("--txt", action="store_const", const="txt", dest="format", help="Shorthand for --format txt")
    p.add_argument("--pretty", action="store_const", const="pretty", dest="format", help="Shorthand for --format pretty")
    p.add_argument("-o", "--output", default=None, help="Write output to file (default: stdout).")
    p.add_argument("--min-segment", type=float, default=5.0, help="Min segment length in seconds (default 5.0).")
    p.add_argument("--hop-length", type=int, default=1024, help="Hop length in samples (default 1024). Smaller = higher resolution, slower.")
    p.add_argument("--sr", type=int, default=22050, help="Sample rate (default 22050).")
    p.add_argument("--quiet", action="store_true", help="Suppress per-file progress messages.")
    p.add_argument("-v", "--version", action="version", version=f"audio2scene {__version__}")
    return p


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    outputs: List[str] = []
    multiple = len(args.input) > 1

    for idx, path in enumerate(args.input):
        p = Path(path)
        if not p.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            return 2

        if not args.quiet and multiple:
            print(f"[{idx+1}/{len(args.input)}] {p.name}", file=sys.stderr)

        try:
            segments = detect(
                p,
                sr=args.sr,
                hop_length=args.hop_length,
                min_segment_sec=args.min_segment,
            )
        except Exception as e:
            print(f"Error processing {p.name}: {e}", file=sys.stderr)
            return 1

        if args.format == "json":
            out = segments_to_json(segments, pretty=True)
        elif args.format == "csv":
            out = segments_to_csv(segments)
        elif args.format == "txt":
            out = segments_to_txt(segments)
        else:
            out = segments_to_pretty(segments)

        if multiple:
            outputs.append(f"=== {p.name} ===\n{out}")
        else:
            outputs.append(out)

    final = "\n\n".join(outputs)

    if args.output:
        Path(args.output).write_text(final, encoding="utf-8")
        if not args.quiet:
            print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(final)

    return 0


if __name__ == "__main__":
    sys.exit(main())
