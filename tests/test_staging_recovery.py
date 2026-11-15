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
        store.propose_recovery.assert_called_once_with("r1")

    def test_ambiguous_outcome_never_recovery_retries(self):
        store, qbit, result = self.run_case("removed", event="")
        self.assertEqual(result[0][1], "ambiguous")
        store.propose_recovery.assert_not_called()


if __name__ == "__main__":
    unittest.main()
