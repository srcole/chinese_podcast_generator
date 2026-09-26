"""Paragraph-synchronised study videos using measured PCM narration durations."""

import argparse
import asyncio
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import wave

from .audio import SAMPLE_RATE, append_silence, append_wave, ffmpeg, open_wave, synthesize
from .core import Speech, load_config, read_transcript, read_vocabulary

FPS = 25


@dataclass(frozen=True)
class Block:
    chinese: str
    english: str
    pinyin: str = ""


def read_blocks(folder, config, pinyin=None):
    patterns = config['podcast']['omit_lines']
    chinese = read_transcript(folder / config['inputs']['chinese'], patterns)
    english = read_transcript(folder / config['inputs']['english'], patterns)
    if pinyin is None:
        candidate = folder / 'transcript_pinyin.txt'
        pinyin = candidate if candidate.exists() else None
    romanised = read_transcript(pinyin, patterns) if pinyin else [''] * len(chinese)
    if not len(chinese) == len(english) == len(romanised):
        raise ValueError(f'Paragraph counts must match: Chinese={len(chinese)}, English={len(english)}, '
                         f'pinyin={len(romanised) if pinyin else "absent"}. '
                         'Use matching blank-line-separated blocks, including headings.')
    return [Block(*parts) for parts in zip(chinese, english, romanised)]


def highlight_mask(text, terms):
    """Leftmost, longest literal match; preserve repeats and punctuation."""
    terms = sorted(set(terms), key=lambda term: (-len(term), term))
    mask = [False] * len(text)
    if terms:
        for match in re.finditer('|'.join(re.escape(term) for term in terms if term), text):
            mask[match.start():match.end()] = [True] * len(match.group())
    return mask


