"""
audio2scene.timeline
====================

Timeline assembly + export to JSON / CSV / TXT / pretty text.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict
from typing import List

from .classifier import LabeledSegment


def segments_to_json(segments: List[LabeledSegment], pretty: bool = False) -> str:
    """Export to JSON. ``pretty=True`` returns indented for human reading."""
    data = {"segments": [s.to_dict() for s in segments]}
    if pretty:
        return json.dumps(data, indent=2)
    return json.dumps(data)


def segments_to_csv(segments: List[LabeledSegment]) -> str:
    """Export to CSV: columns start,end,label,confidence."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["start", "end", "label", "confidence"])
    for s in segments:
        writer.writerow([round(s.start, 3), round(s.end, 3), s.label, round(s.confidence, 3)])
    return buf.getvalue()


def segments_to_txt(segments: List[LabeledSegment]) -> str:
    """Export to TXT: ``MM:SS Label`` per line, one per segment start."""
    lines = []
    for s in segments:
        mm = int(s.start // 60)
        ss = int(s.start % 60)
        lines.append(f"{mm:02d}:{ss:02d} {s.label}")
    return "\n".join(lines) + "\n"


def segments_to_pretty(segments: List[LabeledSegment]) -> str:
    """Human-friendly timeline with timestamps like ``MM:SS.mmm``."""
    if not segments:
        return "(no segments)"
    lines = []
    for s in segments:
        ts = _fmt_timecode(s.start)
        bar = _bar(s.confidence, width=10)
        lines.append(f"  {ts}  {s.label:<22} [{bar}] {int(s.confidence * 100):>3}%")
    # Footer with duration
    total = segments[-1].end if segments else 0.0
    lines.append("")
    lines.append(f"  Total duration: {_fmt_timecode(total)}  ({len(segments)} segments)")
    return "\n".join(lines)


def _fmt_timecode(sec: float) -> str:
    m = int(sec // 60)
    s = sec - m * 60
    return f"{m:02d}:{s:06.3f}"


def _bar(value: float, width: int = 10) -> str:
    n = max(0, min(width, int(round(value * width))))
    return "#" * n + "." * (width - n)
