"""Executes database/sql/schema.sql and queries.sql against in-memory SQLite."""

import re
import sqlite3
import unittest

from helpers import BACKEND

SQL_DIR = BACKEND.parent / "database" / "sql"


def load_queries() -> dict[str, str]:
    text = (SQL_DIR / "queries.sql").read_text()
    blocks = re.split(r"^-- name: (\w+)\s*$", text, flags=re.M)
    return {blocks[i]: blocks[i + 1].strip() for i in range(1, len(blocks), 2)}


class SqlTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript((SQL_DIR / "schema.sql").read_text())
        self.q = load_queries()
        ins = "INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?,?,?,?)"
        self.db.execute(ins, ("ds1", "a", "f1.csv", "h1", 10, 3, 100, 1, "{}", "2026-01-01", "2026-02-01"))
        self.db.execute(ins, ("ds2", "b", "f2.csv", "h1", 10, 3, 100, 0, "{}", "2026-01-05", None))
        self.db.execute(ins, ("ds3", "c", "f3.csv", "h3", 10, 3, 100, 0, "{}", "2026-01-06", "2099-01-01"))
        exp = "INSERT INTO experiments (id,dataset_id,target,task,status,seed,dataset_fingerprint,config_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)"
        for row in [
            ("e1", "ds1", "churned", "binary", "succeeded", 1, "fp", "{}", "2026-01-02"),
            ("e2", "ds1", "churned", "binary", "failed", 1, "fp", "{}", "2026-01-03"),
            ("e3", "ds1", "spend", "regression", "running", 1, "fp", "{}", "2026-01-04"),
        ]:
            self.db.execute(exp, row)
        mdl = "INSERT INTO models VALUES (?,?,?,?,?,?,?,?,?)"
        self.db.execute(mdl, ("m1", "e1", "random_forest", "binary", "churned", "m1.joblib", "x", "{}", "2026-01-02"))
        self.db.execute("INSERT INTO prediction_events VALUES (?,?,?,?,?,?)", ("p1", "m1", 5, "h", "{}", "2026-01-10"))
        self.db.execute("INSERT INTO prediction_events VALUES (?,?,?,?,?,?)", ("p2", "m1", 7, "h", "{}", "2026-01-11"))
        self.db.execute("INSERT INTO audit_events (occurred_at,actor,action,resource_type,resource_id) VALUES (?,?,?,?,?)", ("2026-01-02", "u", "train", "experiment", "e1"))
        self.db.commit()

    def run_q(self, name, **params):
        return self.db.execute(self.q[name], params).fetchall()

    def test_all_queries_load(self):
        self.assertEqual(len(self.q), 7)

    def test_status_counts(self):
        rows = self.run_q("experiment_status_counts_by_dataset", dataset_id="ds1")
        self.assertEqual({(r[2], r[3]) for r in rows}, {("succeeded", 1), ("failed", 1), ("running", 1)})

    def test_expired_and_duplicates_and_latest(self):
        self.assertEqual([r[0] for r in self.run_q("expired_datasets", now="2026-03-01")], ["ds1"])
        self.assertEqual(self.run_q("duplicate_uploads")[0][:2], ("h1", 2))
        self.assertEqual(self.run_q("latest_model_per_target")[0][:2], ("churned", "m1"))

    def test_prediction_volume_and_audit_and_stuck(self):
        vol = self.run_q("prediction_volume_by_model", since="2026-01-01", until="2026-02-01")
        self.assertEqual(vol[0][2:], (2, 12))
        self.assertEqual(self.run_q("audit_trail_for_resource", resource_type="experiment", resource_id="e1")[0][2], "train")
        self.assertEqual([r[0] for r in self.run_q("stuck_experiments", older_than="2026-02-01")], ["e3"])

    def test_injection_payload_is_treated_as_data(self):
        payload = "x'; DROP TABLE datasets; --"
        self.assertEqual(self.run_q("experiment_status_counts_by_dataset", dataset_id=payload), [])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM datasets").fetchone()[0], 3)

    def test_constraints_reject_bad_rows(self):
        bad = [
            "INSERT INTO experiments (id,dataset_id,target,status,seed,dataset_fingerprint,config_json,created_at) VALUES ('z','ds1','t','weird',1,'f','{}','2026')",
            "INSERT INTO experiments (id,dataset_id,target,status,seed,dataset_fingerprint,config_json,created_at) VALUES ('z','nope','t','queued',1,'f','{}','2026')",
            "INSERT INTO datasets VALUES ('d9','n','f1.csv','h',1,1,1,0,'{}','2026',NULL)",  # duplicate stored_filename
            "INSERT INTO prediction_events VALUES ('p9','m1',0,'h','{}','2026')",
        ]
        for stmt in bad:
            with self.subTest(stmt[:40]), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(stmt)

    def test_cascade_delete_removes_dependents(self):
        self.db.execute("DELETE FROM datasets WHERE id='ds1'")
        for table in ("experiments", "models", "prediction_events"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)


if __name__ == "__main__":
    unittest.main()
