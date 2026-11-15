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
        response.cookies = cookiejar_from_dict({})
        response.json.return_value = rows or [{"hash": "a" * 40, "state": "downloading"}]
        return response

    def login_response(self, status=200, body="Ok.", cookie="SID"):
        response = self.response(status)
        response.text = body
        response.cookies = cookiejar_from_dict({cookie: "fixture"})
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
    def test_configured_auth_logs_in_and_reuses_session_cookie(self):
        session = Mock()
        session.post.return_value = self.login_response()
        version = self.response()
        version.text = "v4.6.7"
        session.get.side_effect = [version, self.response(), self.response()]
        client = QbitTorrentClient("http://gluetun:8090", username_env="QBIT_USER",
                                   password_env="QBIT_PASS", session=session)
        client.state("a" * 40)
        client.state("a" * 40)
        session.post.assert_called_once_with(
            "http://gluetun:8090/api/v2/auth/login",
            data={"username": "operator", "password": "secret"},
            timeout=30, allow_redirects=False)

    @patch.dict(os.environ, {"QBIT_USER": "operator", "QBIT_PASS": "secret"}, clear=False)
    def test_qbittorrent_52_empty_login_uses_qbt_sid_cookie(self):
        session = Mock()
        session.post.return_value = self.login_response(204, "", "QBT_SID_8090")
        version = self.response()
        version.text = "v5.2.4"
        session.get.side_effect = [version, self.response()]
        client = QbitTorrentClient("http://gluetun:8090", username_env="QBIT_USER",
                                   password_env="QBIT_PASS", session=session)
        self.assertEqual(client.state("a" * 40), "downloading")
        self.assertTrue(client.authenticated)

    @patch.dict(os.environ, {"QBIT_USER": "operator", "QBIT_PASS": "secret"}, clear=False)
    def test_authentication_failures_are_rejected(self):
        for status, body, cookie in (
            (401, "Fails.", "SID"),
            (403, "Ok.", "SID"),
            (204, "", "unrelated"),
        ):
            with self.subTest(status=status, cookie=cookie):
                session = Mock()
                session.post.return_value = self.login_response(status, body, cookie)
                client = QbitTorrentClient("http://gluetun:8090", username_env="QBIT_USER",
                                           password_env="QBIT_PASS", session=session)
                with self.assertRaisesRegex(requests.RequestException, "login failed"):
                    client.state("a" * 40)
                session.get.assert_not_called()

    @patch.dict(os.environ, {"QBIT_USER": "operator", "QBIT_PASS": "secret"}, clear=False)
    def test_add_torrent_uses_replacement_category_and_path(self):
        session = Mock()
        session.post.side_effect = [self.login_response() , self.response()]
        version = self.response()
        version.text = "v5.2.4"
        session.get.return_value = version
        client = QbitTorrentClient("http://gluetun:8090", username_env="QBIT_USER",
                                   password_env="QBIT_PASS", session=session)
        client.add_torrent("magnet:?xt=urn:btih:" + "a" * 40,
                           "stowarr-replacement", "/data/replacements")
        self.assertEqual(session.post.call_args.args[0],
                         "http://gluetun:8090/api/v2/torrents/add")
        self.assertEqual(session.post.call_args.kwargs["data"]["category"],
                         "stowarr-replacement")
        self.assertEqual(session.post.call_args.kwargs["data"]["savepath"],
                         "/data/replacements")

    @patch.dict(os.environ, {"QBIT_USER": "operator", "QBIT_PASS": "secret"}, clear=False)
    def test_failed_200_login_does_not_authenticate(self):
        session = Mock()
        failed = self.response()
        failed.text = "Fails."
        failed.cookies = cookiejar_from_dict({"SID": "fixture"})
        session.post.return_value = failed
        client = QbitTorrentClient("http://gluetun:8090", username_env="QBIT_USER",
                                   password_env="QBIT_PASS", session=session)
        with self.assertRaisesRegex(requests.RequestException, "login failed"):
            client.state("a" * 40)
        self.assertFalse(client.authenticated)
        session.get.assert_not_called()

    def test_service_client_keeps_connectivity_test(self):
        client = ServiceClient("radarr", "http://radarr")
        with patch("clients.requests.get") as get:
            get.return_value = self.response()
            self.assertTrue(client.connectivity_test().ok)


if __name__ == "__main__":
    unittest.main()
