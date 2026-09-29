#!/usr/bin/env python3
"""One-command Tang-poem pipeline: storyboard -> illustrations -> video -> narration.

Given a poem file, produce a narrated MP4. Every stage is resumable and skips
work that already exists, so a new poem joins the existing batch by dropping a
text file in and running this once.

Stages
    plan      sentence -> storyboard scenes (reuses scripts/story-to-video.mjs)
    subtitle  modern-Chinese paraphrase per scene (translations table)
    images    text-to-image plates via the image generator
    render    Remotion silent MP4 with Ken Burns drift + burned-in subtitles
    tts       per-line narration
    mux       narration onto the rendered track

Usage
    python3 scripts/tangshi-pipeline.py examples/tangshi/batch-inputs/49-xxx.txt
    python3 scripts/tangshi-pipeline.py --all          # every poem in the batch dir
    python3 scripts/tangshi-pipeline.py --all --stages render,mux
    python3 scripts/tangshi-pipeline.py --all --force  # redo even if outputs exist
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH_DIR = ROOT / "storyboards/tangshi-batch"
INPUT_DIR = ROOT / "examples/tangshi/batch-inputs"
AUDIO_DIR = ROOT / "public/tangshi-audio"
IMAGE_DIR = ROOT / "public/tangshi-images"
OUT_DIR = ROOT / "out/tangshi-pilot"

VALID_STAGES = ("plan", "subtitle", "images", "render", "tts", "mux")


def run(cmd: list[str], cwd: Path = ROOT, quiet: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True,
    )
    if proc.returncode != 0 and not quiet:
        sys.stderr.write(proc.stdout + proc.stderr)
    return proc


def stem_from_input(path: Path) -> str:
    """49-登幽州台歌.txt -> 49-登幽州台歌"""
    return path.stem


def stem_from_json(path: Path) -> str:
    return path.stem


# ---------------------------------------------------------------- stages


def stage_plan(stem: str, force: bool) -> bool:
    """Sentence file -> storyboard.json in the batch dir."""
    out = BATCH_DIR / f"{stem}.json"
    if out.exists() and not force:
        print(f"    plan    跳过（已存在 {out.name}）")
        return True

    src = INPUT_DIR / f"{stem}.txt"
    if not src.exists():
        print(f"    plan    跳过（无输入 {src.name}）")
        return False

    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    proc = run([
        "node", "scripts/story-to-video.mjs",
        "--input", str(src),
        "--title", stem.split("-", 1)[-1],
        "--mode", "plan",
    ])
    if proc.returncode != 0:
        print(f"    plan    失败：{proc.stderr.strip()[-200:]}")
        return False

    # story-to-video.mjs writes to storyboard.json; move it into the batch dir.
    produced = ROOT / "storyboard.json"
    target = BATCH_DIR / f"{stem}.json"
    if not produced.exists():
        print("    plan    失败：未产出 storyboard.json")
        return False
    shutil.copy(produced, target)
    print(f"    plan    ✓ {target.name}")
    return True


def stage_subtitle(stem: str, force: bool) -> bool:
    """Attach per-scene modern-Chinese paraphrases from the translations table."""
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import add_subtitles  # noqa: PLC0415
    except ImportError:
        print("    subtitle 失败：找不到 add_subtitles.py")
        return False

    mapping = add_subtitles.TRANSLATIONS.get(stem)
    board_path = BATCH_DIR / f"{stem}.json"
    if not board_path.exists():
        return False
    if mapping is None:
        print(f"    subtitle 跳过（{stem} 暂无译文，需要人工补）")
        return False

    board = json.loads(board_path.read_text(encoding="utf-8"))
    scenes = board if isinstance(board, list) else board.get("scenes", [])
    dirty = False
    for scene in scenes:
        want = mapping.get(scene["id"])
        if want is None:
            continue
        if scene.get("subtitle") != want and (force or not scene.get("subtitle")):
            scene["subtitle"] = want
            dirty = True
    if dirty:
        board_path.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("    subtitle ✓ 已写入译文")
    else:
        print("    subtitle 跳过（已有译文）")
    return True


def stage_images(stem: str, force: bool) -> bool:
    """Text-to-image plates, one per scene, reusing existing plates."""
    board_path = BATCH_DIR / f"{stem}.json"
    if not board_path.exists():
        return False

    board = json.loads(board_path.read_text(encoding="utf-8"))
    scenes = board if isinstance(board, list) else board.get("scenes", [])
    dest = IMAGE_DIR / stem
    dest.mkdir(parents=True, exist_ok=True)

    missing = []
    for scene in scenes:
        rel = scene.get("assets", {}).get("color")
        if rel and not (ROOT / "public" / rel).exists():
            missing.append(scene)

    if not missing and not force:
        print(f"    images   跳过（{len(scenes)} 张插画已齐）")
        return True
    if not missing:
        print(f"    images   跳过（--force 未启用重绘）")
        return True

    if not os.environ.get("MINIMAX_API_KEY"):
        print(f"    images   跳过（{len(missing)} 张待生成，但未配置 MINIMAX_API_KEY）")
        return False

    # Prompts come from the existing prompt builder; images from the generator.
    ok = True
    for scene in missing:
        rel = scene["assets"]["color"]
        target = ROOT / "public" / rel
        proc = run([
            sys.executable, "scripts/minimax_image.py",
            "--prompt-file", "/dev/stdin",
            "--out", str(target),
        ])
        if proc.returncode != 0:
            ok = False
    print(f"    images   {'✓' if ok else '部分失败'}（缺 {len(missing)} 张）")
    return ok


def stage_render(stem: str, force: bool) -> bool:
    """Remotion silent MP4 with Ken Burns + burned-in subtitles."""
    out = OUT_DIR / f"{stem}.mp4"
    silent = ROOT / "out/tangshi-motion" / f"{stem}.mp4"
    board = BATCH_DIR / f"{stem}.json"

    if out.exists() and not force:
        print(f"    render   跳过（{out.name} 已存在）")
        return True
    if not board.exists():
        return False

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    silent.parent.mkdir(parents=True, exist_ok=True)
    backup = ROOT / "storyboard.render-backup.json"
    backup.write_text((ROOT / "storyboard.json").read_text(encoding="utf-8"), encoding="utf-8")
    try:
        (ROOT / "storyboard.json").write_text(board.read_text(encoding="utf-8"), encoding="utf-8")
        proc = run([
            "npx", "remotion", "render", "src/index.ts", "PictureSilent", str(silent),
            "--codec=h264", "--crf=18", "--pixel-format=yuv420p", "--muted", "--concurrency=1",
        ])
    finally:
        shutil.copy(backup, ROOT / "storyboard.json")
        backup.unlink(missing_ok=True)

    if proc.returncode != 0 or not silent.exists():
        print(f"    render   失败：{proc.stderr.strip()[-200:]}")
        return False
    print(f"    render   ✓ {silent.name}")
    return True


def stage_tts(stem: str, force: bool) -> bool:
    """Per-line narration mp3s."""
    dest = AUDIO_DIR / stem
    board = BATCH_DIR / f"{stem}.json"
    if not board.exists():
        return False

    board_data = json.loads(board.read_text(encoding="utf-8"))
    scenes = board_data if isinstance(board_data, list) else board_data.get("scenes", [])

    missing = [s["id"] for s in scenes if not (dest / f"{s['id']}.mp3").exists()]
    if not missing and not force:
        print(f"    tts      跳过（{len(scenes)} 句已齐）")
        return True

    tts_script = ROOT / "scripts/batch-tangshi-tts.mjs"
    if not tts_script.exists():
        print("    tts      跳过（无 TTS 脚本）")
        return False

    proc = run(["node", str(tts_script), "--only", stem])
    if proc.returncode != 0:
        print(f"    tts      失败：{proc.stderr.strip()[-200:]}")
        return False
    print("    tts      ✓ 已生成朗读")
    return True


def stage_mux(stem: str, force: bool) -> bool:
    """Narration onto the silent render."""
    out = OUT_DIR / f"{stem}.mp4"
    silent = ROOT / "out/tangshi-motion" / f"{stem}.mp4"
    board = BATCH_DIR / f"{stem}.json"
    audio = AUDIO_DIR / stem

    if out.exists() and not force:
        print(f"    mux      跳过（{out.name} 已存在）")
        return True
    if not silent.exists() or not board.exists() or not audio.is_dir():
        print("    mux      跳过（缺渲染产物或音频）")
        return False

    proc = run([
        sys.executable, "scripts/mux-narration.py",
        "--video", str(silent),
        "--storyboard", str(board),
        "--audio-dir", str(audio),
        "--out", str(out),
    ])
    if proc.returncode != 0:
        print(f"    mux      失败：{proc.stderr.strip()[-200:]}")
        return False
    print(f"    mux      ✓ {out.name}")
    return True


STAGE_FUNCS = {
    "plan": stage_plan,
    "subtitle": stage_subtitle,
    "images": stage_images,
    "render": stage_render,
    "tts": stage_tts,
    "mux": stage_mux,
}


def main() -> int:
    ap = argparse.ArgumentParser(description="End-to-end Tang-poem video pipeline")
    ap.add_argument("input", nargs="?", help="poem .txt path, or a poem stem")
    ap.add_argument("--all", action="store_true", help="process every poem in the batch dir")
    ap.add_argument("--stages", default=",".join(VALID_STAGES), help="comma-separated stages")
    ap.add_argument("--force", action="store_true", help="rebuild stages that already have output")
    args = ap.parse_args()

    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    bad = [s for s in stages if s not in VALID_STAGES]
    if bad:
        sys.exit(f"unknown stage(s): {', '.join(bad)}; valid: {', '.join(VALID_STAGES)}")

    if args.all:
        stems = sorted(p.stem for p in BATCH_DIR.glob("*.json") if not p.stem.startswith("_"))
    elif args.input:
        p = Path(args.input)
        stems = [p.stem if p.suffix == ".txt" else p.name]
    else:
        ap.error("give a poem path/stem or --all")

    print(f"处理 {len(stems)} 首，阶段: {', '.join(stages)}\n")
    summary: dict[str, int] = {s: 0 for s in stages}
    failed: list[tuple[str, str]] = []

    for stem in stems:
        print(f"=== {stem} ===")
        for stage in stages:
            try:
                if STAGE_FUNCS[stage](stem, args.force):
                    summary[stage] += 1
                else:
                    failed.append((stem, stage))
            except Exception as exc:  # noqa: BLE001
                print(f"    {stage:8s} 异常：{exc}")
                failed.append((stem, stage))
        print()

    print("=== 汇总 ===")
    for stage in stages:
        print(f"  {stage:9s} 成功 {summary[stage]}/{len(stems)}")
    if failed:
        print(f"\n未完成 {len(failed)} 项：")
        for stem, stage in failed:
            print(f"  {stem}: {stage}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
