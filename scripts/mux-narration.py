#!/usr/bin/env python3
"""Mux per-line TTS narration onto a rendered storyboard video.

The storyboard is the single source of truth for timing: scene N starts at the
sum of the preceding durations, and its narration is placed at that offset.
Scenes longer than their narration leave trailing silence, which gives a child
time to look at the drawing before the next line starts.

    python3 scripts/mux-narration.py \
      --video out/picture_silent.mp4 \
      --storyboard storyboard.json \
      --audio-dir public/tangshi-audio/03-鹿柴 \
      --out out/03-鹿柴-narrated.mp4
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Mux narration onto a storyboard video")
    ap.add_argument("--project", default=".", help="project root")
    ap.add_argument("--video", required=True, help="silent input mp4")
    ap.add_argument("--storyboard", required=True, help="storyboard json")
    ap.add_argument("--audio-dir", required=True, help="dir of NN.mp3, one per scene")
    ap.add_argument("--out", required=True, help="output mp4")
    ap.add_argument("--lead-in", type=float, default=0.3,
                    help="seconds of silence before the first line")
    args = ap.parse_args()

    root = Path(args.project).resolve()

    def resolve(value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else root / p

    video, sb_path = resolve(args.video), resolve(args.storyboard)
    audio_dir, out = resolve(args.audio_dir), resolve(args.out)

    if not video.exists():
        sys.exit(f"missing video: {video}")
    if not sb_path.exists():
        sys.exit(f"missing storyboard: {sb_path}")

    scenes = json.loads(sb_path.read_text(encoding="utf-8")).get("scenes") or []
    if not scenes:
        sys.exit(f"no scenes in {sb_path}")

    missing = [s["id"] for s in scenes if not (audio_dir / f"{s['id']}.mp3").exists()]
    if missing:
        sys.exit(f"missing narration for scenes: {', '.join(missing)}")

    offsets, cursor = [], args.lead_in
    for scene in scenes:
        offsets.append(round(cursor * 1000))
        cursor += float(scene.get("duration_sec", 0))
    total = cursor

    # amix over just the narration clips, longest-wins: the trailing scene is the
    # longest contributor, so the mix runs at least to the end of the timeline.
    chains = [
        f"[{i + 1}:a]aresample=44100,adelay={ms}|{ms}[a{i}]"
        for i, ms in enumerate(offsets)
    ]
    labels = "".join(f"[a{i}]" for i in range(len(offsets)))
    graph = ";".join(
        chains + [f"{labels}amix=inputs={len(offsets)}:duration=longest:normalize=0[mixed]"]
    )

    cmd = ["ffmpeg", "-y", "-i", str(video)]
    for scene in scenes:
        cmd += ["-i", str(audio_dir / f"{scene['id']}.mp3")]
    cmd += [
        "-filter_complex", graph,
        "-map", "0:v:0", "-map", "[mixed]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        "-t", f"{total:.3f}",
        str(out),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{proc.stderr[-2000:]}")

    print(f"scenes={len(scenes)} timeline={total:.2f}s lead_in={args.lead_in}s")
    print(f"wrote {out}")
    for line in subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height:format=duration,size",
         "-of", "default=nw=1", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines():
        print(" ", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
