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
and two blocks from each transcript into a separate `preview/` subfolder.

Outputs in `outputs/<input-folder-name>/`:

- `<podcast-id>_01_chinese_slow.mp3`: Chinese at -20%.
- `<podcast-id>_02_vocabulary.mp3`: Chinese term then complete English meaning, both +25%.
- `<podcast-id>_03_english.mp3`: English at +100%.
- `<podcast-id>_04_chinese.mp3`: normal Chinese.
- `<podcast-id>_podcast.mp3`: the combined episode.
- `manifest.json`: effective settings and output filenames.

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

`podcast.sections` can reorder or omit the four supported sections.
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
fails. Combined playback order still follows `podcast.sections` (slow Chinese, vocabulary, English, then Chinese
by default). Each MP3 filename starts with the input folder name, even when using
`--output` or `--preview`. Reruns replace matching filenames; obsolete files from
changed section orders are not automatically removed. Do not run concurrent jobs
into the same output directory.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests do not contact the speech service. Audio integration tests require FFmpeg.
