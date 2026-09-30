import asyncio
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import wave

from podcast_generator.core import Speech, Silence, build_plan, load_config, read_transcript, read_vocabulary
from podcast_generator.audio import append_silence, append_wave, encode, ffmpeg, open_wave, synthesize, generate

ROOT = Path(__file__).resolve().parents[1]


class GeneratorTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg unavailable')
    def test_vocabulary_last_and_sections_survive_failure(self):
        for failure in ('vocabulary', 'combined', None):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / 'source.wav'
                with open_wave(source) as stream:
                    append_silence(stream, 0.1)
                names = ['vocabulary', 'chinese', 'english', 'chinese_slow']
                plan = [(name, [Speech(name, 'voice', '+0%')]) for name in names]
                calls = []
                async def fake_synthesize(speech, cache):
                    calls.append(speech.text)
                    if speech.text == 'vocabulary' and failure == 'vocabulary':
                        raise RuntimeError('vocabulary failed')
                    return source
                service = SimpleNamespace(list_voices=AsyncMock(return_value=[{'ShortName': 'voice'}]))
                output = root / 'custom-output'
                def fake_encode(source, destination):
                    if source.name == 'podcast.wav' and failure == 'combined':
                        raise RuntimeError('combined failed')
                    encode(source, destination)
                with patch.dict(sys.modules, {'edge_tts': service}), patch(
                    'podcast_generator.audio.synthesize', side_effect=fake_synthesize
                ), patch(
                    'podcast_generator.audio.encode', side_effect=fake_encode
                ), patch('podcast_generator.audio.append_wave', wraps=append_wave) as append:
                    job = generate(plan, load_config([]), output, root / 'cache', 'episode-id')
                    if failure:
                        with self.assertRaisesRegex(RuntimeError, f'{failure} failed'):
                            asyncio.run(job)
                    else:
                        asyncio.run(job)
                        combined_sources = [call.args[1].stem for call in append.call_args_list[-4:]]
                        self.assertEqual(combined_sources, [f'episode-id_{i:02d}_{name}' for i, name in enumerate(names, 1)])
                self.assertEqual(calls, ['chinese', 'english', 'chinese_slow', 'vocabulary'])
                for index, name in enumerate(names, 1):
                    part = output / f'episode-id_{index:02d}_{name}.mp3'
                    if failure and not (failure == 'vocabulary' and name == 'vocabulary'):
                        self.assertGreater(part.stat().st_size, 0)
                    else:
                        self.assertFalse(part.exists())
                self.assertEqual((output / 'episode-id_podcast.mp3').exists(), failure is None)
                if failure is None:
                    manifest = json.loads((output / 'manifest.json').read_text())
                    self.assertEqual(manifest['files'], ['episode-id_podcast.mp3'])

    def test_example_plan(self):
        config = load_config([ROOT / 'podcast.toml'])
        plan = build_plan(ROOT / 'inputs/20260921_1_tech_week', config)
        self.assertEqual([name for name, _ in plan], ['chinese_slow', 'vocabulary', 'interleaved'])
        self.assertEqual(plan[1][1][:4], [
            Speech('Tech Stew (podcast name)', 'en-US-AvaMultilingualNeural', '+100%'), Silence(0.05),
            Speech('科技乱炖', 'zh-CN-XiaoxiaoNeural', '+0%'), Silence(0.5)])
        self.assertEqual(sum(isinstance(s, Speech) and s.text == '量产' for s in plan[1][1]), 2)
        english = read_transcript(ROOT / 'inputs/20260921_1_tech_week/transcript_english.txt', config['podcast']['omit_lines'])
        chinese = read_transcript(ROOT / 'inputs/20260921_1_tech_week/transcript.txt', config['podcast']['omit_lines'])
        self.assertEqual(plan[2][1], [speech for en, zh in zip(english, chinese) for speech in (
            Speech(en, config['voices']['english'], '+100%'),
            Speech(zh, config['voices']['chinese'], '+0%'))])
        self.assertTrue(all(s.rate == '-20%' for s in plan[0][1]))

    def test_interleaved_lines_alignment_and_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'podcast.toml').write_text(
                '[podcast]\nsections = ["interleaved"]\n'
                '[rates]\nenglish = "+50%"\nchinese = "-10%"\n'
                '[voices]\nenglish = "en-voice"\nchinese = "zh-voice"\n')
            config = load_config([folder / 'podcast.toml'])
            (folder / 'transcript_english.txt').write_text(
                '# Title\n\nA roughly 20-minute solo podcast script\n\n---\nFirst.\nSecond.\n')
            (folder / 'transcript.txt').write_text('# 标题\n\n第一句。\n第二句。\n')
            self.assertEqual(build_plan(folder, config), [('interleaved', [
                Speech('Title', 'en-voice', '+50%'), Speech('标题', 'zh-voice', '-10%'),
                Speech('First.', 'en-voice', '+50%'), Speech('第一句。', 'zh-voice', '-10%'),
                Speech('Second.', 'en-voice', '+50%'), Speech('第二句。', 'zh-voice', '-10%'),
            ])])
            (folder / 'transcript.txt').write_text('只有一句。\n')
            with self.assertRaisesRegex(ValueError, 'matching nonempty spoken lines'):
                build_plan(folder, config)
            # Explicit separate sections remain supported for older configurations.
            (folder / 'podcast.toml').write_text('[podcast]\nsections = ["english", "chinese"]\n')
            self.assertEqual([name for name, _ in build_plan(folder, load_config([folder / 'podcast.toml']))],
                             ['english', 'chinese'])

    def test_interleaved_preview_keeps_two_complete_pairs(self):
        from podcast_generator.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'podcast.toml').write_text('[podcast]\nsections = ["interleaved"]\n')
            (folder / 'transcript.txt').write_text('一\n二\n三\n')
            (folder / 'transcript_english.txt').write_text('One\nTwo\nThree\n')
            with patch.object(sys, 'argv', ['podcast', str(folder), '--preview']), \
                 patch('podcast_generator.audio.generate', new_callable=AsyncMock) as render, \
                 patch('podcast_generator.cli.shutil.which', return_value='/bin/ffmpeg'), \
                 patch('builtins.print'):
                main()
            items = render.call_args.args[0][0][1]
            self.assertEqual([s.text for s in items], ['One', '一', 'Two', '二'])

    def test_notes_and_headings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'transcript.txt'
            path.write_text('\ufeff# Title\n\nA roughly 20-minute solo podcast script\n\n---\n\n**Opening**\n\nBody with 20-minute discussion.', encoding='utf-8')
            self.assertEqual(read_transcript(path, load_config([])['podcast']['omit_lines']),
                             ['Title', 'Opening', 'Body with 20-minute discussion.'])

    def test_csv_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'v.csv'
            path.write_text('chinese,english\n词,"word, term"\n', encoding='utf-8')
            self.assertEqual(read_vocabulary(path), [('词', 'word, term')])
            path.write_text('chinese,english\n词,word,term\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'malformed'):
                read_vocabulary(path)

    def test_overrides_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'podcast.toml'
            path.write_text('[rates]\nenglish = "+50%"\n')
            config = load_config([ROOT / 'podcast.toml', path])
            self.assertEqual(config['rates']['english'], '+50%')
            self.assertEqual(config['rates']['vocabulary'], '+25%')
            vocabulary = dict(build_plan(ROOT / 'inputs/20260921_1_tech_week', config))['vocabulary']
            self.assertEqual(vocabulary[0].rate, '+50%')
            self.assertEqual(vocabulary[2].rate, '+0%')
            for invalid in ['[rates]\nenglish = "-100%"', '[pauses]\nbetween_entries = -1', '[rates]\nenglis = "+5%"']:
                path.write_text(invalid)
                with self.assertRaises(ValueError):
                    load_config([path])

    def test_cache_reuse_and_rate_invalidation(self):
        calls = []
        class FakeCommunicate:
            def __init__(self, **kwargs):
                calls.append(kwargs)
            async def save(self, path):
                Path(path).write_bytes(b'fake audio')
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {'edge_tts': SimpleNamespace(Communicate=FakeCommunicate)}):
            cache = Path(tmp)
            first = asyncio.run(synthesize(Speech('你好', 'voice', '+0%'), cache))
            self.assertEqual(first, asyncio.run(synthesize(Speech('你好', 'voice', '+0%'), cache)))
            self.assertNotEqual(first, asyncio.run(synthesize(Speech('你好', 'voice', '-20%'), cache)))
            self.assertEqual(len(calls), 2)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg unavailable')
    def test_audio_assembly_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with open_wave(root / 'section.wav') as stream:
                append_silence(stream, 0.5)
            with open_wave(root / 'combined.wav') as stream:
                append_wave(stream, root / 'section.wav')
                append_silence(stream, 3)
                append_wave(stream, root / 'section.wav')
            encode(root / 'combined.wav', root / 'podcast.mp3')
            ffmpeg('-i', root / 'podcast.mp3', root / 'decoded.wav')
            with wave.open(str(root / 'decoded.wav')) as stream:
                self.assertAlmostEqual(stream.getnframes() / stream.getframerate(), 4.0, places=2)


if __name__ == '__main__':
    unittest.main()
