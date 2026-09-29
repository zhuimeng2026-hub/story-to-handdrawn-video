#!/usr/bin/env python3
"""Batch-mux narration onto every rendered Tang-poem video.

Pairs out/tangshi-video/<poem>.mp4 with public/tangshi-audio/<poem>/NN.mp3 using
storyboards/tangshi-batch/<poem>.json as the timing source, then delegates the
actual mix to mux-narration.py so batch and single runs cannot drift apart.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUX = ROOT / "scripts/mux-narration.py"
VIDEO_DIR = ROOT / "out/tangshi-video"
AUDIO_DIR = ROOT / "public/tangshi-audio"
BOARD_DIR = ROOT / "storyboards/tangshi-batch"
OUT_DIR = ROOT / "out/tangshi-narrated"


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch-mux narration onto poem videos")
    ap.add_argument("--limit", type=int, default=0, help="only the first N poems")
    ap.add_argument("--force", action="store_true", help="re-mux existing outputs")
    ap.add_argument("--only", default="", help="comma-separated poem names")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    videos = sorted(p for p in VIDEO_DIR.glob("*.mp4"))
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        videos = [p for p in videos if p.stem in wanted]
    if args.limit:
        videos = videos[: args.limit]

    ok, skipped, failed = [], [], []
    for video in videos:
        name = video.stem
        board = BOARD_DIR / f"{name}.json"
        audio = AUDIO_DIR / name
        out = OUT_DIR / f"{name}.mp4"

        if not board.exists():
            failed.append((name, "缺 storyboard"))
            continue
        if not audio.is_dir():
            failed.append((name, "缺 audio dir"))
            continue
        if out.exists() and out.stat().st_size > 10000 and not args.force:
            skipped.append(name)
            continue

        proc = subprocess.run(
            [
                sys.executable, str(MUX),
                "--project", str(ROOT),
                "--video", str(video),
                "--storyboard", str(board),
                "--audio-dir", str(audio),
                "--out", str(out),
            ],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-1:]
            failed.append((name, tail[0] if tail else f"exit={proc.returncode}"))
            print(f"  ✗ {name}: {tail[0] if tail else ''}")
            continue
        ok.append(name)
        print(f"  ✓ {name}.mp4")

    print(f"\n=== 汇总 ===")
    print(f"成功 {len(ok)} | 跳过 {len(skipped)} | 失败 {len(failed)} | 共 {len(videos)}")
    if failed:
        print("失败明细:")
        for name, why in failed:
            print(f"  {name}: {why}")
    print(f"输出目录: {OUT_DIR}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
