import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from clients import QbitTorrentClient, ServiceClient


class QbitClientTests(unittest.TestCase):
    def response(self, status=200, rows=None):
        response = Mock(status_code=status)
        response.json.return_value = rows or [{"hash": "a" * 40, "state": "downloading"}]
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
        session.post.return_value = self.response()
        session.get.return_value = self.response()
        client = QbitTorrentClient("http://gluetun:8090", username_env="QBIT_USER",
                                   password_env="QBIT_PASS", session=session)
        client.state("a" * 40)
        client.state("a" * 40)
        session.post.assert_called_once_with(
            "http://gluetun:8090/api/v2/auth/login",
            data={"username": "operator", "password": "secret"}, timeout=30)

    def test_service_client_keeps_connectivity_test(self):
        client = ServiceClient("radarr", "http://radarr")
        with patch("clients.requests.get") as get:
            get.return_value = self.response()
            self.assertTrue(client.connectivity_test().ok)


if __name__ == "__main__":
    unittest.main()
