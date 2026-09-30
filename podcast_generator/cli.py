import argparse
import asyncio
import json
from pathlib import Path
import re
import shutil
import sys

from .core import Speech, build_plan, load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Chinese study podcasts with Edge TTS")
    parser.add_argument("folder", type=Path, help="Folder containing transcripts and vocabulary")
    parser.add_argument("--config", type=Path, help="Base TOML settings (default: ./podcast.toml if present)")
    parser.add_argument("--output", type=Path, help="Output folder (default: outputs/<input folder name>)")
    parser.add_argument("--cache", type=Path, default=Path(".podcast-cache"))
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print settings without network or audio generation")
    parser.add_argument("--preview", action="store_true", help="Render first two vocabulary entries and first two transcript blocks")
    args = parser.parse_args()
    try:
        folder = args.folder.resolve()
        if not folder.is_dir():
            raise ValueError(f"Input folder does not exist: {folder}")
        paths = []
        base = args.config or Path("podcast.toml")
        if args.config or base.exists():
            paths.append(base)
        override = folder / "podcast.toml"
        if override.exists() and override.resolve() != base.resolve():
            paths.append(override)
        config = load_config(paths)
        plan = build_plan(folder, config)
        if args.preview:
            limits = {"vocabulary": 7, "interleaved": 4}
            plan = [(name, items[:limits.get(name, 2)]) for name, items in plan]
        output = args.output or Path("outputs") / folder.name
        if args.preview:
            output = output / "preview"
        print(json.dumps(config, indent=2, ensure_ascii=False))
        for name, items in plan:
            print(f"{name}: {sum(isinstance(item, Speech) for item in items)} speech segments")
        print(f"Output: {output}")
        if args.dry_run:
            return
        if not shutil.which("ffmpeg"):
            raise ValueError("FFmpeg is required. On macOS install it with: brew install ffmpeg")
        from .audio import generate
        asyncio.run(generate(plan, config, output, args.cache, folder.name))
        print(f"Finished: {output / (folder.name + '_podcast.mp3')}")
    except (OSError, ValueError, RuntimeError, re.error, ImportError) as error:
        parser.exit(1, f"Error: {error}\n")
    except KeyboardInterrupt:
        sys.exit("Interrupted; rerun the same command to reuse cached speech.")
