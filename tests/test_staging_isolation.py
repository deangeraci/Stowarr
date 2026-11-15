import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from staging_isolation import IsolationError, validate_source_url, verify_replacement_isolation


class IsolationTests(unittest.TestCase):
    def setUp(self):
        if sys.platform == "win32":
            self.skipTest("container-path isolation tests require POSIX paths")

    def clients(self, category="stowarr-replacement", save_path=None, all_clients=None):
        radarr = Mock()
        response = Mock()
        response.json.return_value = {
            "id": 2,
            "fields": [{"name": "movieCategory", "value": "stowarr"}],
        }
        radarr.request.return_value = response
        qbit = Mock()
        qbit.categories.return_value = {category: {"savePath": save_path or "/data/replacements"}}
        return radarr, qbit

    def test_category_and_path_are_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            replacement = Path(tmp) / "replacements"
            root = Path(tmp) / "movies"
            replacement.mkdir(); root.mkdir()
            radarr, qbit = self.clients(save_path=str(replacement))
            path = verify_replacement_isolation(
                radarr, qbit, 2, "stowarr", "stowarr-replacement", str(replacement),
                ["/radarr/movies"], [{"id": 2, "enable": True,
                "fields": [{"name": "movieCategory", "value": "stowarr"}]}],
                {"/radarr/movies": str(root)})
            self.assertEqual(path, str(replacement.resolve()))

    def test_monitored_category_and_overlapping_path_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            replacement = Path(tmp) / "replacements"
            root = Path(tmp) / "movies"
            replacement.mkdir(); root.mkdir()
            for category, path in (("stowarr", str(replacement)),
                                   ("stowarr-replacement", str(root / "replacements")),
                                   ("stowarr-replacement", "")):
                with self.subTest(category=category, path=path):
                    radarr, qbit = self.clients(save_path=str(replacement))
                    with self.assertRaises(IsolationError):
                        verify_replacement_isolation(
                            radarr, qbit, 2, "stowarr", category, path,
                            [str(root)], [{"id": 2, "enable": True,
                            "fields": [{"name": "movieCategory", "value": "stowarr"}]}])

    def test_missing_precreated_category_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            replacement = Path(tmp) / "replacements"
            root = Path(tmp) / "media"
            replacement.mkdir(); root.mkdir()
            radarr, qbit = self.clients("other", save_path=str(replacement))
            with self.assertRaises(IsolationError):
                verify_replacement_isolation(
                    radarr, qbit, 2, "stowarr", "stowarr-replacement",
                    str(replacement), [str(root)], [{"id": 2, "enable": True,
                    "fields": [{"name": "movieCategory", "value": "stowarr"}]}])

    def test_other_enabled_radarr_client_using_replacement_category_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            replacement = Path(tmp) / "replacements"; root = Path(tmp) / "media"
            replacement.mkdir(); root.mkdir()
            radarr, qbit = self.clients(save_path=str(replacement))
            with self.assertRaises(IsolationError):
                verify_replacement_isolation(
                    radarr, qbit, 2, "stowarr", "stowarr-replacement", str(replacement),
                    [str(root)], [{"id": 2, "enable": True,
                    "fields": [{"name": "movieCategory", "value": "stowarr"}]},
                    {"id": 7, "enable": True,
                    "fields": [{"name": "movieCategory", "value": "stowarr-replacement"}]}])

    def test_category_save_path_and_symlink_overlap_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "media"; root.mkdir()
            alias = Path(tmp) / "alias"; alias.symlink_to(root, target_is_directory=True)
            replacement = Path(tmp) / "replacements"; replacement.mkdir()
            radarr, qbit = self.clients(save_path=str(replacement))
            with self.assertRaises(IsolationError):
                verify_replacement_isolation(
                    radarr, qbit, 2, "stowarr", "stowarr-replacement", str(replacement),
                    [str(alias)], [{"id": 2, "enable": True,
                    "fields": [{"name": "movieCategory", "value": "stowarr"}]}])
            qbit.categories.return_value = {"stowarr-replacement": {"savePath": str(root)}}
            with self.assertRaises(IsolationError):
                verify_replacement_isolation(
                    radarr, qbit, 2, "stowarr", "stowarr-replacement", str(replacement),
                    [str(root)], [{"id": 2, "enable": True,
                    "fields": [{"name": "movieCategory", "value": "stowarr"}]}])

    def test_release_url_validation_rejects_credentials_and_unknown_schemes(self):
        self.assertTrue(validate_source_url("magnet:?xt=urn:btih:" + "a" * 40))
        for url in ("", "ftp://example/release", "https://user:pass@example/release"):
            with self.assertRaises(IsolationError):
                validate_source_url(url)


if __name__ == "__main__":
    unittest.main()
