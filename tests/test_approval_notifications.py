import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from approval_notifications import NoRedirect, notify


class NotificationTests(unittest.TestCase):
    proposal = dict(title='Movie', release_title='Release', source_size_bytes=20, release_size_bytes=6)

    def test_disabled_needs_no_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            notify('request', self.proposal)

    def test_unknown_provider_and_unsafe_urls_fail(self):
        for env in [
            {'STOWARR_NOTIFY_CHANNELS':'unknown'},
            {'STOWARR_NOTIFY_CHANNELS':'webhook','STOWARR_APPROVAL_URL':'https://user:secret@example.test'},
            {'STOWARR_NOTIFY_CHANNELS':'webhook','STOWARR_APPROVAL_URL':'https://private.test','STOWARR_WEBHOOK_URL':'http://public.test'},
        ]:
            with patch.dict(os.environ, env, clear=True), self.assertRaises(ValueError):
                notify('request', self.proposal)

    def test_redirect_cannot_forward_bearer(self):
        request = Request('https://one.test', headers={'Authorization':'Bearer secret'})
        self.assertIsNone(NoRedirect().redirect_request(request, None, 302, 'redirect', {}, 'https://two.test'))
