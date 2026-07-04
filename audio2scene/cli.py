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
    audio2scene music.mp3 --video-editor      # video editor effect events (Cut/Flash/Zoom/Glitch/Fade)
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
from .video_editor import events_to_json, events_summary, map_video_events
from .remotion_generator import generate_remotion_project


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="audio2scene",
        description="Auto Video Editor — data.json in, MP4 out. 100% offline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
SUBCOMMANDS:
  generate-remotion    Generate Remotion video project from data.json (MAIN)
  (no subcommand)      Analyze audio file (segments, beats, events)

QUICK START — Generate Video:
  audio2scene generate-remotion -i data.json -o ./my-video --render --scale 0.5

  data.json format:
    {
      "music": "song.mp3",
      "text": ["Title", "Scene 2", "Thanks for watching"],
      "screen": "1080:1920",
      "duration": "30s",
      "font": "Inter",
      "logo": "https://example.com/logo.png",
      "videos": ["https://cdn.pixabay.com/video/clip.mp4"],
      "images": ["https://cdn.pixabay.com/photo/bg.jpg"]
    }

ANALYZE AUDIO:
  audio2scene music.mp3                 # pretty timeline
  audio2scene music.mp3 --json          # JSON output
  audio2scene music.mp3 --video-editor  # video editor events JSON
  audio2scene music.mp3 -o labels.json  # write to file
  audio2scene *.mp3                     # batch processing
