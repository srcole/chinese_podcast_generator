import asyncio
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from podcast_generator.core import DEFAULTS
from podcast_generator.audio import append_silence, open_wave
from podcast_generator.video import (Block, find_font, generate_video, highlight_mask,
                                     layout, read_blocks, render_card)


class VideoTests(unittest.TestCase):
    def test_alignment_and_optional_pinyin(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'transcript.txt').write_text('你好。\n\n世界。')
            (folder / 'transcript_english.txt').write_text('Hello.\n\nWorld.')
            blocks = read_blocks(folder, DEFAULTS)
            self.assertEqual(blocks[0], Block('你好。', 'Hello.'))
            (folder / 'transcript_pinyin.txt').write_text('nǐ hǎo.\n\nshì jiè.')
            self.assertEqual(read_blocks(folder, DEFAULTS)[1].pinyin, 'shì jiè.')
            (folder / 'transcript_pinyin.txt').write_text('nǐ hǎo.')
            with self.assertRaisesRegex(ValueError, 'Paragraph counts'):
                read_blocks(folder, DEFAULTS)

    def test_literal_longest_highlights_and_repeated_words(self):
        self.assertEqual(highlight_mask('中国人中国 C++', ['中国', '中国人', 'C++']),
                         [True] * 5 + [False] + [True] * 3)
        self.assertEqual(highlight_mask('甲乙丙', ['甲乙', '乙丙']), [True, True, False])

    def test_layout_rejects_overflow(self):
        try:
            font = find_font()
            import PIL
        except (ValueError, ImportError):
            self.skipTest('Pillow and a CJK font required')
        with self.assertRaisesRegex(ValueError, 'too long'):
            layout(Block('中国' * 3000, 'English ' * 3000), font)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_render_timing_cleanup_and_failure_preserves_output(self):
        try:
            font = find_font()
            import PIL
        except (ValueError, ImportError):
            self.skipTest('Pillow and a CJK font required')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.wav'
            with open_wave(source) as audio:
                append_silence(audio, .213)
            config = copy.deepcopy(DEFAULTS)
            config['rates']['chinese'] = '+80%'
            synth = AsyncMock(return_value=source)
            blocks = [Block('你好中国。', 'Hello China.', 'nǐ hǎo zhōng guó.'),
                      Block('再见。', 'Goodbye.')]
            with patch('edge_tts.list_voices', AsyncMock(return_value=[{'ShortName': config['voices']['chinese']}])), \
                 patch('podcast_generator.video.synthesize', synth):
                target = asyncio.run(generate_video(blocks, ['中国'], config, root / 'out', root / 'cache', 'test', font))
                self.assertTrue(target.exists())
                self.assertEqual(synth.call_args_list[0].args[0].rate, '+0%')
                manifest = json.loads((target.parent / 'video_manifest.json').read_text())
                self.assertEqual(manifest['timeline'], [{'block': 1, 'start': 0, 'end': .24},
                                                        {'block': 2, 'start': .24, 'end': .48}])
                probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(target)]))
                video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
                self.assertEqual((video['width'], video['height']), (1920, 1080))
                self.assertAlmostEqual(float(video['duration']), .48, places=2)
                self.assertTrue(any(s['codec_type'] == 'audio' for s in probe['streams']))
                self.assertEqual(sorted(p.name for p in target.parent.iterdir()), ['test_video.mp4', 'video_manifest.json'])
                original = target.read_bytes()
                with patch('podcast_generator.video.ffmpeg', side_effect=RuntimeError('encoding failed')):
                    with self.assertRaisesRegex(RuntimeError, 'encoding failed'):
                        asyncio.run(generate_video(blocks, [], config, target.parent, root / 'cache', 'test', font))
                self.assertEqual(target.read_bytes(), original)
                self.assertFalse(list(target.parent.glob('.video-*')))


if __name__ == '__main__':
    unittest.main()
