import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from requests.cookies import cookiejar_from_dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from clients import QbitTorrentClient, ServiceClient


class QbitClientTests(unittest.TestCase):
    def response(self, status=200, rows=None):
        response = Mock(status_code=status)
        response.text = "Ok."
        response.json.return_value = rows or [{"hash": "a" * 40, "state": "downloading"}]
        return response

    def login_response(self, status, body, cookies):
        response = self.response(status)
        response.text = body
        response.cookies = cookiejar_from_dict(cookies)
        return response

    def test_production_endpoint_category_and_no_mutation(self):
        session = Mock()
        session.get.return_value = self.response()
        client = QbitTorrentClient("http://gluetun:8090", "stowarr", session=session)
        self.assertEqual(client.state("A" * 40), "downloading")
        session.get.assert_called_once_with(
            "http://gluetun:8090/api/v2/torrents/info",
            params={"hashes": "A" * 40, "category": "stowarr"}, timeout=30)
        session.post.assert_not_called()

    @patch.dict(os.environ, {"QBIT_USER": "operator", "QBIT_PASS": "secret"}, clear=False)
    def test_configured_auth_verifies_legacy_and_new_sessions_once(self):
        for status, body, cookie, version_text in (
            (200, "Ok.", "SID", "v4.6.7"),
            (204, "", "QBT_SID_8090", "v5.2.4"),
        ):
            with self.subTest(status=status):
                session = Mock()
                session.post.return_value = self.login_response(status, body, {cookie: "fixture"})
                version = self.response()
                version.text = version_text
                session.get.side_effect = [version, self.response(), self.response()]
                client = QbitTorrentClient("http://gluetun:8090", username_env="QBIT_USER",
                                           password_env="QBIT_PASS", session=session)
                self.assertEqual(client.state("a" * 40), "downloading")
                self.assertEqual(client.state("a" * 40), "downloading")
                self.assertTrue(client.authenticated)
                session.post.assert_called_once_with(
                    "http://gluetun:8090/api/v2/auth/login",
                    data={"username": "operator", "password": "secret"},
                    timeout=30, allow_redirects=False)
                self.assertEqual(session.get.call_count, 3)
                self.assertEqual(session.get.call_args_list[0].args,
                                 ("http://gluetun:8090/api/v2/app/version",))
                self.assertEqual(session.get.call_args_list[0].kwargs,
                                 {"timeout": 30, "allow_redirects": False})

    @patch.dict(os.environ, {"QBIT_USER": "operator", "QBIT_PASS": "secret"}, clear=False)
    def test_failed_login_does_not_authenticate(self):
        for status, body, cookies in (
            (200, "Fails.", {"SID": "fixture"}),
            (200, "Ok.", {}),
            (204, "", {}),
            (204, "", {"unrelated": "fixture"}),
            (204, "", {"QBT_SID_8090": ""}),
            (204, "Fails.", {"QBT_SID_8090": "fixture"}),
            (401, "Ok.", {"SID": "fixture"}),
            (403, "Ok.", {"SID": "fixture"}),
            (307, "Ok.", {"SID": "fixture"}),
        ):
            with self.subTest(status=status, body=body):
                session = Mock()
                session.cookies = cookiejar_from_dict({"SID": "stale"})
                session.post.return_value = self.login_response(status, body, cookies)
                client = QbitTorrentClient("http://gluetun:8090", username_env="QBIT_USER",
                                           password_env="QBIT_PASS", session=session)
                with self.assertRaisesRegex(requests.RequestException, "login failed"):
                    client.state("a" * 40)
                self.assertFalse(client.authenticated)
                session.get.assert_not_called()

    @patch.dict(os.environ, {"QBIT_USER": "operator", "QBIT_PASS": "secret"}, clear=False)
    def test_failed_session_probe_blocks_torrent_reads(self):
        for status, body in ((401, ""), (403, ""), (302, ""), (200, "<html>Login</html>")):
            with self.subTest(status=status, body=body):
                session = Mock()
                session.post.return_value = self.login_response(204, "", {"QBT_SID_8090": "fixture"})
                session.get.return_value = self.response(status)
                session.get.return_value.text = body
                client = QbitTorrentClient("http://gluetun:8090", username_env="QBIT_USER",
                                           password_env="QBIT_PASS", session=session)
                with self.assertRaisesRegex(requests.RequestException, "session verification failed"):
                    client.state("a" * 40)
                self.assertFalse(client.authenticated)
                session.get.assert_called_once_with(
                    "http://gluetun:8090/api/v2/app/version", timeout=30, allow_redirects=False)

    def test_service_client_keeps_connectivity_test(self):
        client = ServiceClient("radarr", "http://radarr")
        with patch("clients.requests.get") as get:
            get.return_value = self.response()
            self.assertTrue(client.connectivity_test().ok)


if __name__ == "__main__":
    unittest.main()