""",
    )
    p.add_argument("input", nargs="*", help="Path(s) to audio file(s) for analysis mode. Use 'generate-remotion' subcommand for video generation.")
    p.add_argument("--format", choices=["json", "csv", "txt", "pretty", "video-editor"], default="pretty",
                   help="Output format (default: pretty)")
    p.add_argument("--json", action="store_const", const="json", dest="format", help="Shorthand for --format json")
    p.add_argument("--csv", action="store_const", const="csv", dest="format", help="Shorthand for --format csv")
    p.add_argument("--txt", action="store_const", const="txt", dest="format", help="Shorthand for --format txt")
    p.add_argument("--pretty", action="store_const", const="pretty", dest="format", help="Shorthand for --format pretty")
    p.add_argument("--video-editor", action="store_const", const="video-editor", dest="format",
                   help="Shorthand for --format video-editor. Outputs JSON with effect events (Cut/Flash/Zoom/Glitch/Fade).")
    p.add_argument("-o", "--output", default=None, help="Write output to file (default: stdout).")
    p.add_argument("--min-segment", type=float, default=5.0, help="Min segment length in seconds (default 5.0).")
    p.add_argument("--hop-length", type=int, default=1024, help="Hop length in samples (default 1024). Smaller = higher resolution, slower.")
    p.add_argument("--sr", type=int, default=22050, help="Sample rate (default 22050).")
    p.add_argument("--beat-strategy", choices=["auto", "all", "downbeat_only"], default="auto",
                   help="Beat emit strategy for video-editor format (default: auto).")
    p.add_argument("--onset-strategy", choices=["all", "strong_only"], default="all",
                   help="Onset emit strategy for video-editor format (default: all).")
    p.add_argument("--no-fades", action="store_true", help="Skip fade in/out events in video-editor output.")
    p.add_argument("--no-title", action="store_true", help="Skip title card event in video-editor output.")
    p.add_argument("--quiet", action="store_true", help="Suppress per-file progress messages.")
    p.add_argument("-v", "--version", action="version", version=f"audio2scene {__version__}")
    return p


def main(argv: List[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    # Subcommand: generate-remotion
    if args and args[0] == "generate-remotion":
        return _cmd_generate_remotion(args[1:])

    # Default: analyze mode
    return _cmd_analyze(args)


def _cmd_generate_remotion(args: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="audio2scene generate-remotion",
        description="Generate a ready-to-render Remotion project from data.json spec.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
data.json format:
  {
    "music": "song.mp3",
    "screen": "1280:720",
    "duration": "60s",
    "font": "Inter",
    "text": ["Title", "Verse 1", "Chorus", "Outro"],
    "videos": ["clip1.mp4", "clip2.mp4"],
    "images": ["bg1.jpg", "bg2.png"]
  }

Examples:
  # Generate project only
  audio2scene generate-remotion -i data.json -o ./my-video

  # Generate + install deps + render MP4 (single command)
  audio2scene generate-remotion -i data.json -o ./my-video --render

  # Fast render (quarter-res, 4x faster, for sandbox/preview)
  audio2scene generate-remotion -i data.json -o ./my-video --render --fast

  # Render only first 30s (900 frames)
  audio2scene generate-remotion -i data.json -o ./my-video --render --fast --frames=0-900
""",
    )
    parser.add_argument("--input", "-i", required=True, help="Path to data.json")
    parser.add_argument("--output", "-o", required=True, help="Output directory for Remotion project")
    parser.add_argument("--hop-length", type=int, default=1024, help="Hop length (default 1024)")
    parser.add_argument("--min-segment", type=float, default=5.0, help="Min segment length in seconds (default 5.0)")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second (default 30)")
    parser.add_argument("--render", action="store_true",
                        help="After generating, run npm install + render MP4 automatically")
    parser.add_argument("--fast", action="store_true",
                        help="Fast render: scale=0.25 (quarter-res), 4x faster. Use with --render")
    parser.add_argument("--scale", type=float, default=None,
                        help="Render scale 0.25-1.0 (overrides --fast). Default 0.5")
    parser.add_argument("--frames", type=str, default=None,
                        help="Frame range to render, e.g. '0-900' for first 30s. Default: full duration")
    sub_args = parser.parse_args(args)

    try:
        project_dir = generate_remotion_project(
            sub_args.input,
            sub_args.output,
            hop_length=sub_args.hop_length,
            min_segment_sec=sub_args.min_segment,
            fps=sub_args.fps,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if sub_args.render:
        return _render_project(project_dir, sub_args)
    return 0


def _render_project(project_dir, args) -> int:
    """Run npm install + remotion render inside the generated project."""
    import subprocess
    import shutil
    from pathlib import Path

    npm = shutil.which("npm")
    npx = shutil.which("npx")
    if not npm or not npx:
        print("Error: npm/npx not found. Install Node.js to use --render", file=sys.stderr)
        return 3

    # Determine render params
    if args.scale is not None:
        scale = args.scale
    elif args.fast:
        scale = 0.25
    else:
        scale = 0.5

    project_dir = Path(project_dir)
    print(f"\n[audio2scene] Installing dependencies in {project_dir}...")
    r = subprocess.run([npm, "install", "--silent"], cwd=str(project_dir))
    if r.returncode != 0:
        print("Error: npm install failed", file=sys.stderr)
        return r.returncode

    # Install extra dev deps for typography components
    subprocess.run([npm, "install", "--silent", "--save-dev", "@types/culori", "culori"],
                   cwd=str(project_dir))

    # Build output path
    output_mp4 = str(project_dir / "out" / "video.mp4")
    (project_dir / "out").mkdir(exist_ok=True)

    # Build render command
    cmd = [npx, "remotion", "render", "Audio2ScenePreview", output_mp4,
           f"--scale={scale}", "--timeout=60000", "--concurrency=2"]
    if args.frames:
        cmd.append(f"--frames={args.frames}")

    print(f"[audio2scene] Rendering MP4 (scale={scale})...")
    print(f"[audio2scene] Output: {output_mp4}")
    print()

    r = subprocess.run(cmd, cwd=str(project_dir))
    if r.returncode != 0:
        print(f"Error: render failed (exit {r.returncode})", file=sys.stderr)
        return r.returncode

    # Verify
    out_path = project_dir / "out" / "video.mp4"
    if out_path.exists():
        size_mb = out_path.stat().st_size / (1024 * 1024)
        print(f"\n[audio2scene] DONE — {output_mp4} ({size_mb:.1f} MB)")
    return 0


def _cmd_analyze(args: List[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(args)

    outputs: List[str] = []
    multiple = len(args.input) > 1

    if not args.input:
        parser.print_help()
        return 0

    for idx, path in enumerate(args.input):
        p = Path(path)
        if not p.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            return 2

        if not args.quiet and multiple:
            print(f"[{idx+1}/{len(args.input)}] {p.name}", file=sys.stderr)

        try:
            if args.format == "video-editor":
                # Need features for video editor mapping
                segments, feats = detect(
                    p,
                    sr=args.sr,
                    hop_length=args.hop_length,
                    min_segment_sec=args.min_segment,
                    return_features=True,
                )
                events = map_video_events(
                    segments, feats,
                    beat_strategy=args.beat_strategy,
                    onset_strategy=args.onset_strategy,
                    include_fades=not args.no_fades,
                    include_title=not args.no_title,
                )
                summary = events_summary(events)
                import json
                out = json.dumps({
                    "file": p.name,
                    "duration": round(feats.duration, 3),
                    "tempo": round(feats.tempo, 1),
                    "n_segments": len(segments),
                    "n_beats": int(len(feats.beat_times)),
                    "n_onsets": int(len(feats.onset_times)),
                    "summary": summary,
                    "events": [e.to_dict() for e in events],
                }, indent=2, ensure_ascii=False)
            else:
                segments = detect(
                    p,
                    sr=args.sr,
                    hop_length=args.hop_length,
                    min_segment_sec=args.min_segment,
                )
                if args.format == "json":
                    out = segments_to_json(segments, pretty=True)
                elif args.format == "csv":
                    out = segments_to_csv(segments)
                elif args.format == "txt":
                    out = segments_to_txt(segments)
                else:
                    out = segments_to_pretty(segments)
        except Exception as e:
            print(f"Error processing {p.name}: {e}", file=sys.stderr)
            return 1

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
