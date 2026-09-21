import asyncio
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
        for fail_vocabulary in (True, False):
            with self.subTest(fail_vocabulary=fail_vocabulary), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / 'source.wav'
                with open_wave(source) as stream:
                    append_silence(stream, 0.1)
                names = ['vocabulary', 'chinese', 'english', 'chinese_slow']
                plan = [(name, [Speech(name, 'voice', '+0%')]) for name in names]
                calls = []
                async def fake_synthesize(speech, cache):
                    calls.append(speech.text)
                    if speech.text == 'vocabulary' and fail_vocabulary:
                        raise RuntimeError('vocabulary failed')
                    return source
                service = SimpleNamespace(list_voices=AsyncMock(return_value=[{'ShortName': 'voice'}]))
                output = root / 'custom-output'
                with patch.dict(sys.modules, {'edge_tts': service}), patch(
                    'podcast_generator.audio.synthesize', side_effect=fake_synthesize
                ), patch('podcast_generator.audio.append_wave', wraps=append_wave) as append:
                    job = generate(plan, load_config([]), output, root / 'cache', 'episode-id')
                    if fail_vocabulary:
                        with self.assertRaisesRegex(RuntimeError, 'vocabulary failed'):
                            asyncio.run(job)
                    else:
                        asyncio.run(job)
                        combined_sources = [call.args[1].stem for call in append.call_args_list[-4:]]
                        self.assertEqual(combined_sources, [f'episode-id_{i:02d}_{name}' for i, name in enumerate(names, 1)])
                self.assertEqual(calls, ['chinese', 'english', 'chinese_slow', 'vocabulary'])
                for index, name in enumerate(names[1:], 2):
                    self.assertGreater((output / f'episode-id_{index:02d}_{name}.mp3').stat().st_size, 0)
                self.assertEqual((output / 'episode-id_podcast.mp3').exists(), not fail_vocabulary)

    def test_example_plan(self):
        config = load_config([ROOT / 'podcast.toml'])
        plan = build_plan(ROOT / 'inputs/20260921_1_tech_week', config)
        self.assertEqual([name for name, _ in plan], ['vocabulary', 'chinese', 'english', 'chinese_slow'])
        self.assertEqual(plan[0][1][:4], [
            Speech('科技乱炖', 'zh-CN-XiaoxiaoNeural', '+25%'), Silence(0.3),
            Speech('Tech Stew (podcast name)', 'en-US-AvaMultilingualNeural', '+25%'), Silence(0.6)])
        self.assertEqual(sum(isinstance(s, Speech) and s.text == '量产' for s in plan[0][1]), 2)
        self.assertTrue(all(s.rate == '+100%' for s in plan[2][1]))
        self.assertTrue(all(s.rate == '-20%' for s in plan[3][1]))

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
