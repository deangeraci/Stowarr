import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from staging_reconciliation import reconcile_attempts


class RecoveryTests(unittest.TestCase):
    def attempt(self, rid="r1", release="a" * 40):
        return {"request_id": rid, "release_id": release,
                "snapshot": json.dumps({"identity_key": "movie:radarr:15"})}

    def response(self, records):
        response = Mock()
        response.json.return_value = {"totalRecords": len(records), "records": records}
        return response

    def record(self, event, release="a" * 40):
        return {"movieId": 15, "eventType": event, "downloadId": release,
                "data": {"torrentInfoHash": release}}

    def run_case(self, qbit_state, event="grabbed"):
        store = Mock()
        store.list_staging_attempts.return_value = [self.attempt()]
        radarr = Mock()
        radarr.request.return_value = self.response([self.record(event)])
        qbit = Mock()
        qbit.state.return_value = qbit_state
        return store, qbit, reconcile_attempts(store, radarr, qbit)

    def test_confirmed_attempt_is_monitored_through_terminal_import(self):
        store = Mock()
        attempt = self.attempt()
        attempt.update({"status": "confirmed", "lifecycle_status": "downloading",
                        "recovery_request_id": None})
        terminal = dict(attempt, lifecycle_status="imported")
        store.list_staging_attempts.side_effect = [[attempt], [attempt], [attempt], [terminal]]
        radarr = Mock()
        radarr.request.return_value = self.response([self.record("grabbed")])
        qbit = Mock()
        qbit.state.side_effect = ["downloading", "stalledDL", "removed"]
        self.assertEqual(reconcile_attempts(store, radarr, qbit)[0][1], "downloading")
        self.assertEqual(reconcile_attempts(store, radarr, qbit)[0][1], "stalled")
        radarr.request.return_value = self.response([self.record("downloadFolderImported")])
        self.assertEqual(reconcile_attempts(store, radarr, qbit)[0][1], "imported")
        # Once imported, the next pass does not query Radarr/qBittorrent.
        self.assertEqual(reconcile_attempts(store, radarr, qbit), [])

    def test_missing_uses_fresh_candidate_and_is_at_most_once(self):
        store = Mock()
        store.list_staging_attempts.side_effect = [
            [self.attempt()],
            [dict(self.attempt(), lifecycle_status="missing", recovery_request_id="new")],
        ]
        radarr = Mock()
        radarr.request.return_value = self.response([self.record("grabbed")])
        qbit = Mock()
        qbit.state.return_value = "removed"
        fresh = {"identity_key": "movie:radarr:15", "title": "New", "source_file_id": "2",
                 "source_size_bytes": 20, "release_id": "b" * 40, "release_title": "New",
                 "release_size_bytes": 10, "indexer_id": "1"}
        factory = Mock(return_value=fresh)
        reconcile_attempts(store, radarr, qbit, recovery_factory=factory)
        factory.assert_called_once()
        store.propose_recovery.assert_called_once_with("r1", fresh)
        reconcile_attempts(store, radarr, qbit, recovery_factory=factory)
        self.assertEqual(factory.call_count, 1)

    def test_recovery_lineage_excludes_a_after_a_to_b(self):
        store = Mock()
        store.list_staging_attempts.return_value = [self.attempt("b-request", "b" * 40)]
        store.attempted_release_ids.return_value = {"a" * 40, "b" * 40}
        radarr = Mock()
        radarr.request.return_value = self.response([self.record("grabbed", "b" * 40)])
        qbit = Mock()
        qbit.state.return_value = "removed"
        factory = Mock(return_value=None)
        result = reconcile_attempts(store, radarr, qbit, recovery_factory=factory)
        self.assertEqual(result[0][1], "missing")
        factory.assert_called_once()
        self.assertEqual(factory.call_args.args[0]["excluded_release_ids"],
                         {"a" * 40, "b" * 40})
        store.propose_recovery.assert_not_called()

    def test_downloading_and_stalled_are_observable_without_mutation(self):
        store, qbit, result = self.run_case("downloading")
        self.assertEqual(result[0][1], "downloading")
        self.assertEqual(store.update_staging.call_args.kwargs["lifecycle_status"], "downloading")
        store, qbit, result = self.run_case("stalledDL")
        self.assertEqual(result[0][1], "stalled")

    def test_imported_and_failed_are_terminal(self):
        store, qbit, result = self.run_case("downloading", "downloadFolderImported")
        self.assertEqual(result[0][1], "imported")
        self.assertEqual(store.update_staging.call_args.args[1], "confirmed")
        store, qbit, result = self.run_case("downloading", "downloadFailed")
        self.assertEqual(result[0][1], "failed")
        self.assertEqual(store.update_staging.call_args.args[1], "failed")
        qbit.state.assert_not_called()

    def test_removed_download_gets_one_fresh_approval(self):
        store, qbit, result = self.run_case("removed")
        self.assertEqual(result[0][1], "missing")
        store.propose_recovery.assert_not_called()

    def test_missing_with_no_different_candidate_stays_missing(self):
        store = Mock()
        store.list_staging_attempts.return_value = [self.attempt()]
        radarr = Mock()
        radarr.request.return_value = self.response([self.record("grabbed")])
        qbit = Mock()
        qbit.state.return_value = "removed"
        factory = Mock(return_value=None)
        result = reconcile_attempts(store, radarr, qbit, recovery_factory=factory)
        self.assertEqual(result[0][1], "missing")
        factory.assert_called_once()
        store.propose_recovery.assert_not_called()

    def test_ambiguous_outcome_never_recovery_retries(self):
        store, qbit, result = self.run_case("removed", event="")
        self.assertEqual(result[0][1], "ambiguous")
        store.propose_recovery.assert_not_called()

    def test_direct_qbit_restart_recovery_skips_radarr_import_history(self):
        store = Mock()
        attempt = self.attempt()
        attempt.update({
            "status": "confirmed", "lifecycle_status": "downloading",
            "staging_category": "stowarr-replacement",
            "torrent_hash": "a" * 40,
            "download_path": "/data/replacements",
        })
        store.list_staging_attempts.return_value = [attempt]
        radarr = Mock()
        qbit = Mock()
        qbit.info.return_value = {
            "hash": "a" * 40, "state": "uploading", "progress": 1,
            "amount_left": 0, "category": "stowarr-replacement",
            "content_path": "/data/replacements/movie.mkv",
        }
        result = reconcile_attempts(store, radarr, qbit)
        self.assertEqual(result[0][1], "complete_unverified")
        radarr.request.assert_not_called()
        store.update_staging.assert_called_once()
        self.assertEqual(store.update_staging.call_args.kwargs["lifecycle_status"],
                         "complete_unverified")

    def test_uncertain_direct_submission_is_not_retried_when_hash_is_absent(self):
        store = Mock()
        attempt = self.attempt()
        attempt.update({
            "status": "uncertain", "lifecycle_status": "submitting",
            "staging_category": "stowarr-replacement", "torrent_hash": "a" * 40,
            "download_path": "/data/replacements",
        })
        store.list_staging_attempts.return_value = [attempt]
        radarr = Mock()
        qbit = Mock()
        qbit.info.return_value = None
        qbit.state.return_value = "removed"
        factory = Mock()
        result = reconcile_attempts(store, radarr, qbit, recovery_factory=factory)
        self.assertEqual(result[0][1], "ambiguous")
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
