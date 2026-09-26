"""Resumable synthesis and PCM assembly, avoiding MP3 padding at joins."""

import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import wave

from .core import Silence, Speech

SAMPLE_RATE = 24000


def ffmpeg(*args: str) -> None:
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError(f"FFmpeg failed: {result.stderr.strip()}")


async def synthesize(speech: Speech, cache: Path) -> Path:
    import edge_tts

    key = hashlib.sha256(json.dumps(asdict(speech), sort_keys=True).encode()).hexdigest()
    target = cache / f"{key}.mp3"
    if target.exists() and target.stat().st_size:
        return target
    for attempt in range(3):
        try:
            with tempfile.TemporaryDirectory(dir=cache) as temporary:
                part = Path(temporary) / "speech.mp3"
                await edge_tts.Communicate(**asdict(speech)).save(str(part))
                if not part.stat().st_size:
                    raise RuntimeError("TTS returned empty audio")
                part.replace(target)
            return target
        except Exception as error:
            if attempt == 2:
                raise RuntimeError(f"Speech generation failed for {speech.text[:60]!r}: {error}") from error
            print(f"  Temporary TTS failure; retrying ({attempt + 1}/2): {error}", flush=True)
            await asyncio.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def append_silence(output, seconds: float) -> None:
    remaining = round(seconds * SAMPLE_RATE) * 2
    while remaining:
        count = min(remaining, 65536)
        output.writeframesraw(bytes(count))
        remaining -= count


def append_wave(output, path: Path) -> None:
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, SAMPLE_RATE):
            raise RuntimeError(f"Unexpected audio format in {path}")
        while chunk := source.readframes(32768):
            output.writeframesraw(chunk)


def open_wave(path: Path):
    output = wave.open(str(path), "wb")
    output.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
    return output


def encode(source: Path, destination: Path) -> None:
    ffmpeg("-i", source, "-codec:a", "libmp3lame", "-b:a", "128k", destination)


async def generate(plan, config: dict, output: Path, cache: Path, podcast_id: str) -> None:
    import edge_tts

    available = {voice["ShortName"] for voice in await edge_tts.list_voices()}
    requested = {item.voice for _, items in plan for item in items if isinstance(item, Speech)}
    missing = requested - available
    if missing:
        raise ValueError(f"Voices unavailable: {', '.join(sorted(missing))}. Run edge-tts --list-voices to choose replacements.")
    output.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    # Publish each completed section immediately; vocabulary synthesis runs last.
    with tempfile.TemporaryDirectory(dir=output, prefix=".render-") as temporary:
        work = Path(temporary)
        waves = {}
        deliverables = {}
        generation_order = sorted(enumerate(plan, 1), key=lambda entry: entry[1][0] == "vocabulary")
        for index, (name, items) in generation_order:
            print(f"Section {index}/{len(plan)}: {name}", flush=True)
            section = work / f"{podcast_id}_{index:02d}_{name}.wav"
            with open_wave(section) as stream:
                count = sum(isinstance(item, Speech) for item in items)
                completed = 0
                for item in items:
                    if isinstance(item, Silence):
                        append_silence(stream, item.seconds)
                    else:
                        audio = await synthesize(item, cache)
                        decoded = work / "segment.wav"
                        ffmpeg("-i", audio, "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", decoded)
                        append_wave(stream, decoded)
                        completed += 1
                        print(f"  Speech {completed}/{count}", flush=True)
            destination = section.with_suffix(".mp3")
            encode(section, destination)
            destination.replace(output / destination.name)
            deliverables[name] = destination.name
            waves[name] = section
        combined = work / "podcast.wav"
        with open_wave(combined) as stream:
            for index, (name, _) in enumerate(plan):
                if index:
                    append_silence(stream, config["pauses"]["between_sections"])
                append_wave(stream, waves[name])
        combined_mp3 = work / f"{podcast_id}_podcast.mp3"
        encode(combined, combined_mp3)
        combined_mp3.replace(output / combined_mp3.name)
        manifest = work / "manifest.json"
        manifest.write_text(json.dumps({"settings": config, "files": [combined_mp3.name]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        manifest.replace(output / manifest.name)
        # Keep completed sections on failure; remove them only after publishing the episode.
        for filename in deliverables.values():
            (output / filename).unlink()
