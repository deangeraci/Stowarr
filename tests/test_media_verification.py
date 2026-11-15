import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from media_verification import VerificationError, verify_media


class MediaVerificationTests(unittest.TestCase):
    def test_probe_decode_and_digest_are_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "candidate.mkv"
            media.write_bytes(b"fixture-media")
            before = media.read_bytes()
            probe = Mock(stdout=json.dumps({
                "format": {"duration": "121.5"},
                "streams": [{"codec_type": "video", "codec_name": "hevc", "height": 1080}],
            }))
            decode = Mock(stdout="")
            with patch("media_verification.subprocess.run", side_effect=[probe, decode]) as run:
                manifest = verify_media(media, expected_size=len(before))
            self.assertEqual(media.read_bytes(), before)
            self.assertEqual(manifest["video_height"], 1080)
            self.assertEqual(run.call_count, 2)
            decode_args = run.call_args_list[1].args[0]
            self.assertIn("-threads", decode_args)
            self.assertEqual(decode_args[decode_args.index("-threads") + 1], "1")
            self.assertLessEqual(run.call_args_list[1].kwargs["timeout"], 1800)

    def test_size_limit_fails_before_ffmpeg(self):
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "candidate.mkv"
            media.write_bytes(b"fixture-media")
            with patch("media_verification.subprocess.run") as run:
                with self.assertRaisesRegex(VerificationError, "size limit"):
                    verify_media(media, max_bytes=1)
            run.assert_not_called()

    def test_invalid_codec_or_corrupt_probe_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "candidate.mkv"
            media.write_bytes(b"fixture-media")
            probe = Mock(stdout=json.dumps({
                "format": {"duration": "121.5"},
                "streams": [{"codec_type": "video", "codec_name": "h264", "height": 1080}],
            }))
            with patch("media_verification.subprocess.run", return_value=probe):
                with self.assertRaises(VerificationError):
                    verify_media(media, expected_size=len(media.read_bytes()))


if __name__ == "__main__":
    unittest.main()
