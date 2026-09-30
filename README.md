# Chinese podcast generator

Generate study podcasts from `transcript.txt`, `transcript_english.txt`, and
`vocab_list.csv` in a resource folder. Requires Python 3.11+, FFmpeg, and internet
access. Text is sent to Microsoft's online speech service through
[edge-tts](https://github.com/rany2/edge-tts); no API key is required.

## Install and run

```sh
brew install ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m podcast_generator inputs/20260921_1_tech_week --dry-run
python -m podcast_generator inputs/20260921_1_tech_week --preview
python -m podcast_generator inputs/20260921_1_tech_week
```

The installed `chinese-podcast` command accepts the same arguments. Dry runs
validate resources without network access. Preview renders two vocabulary entries
and two transcript blocks (two complete line pairs for interleaved narration)
into a separate `preview/` subfolder.

Outputs in `outputs/<input-folder-name>/`:

- `<podcast-id>_podcast.mp3`: the combined episode.
- `manifest.json`: effective settings and output filenames.

The default playback order is slow Chinese (-20%), vocabulary (complete English
meaning at +100%, then Chinese term at +0%), then interleaved narration:
English line 1 (+100%), Chinese line 1 (+0%), English line 2, Chinese line 2,
and so on through both transcripts.
Vocabulary uses `rates.english` and `rates.chinese`; the old shared
`rates.vocabulary` setting is accepted for compatibility but no longer used.
Numbered section MP3s are saved during generation and deleted after the combined
episode and manifest are successfully saved. If generation fails, completed
sections remain available.

Voices default to `zh-CN-XiaoxiaoNeural` and `en-US-AvaMultilingualNeural`.
Vocabulary preserves order, duplicates, alternative meanings and parentheses;
pinyin and timestamps are ignored. Added pauses are 0.05 seconds between term and
meaning, 0.5 seconds between entries, and 1.5 seconds between major sections.
These are additional to the voice's natural pauses. No extra announcements are
inserted. Titles and headings are spoken; production notes are omitted.

## Configuration

Edit `podcast.toml` for shared settings. Place another `podcast.toml` inside an
episode's resource folder to override individual settings, for example:

```toml
[rates]
english = "+50%"
chinese_slow = "-30%"

[pauses]
between_sections = 4.0
```

Precedence: built-in defaults, then `./podcast.toml` (or `--config PATH`), then the
resource folder's `podcast.toml`. Input filenames resolve against the resource
folder. `--output PATH` and `--cache PATH` change output and cache directories;
these paths resolve against the current working directory.

`podcast.sections` defaults to `["chinese_slow", "vocabulary", "interleaved"]`.
It can reorder or omit sections; separate `english` and `chinese` sections
remain available when explicitly configured.
The `interleaved` section pairs nonempty spoken lines, including headings,
after removing production notes and markup. Both transcripts must have the same
number of lines in matching translation order; mismatches fail before synthesis.
A paragraph written on one line is spoken as one unit. Lines are not automatically
split into sentences or translated. Interleaved narration uses `rates.english`
and `rates.chinese` and the corresponding configured voices.
`podcast.omit_lines` is a list of regular expressions matching entire production
note lines; an override replaces that list. Plain text and the example's Markdown
headings, bold, links and separators are supported, not arbitrary Markdown.
Transcripts are read as supplied without translation or editorial changes.

CSV requires `chinese` and `english` columns; extra columns are ignored. Quote
values containing commas. Files must be UTF-8; a UTF-8 BOM is accepted.

Completed speech segments are cached by text, voice and rate in `.podcast-cache/`.
Rerun after interruption to reuse them. Speech failures are retried twice. Voices
are validated against the live service before rendering, with no automatic
substitution. Use `edge-tts --list-voices` to inspect available voices.

Audio is assembled in mono PCM and encoded to 128 kbps MP3. Combined audio is
built from PCM, avoiding another encode of section MP3s. Each section is published immediately after it completes. Transcript recordings
are generated before vocabulary, so they remain accessible if vocabulary synthesis
fails. Combined playback order still follows `podcast.sections` (slow Chinese, vocabulary, then interleaved English/Chinese
by default). Each MP3 filename starts with the input folder name, even when using
`--output` or `--preview`. Reruns replace matching filenames; obsolete files from
changed section orders are not automatically removed. Do not run concurrent jobs
into the same output directory.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests do not contact the speech service. Audio integration tests require FFmpeg.

## Study videos

Install the optional video dependency, then use the separate video command:

```sh
pip install -e '.[video]'
python -m podcast_generator.video inputs/places_liverpool --dry-run
python -m podcast_generator.video inputs/places_liverpool --preview
python -m podcast_generator.video inputs/places_liverpool
```

The installed `chinese-podcast-video` command accepts the same arguments.
Videos contain **only Chinese narration at normal speed (`+0%`)**, using the
configured Chinese voice. Each 1080p screen shows one Chinese paragraph, its
English translation, and optional pinyin. Vocabulary matches from `vocab_list.csv`
are gold throughout their screen; highlights are not a word-by-word karaoke cursor.
Matching is literal, leftmost and longest first, including repeated occurrences.

Use matching blank-line-separated blocks in both transcripts, including titles
and headings. For pinyin, add `transcript_pinyin.txt` in the input folder or pass
`--pinyin PATH` (relative to the working directory). It must have the same block
count and order. Pinyin is displayed as supplied, not generated or aligned under
individual characters. Equal block counts cannot detect incorrectly paired
translations: check their order yourself. Existing transcript markup and omitted
production-note rules also apply here.

Text wraps and adjusts its size to fit a screen. A block that cannot fit at the
minimum readable size fails validation with its block number; split it into
shorter matching blocks in all supplied transcripts. The tool does not guess
sentence-level translation alignment or truncate text.

Requires FFmpeg with H.264 (`libx264`) and AAC encoding, Pillow, and a Chinese font.
The tool finds Hiragino Sans GB on macOS, common Noto Sans CJK installations on
Linux, or Microsoft YaHei on Windows. Use `--font PATH` to select another
Chinese-capable TTF/OTF/TTC font; ensure it also supports your pinyin tone marks.
Font metrics and wrapping use [Pillow](https://pillow.readthedocs.io/en/stable/reference/ImageFont.html).
Dry runs check all blocks, font loading, layout, and FFmpeg presence without
network access. Rendering requires the same online speech service as podcasts.

Configuration precedence, `--config`, `--output`, and `--cache` match the audio
command. Audio section order and configured speed are ignored for videos. Normal
Chinese speech already in the cache is reused. Screen boundaries come from each
recording's decoded duration, padded by less than one frame (40 ms), so audio and
video remain aligned without accumulating timing drift.

Outputs are `<topic-key>_video.mp4` and `video_manifest.json`, containing paragraph
timings, voice, rate, and font. Preview renders the first two blocks in a separate
`video-preview/` directory. Rendering files and temporary audio are removed;
reusable speech stays in `.podcast-cache/`. Existing completed videos are replaced
only after encoding succeeds. Audio podcast files and their manifest are preserved.