def find_font(explicit=None):
    candidates = [explicit] if explicit else [
        '/System/Library/Fonts/Hiragino Sans GB.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
        'C:/Windows/Fonts/msyh.ttc',
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return str(candidate)
    raise ValueError('A Chinese font is required. Install Noto Sans CJK or pass --font PATH to a CJK TTF/OTF/TTC font.')


def wrap(text, font, width):
    """Wrap at words for Latin text and at characters for Chinese; keep offsets."""
    lines, line, length = [], [], 0
    for match in re.finditer(r'[A-Za-z\u00c0-\u024f]+|[^\n]', text.replace('\n', ' ')):
        token = match.group()
        pieces = [(token, match.start())]
        if font.getlength(token) > width:
            pieces = [(char, match.start() + i) for i, char in enumerate(token)]
        for piece, start in pieces:
            size = font.getlength(piece)
            if line and length + size > width:
                lines.append(line)
                line, length = [], 0
            if not line and piece.isspace():
                continue
            line.append((piece, start))
            length += size
    if line:
        lines.append(line)
    return lines


def layout(block, font_path):
    from PIL import ImageFont
    for size in range(52, 31, -2):
        groups = []
        height = 0
        for text, scale, color in [(block.chinese, 1, '#f5f7fc'),
                                    (block.pinyin, .70, '#9ac5f5'),
                                    (block.english, .73, '#c9d2e2')]:
            if not text:
                continue
            font = ImageFont.truetype(font_path, round(size * scale))
            lines = wrap(text, font, 1728)
            spacing = sum(font.getmetrics()) + 12
            groups.append((font, lines, spacing, color))
            height += len(lines) * spacing + 36
        if height <= 880:
            return groups
    raise ValueError('Text block is too long for a readable 1080p screen. Split it into shorter matching '
                     'blank-line-separated blocks in Chinese, English, and pinyin.')


def render_card(block, terms, font_path, index, total, destination):
    from PIL import Image, ImageDraw, ImageFont
    groups = layout(block, font_path)
    image = Image.new('RGB', (1920, 1080), '#101827')
    draw = ImageDraw.Draw(image)
    small = ImageFont.truetype(font_path, 24)
    draw.text((96, 35), f'{index} / {total}     中文 · Chinese', font=small, fill='#9ac5f5')
    draw.line((96, 83, 1824, 83), fill='#33435b', width=2)
    mask = highlight_mask(block.chinese, terms)
    y = 114
    for group_index, (font, lines, spacing, color) in enumerate(groups):
        for line in lines:
            x = 96
            for token, offset in line:
                # Split only at highlight changes, including Latin terms inside Chinese prose.
                start = 0
                while start < len(token):
                    highlighted = group_index == 0 and mask[offset + start]
                    end = start + 1
                    while end < len(token) and (group_index == 0 and mask[offset + end]) == highlighted:
                        end += 1
                    draw.text((x + font.getlength(token[:start]), y), token[start:end],
                              font=font, fill='#ffd36b' if highlighted else color)
                    start = end
                x += font.getlength(token)
            y += spacing
        y += 36
    draw.text((96, 1020), '词汇 · Vocabulary', font=small, fill='#ffd36b')
    image.save(destination)


async def generate_video(blocks, terms, config, output, cache, podcast_id, font_path):
    import edge_tts
    voice = config['voices']['chinese']
    available = {v['ShortName'] for v in await edge_tts.list_voices()}
    if voice not in available:
        raise ValueError(f'Voice unavailable: {voice}')
    output.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output, prefix='.video-') as temporary:
        work = Path(temporary)
        timeline = []
        total_frames = 0
        with open_wave(work / 'narration.wav') as combined:
            for index, block in enumerate(blocks, 1):
                print(f'Video block {index}/{len(blocks)}', flush=True)
                card = work / f'{index:04d}.png'
                render_card(block, terms, font_path, index, len(blocks), card)
                audio = await synthesize(Speech(block.chinese, voice, '+0%'), cache)
                decoded = work / 'segment.wav'
                ffmpeg('-i', audio, '-ar', str(SAMPLE_RATE), '-ac', '1', '-c:a', 'pcm_s16le', decoded)
                with wave.open(str(decoded), 'rb') as stream:
                    samples = stream.getnframes()
                frames = math.ceil(samples / (SAMPLE_RATE // FPS))
                append_wave(combined, decoded)
                # Quantise each boundary to a frame and pad audio identically: no cumulative drift.
                append_silence(combined, (frames * (SAMPLE_RATE // FPS) - samples) / SAMPLE_RATE)
                timeline.append({'block': index, 'start': total_frames / FPS,
                                 'end': (total_frames + frames) / FPS})
                total_frames += frames
        concat = []
        for item in timeline:
            concat.extend([f"file '{item['block']:04d}.png", 'option framerate 25',
                           f"duration {item['end'] - item['start']:.8f}"])
        concat.append(f"file '{len(blocks):04d}.png'")
        (work / 'frames.txt').write_text('\n'.join(concat) + '\n', encoding='utf-8')
        destination = work / f'{podcast_id}_video.mp4'
        print('Encoding 1080p video…', flush=True)
        ffmpeg('-f', 'concat', '-safe', '0', '-i', work / 'frames.txt', '-i', work / 'narration.wav',
               '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-preset', 'veryfast',
               '-tune', 'stillimage', '-crf', '23',
               '-vf', f'tpad=stop_mode=clone:stop_duration=1,fps={FPS}', '-pix_fmt', 'yuv420p', '-r', str(FPS), '-fps_mode', 'cfr',
               '-t', str(total_frames / FPS), '-c:a', 'aac', '-b:a', '128k',
               '-movflags', '+faststart', destination)
        manifest = work / 'video_manifest.json'
        manifest.write_text(json.dumps({'file': destination.name, 'voice': voice, 'rate': '+0%',
                                       'font': font_path, 'timeline': timeline}, indent=2) + '\n')
        destination.replace(output / destination.name)
        manifest.replace(output / manifest.name)
    return output / f'{podcast_id}_video.mp4'


def main():
    parser = argparse.ArgumentParser(description='Generate a Chinese-only narrated study video')
    parser.add_argument('folder', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--cache', type=Path, default=Path('.podcast-cache'))
    parser.add_argument('--pinyin', type=Path, help='Optional aligned pinyin file (default: folder/transcript_pinyin.txt)')
    parser.add_argument('--font', type=Path, help='Chinese-capable TTF/OTF/TTC font')
    parser.add_argument('--dry-run', action='store_true', help='Check inputs, layout and dependencies without speech or video generation')
    parser.add_argument('--preview', action='store_true', help='Render only the first two blocks in video-preview/')
    args = parser.parse_args()
    try:
        base = args.config or Path('podcast.toml')
        paths = [base] if args.config or base.exists() else []
        override = args.folder / 'podcast.toml'
        if override.exists() and override.resolve() != base.resolve():
            paths.append(override)
        config = load_config(paths)
        blocks = read_blocks(args.folder, config, args.pinyin)
        terms = [term for term, _ in read_vocabulary(args.folder / config['inputs']['vocabulary'])]
        font = find_font(args.font)
        if not shutil.which('ffmpeg'):
            raise ValueError('FFmpeg is required (macOS: brew install ffmpeg).')
        for index, block in enumerate(blocks, 1):
            try:
                layout(block, font)
            except ValueError as error:
                raise ValueError(f'Block {index}: {error}') from error
        output = args.output or Path('outputs') / args.folder.resolve().name
        if args.preview:
            blocks = blocks[:2]
            output /= 'video-preview'
        print(f'{len(blocks)} aligned blocks; {len(terms)} vocabulary entries; normal-speed Chinese narration')
        print(f'Font: {font}\nOutput: {output}')
        if not args.dry_run:
            result = asyncio.run(generate_video(blocks, terms, config, output, args.cache,
                                                args.folder.resolve().name, font))
            print(f'Finished: {result}')
    except (OSError, ValueError, RuntimeError, ImportError, re.error) as error:
        parser.exit(1, f'Error: {error}\n')
    except KeyboardInterrupt:
        parser.exit(1, 'Interrupted; cached speech can be reused on the next run.\n')


if __name__ == '__main__':
    main()
