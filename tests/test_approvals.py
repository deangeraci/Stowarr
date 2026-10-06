import base64
import concurrent.futures
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from approvals import ApprovalStore, fingerprint
from approval_web import make_handler


class StoreFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ApprovalStore(Path(self.tmp.name) / 'approvals.sqlite3')
        self.proposal = dict(identity_key='movie:1', title='<script>alert(1)</script>',
                             source_file_id='10', source_size_bytes=20_000_000_000,
                             release_id='hash1', release_title='1080p HEVC',
                             release_size_bytes=6_000_000_000, indexer_id='1')
        self.rid = self.store.propose(self.proposal)
        self.digest = fingerprint(self.proposal)

    def tearDown(self):
        self.tmp.cleanup()

    def approve(self):
        self.store.decide(self.rid, self.digest, 'approved', 'dean')

    def expire(self):
        with sqlite3.connect(self.store.path) as db:
            db.execute("UPDATE approval_requests SET expires_at='2000-01-01T00:00:00+00:00'")


class ApprovalTests(StoreFixture, unittest.TestCase):
    def test_duplicate_proposals_are_durable(self):
        other = ApprovalStore(self.store.path)
        self.assertEqual(other.propose(self.proposal), self.rid)
        self.approve()
        self.assertEqual(other.propose(self.proposal), self.rid)

    def test_unapproved_cannot_be_consumed(self):
        with self.assertRaises(ValueError):
            self.store.consume(self.rid, self.proposal)

    def test_expiry_blocks_decision_and_consumption(self):
        self.expire()
        self.assertEqual(self.store.list()[0]['status'], 'expired')
        with self.assertRaises(ValueError):
            self.approve()
        self.assertNotEqual(self.store.propose(self.proposal), self.rid)

    def test_approved_expiry_blocks_consumption(self):
        self.approve()
        self.expire()
        with self.assertRaises(ValueError):
            self.store.consume(self.rid, self.proposal)

    def test_every_snapshot_field_is_pinned(self):
        self.approve()
        for name in self.proposal:
            altered = self.proposal.copy()
            altered[name] = altered[name] + 1 if isinstance(altered[name], int) else altered[name] + '-changed'
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.store.consume(self.rid, altered)
        self.store.consume(self.rid, self.proposal)

    def test_reject_and_decision_replay_fail(self):
        self.store.decide(self.rid, self.digest, 'rejected', 'dean')
        with self.assertRaises(ValueError):
            self.approve()
        with self.assertRaises(ValueError):
            self.store.consume(self.rid, self.proposal)

    def test_concurrent_consumers_only_one_claim(self):
        self.approve()
        def consume(_):
            try:
                self.store.consume(self.rid, self.proposal)
                return True
            except ValueError:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(consume, range(4))), 1)
        with sqlite3.connect(self.store.path) as db:
            self.assertEqual([r[0] for r in db.execute('SELECT event FROM approval_events ORDER BY id')], ['proposed', 'approved', 'consumed'])

    def test_invalid_size_and_extra_secret_fields_rejected(self):
        for changes in [{'release_size_bytes': True}, {'release_size_bytes': 30_000_000_000}, {'api_key':'secret'}]:
            with self.assertRaises(ValueError):
                self.store.propose(dict(self.proposal, **changes))


class WebTests(StoreFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store, 'dean', 'test-password'))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.auth = 'Basic ' + base64.b64encode(b'dean:test-password').decode()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def request(self, method, path, body=None, authenticated=True):
        c = HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        headers = {'Content-Type':'application/x-www-form-urlencoded'}
        if authenticated:
            headers['Authorization'] = self.auth
        c.request(method, path, body, headers)
        r = c.getresponse()
        status, result = r.status, r.read()
        c.close()
        return status, result

    def test_auth_required_for_reads_and_writes(self):
        self.assertEqual(self.request('GET', '/api/requests', authenticated=False)[0], 401)
        self.assertEqual(self.request('POST', '/api/decision', 'x=y', False)[0], 401)

    def test_get_cannot_approve(self):
        self.assertEqual(self.request('GET', '/api/decision?id='+self.rid)[0], 404)
        self.assertEqual(self.store.list()[0]['status'], 'pending')

    def test_post_requires_csrf_and_pins_request(self):
        status, body = self.request('GET', '/api/requests')
        self.assertEqual(status, 200)
        data = json.loads(body)
        form = dict(id=self.rid, fingerprint=self.digest, decision='approved', csrf='wrong')
        self.assertEqual(self.request('POST', '/api/decision', urlencode(form))[0], 403)
        form['csrf'] = data['csrf']
        self.assertEqual(self.request('POST', '/api/decision', urlencode(form))[0], 200)
        self.assertEqual(self.request('POST', '/api/decision', urlencode(form))[0], 409)
        self.assertEqual(self.store.list()[0]['actor'], 'dean')

    def test_invalid_form_fails_without_mutation(self):
        self.assertEqual(self.request('POST', '/api/decision', 'id=a&id=b')[0], 409)
        self.assertEqual(self.store.list()[0]['status'], 'pending')


if __name__ == '__main__':
    unittest.main()
