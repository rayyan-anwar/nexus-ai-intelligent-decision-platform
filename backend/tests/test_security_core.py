import json
import logging
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from helpers import BACKEND  # noqa: F401
from app.core.config import Settings
from app.core.logging import JsonFormatter, redact
from app.security.files import display_name, new_stored_name, resolve_inside, write_atomic
from app.security.ratelimit import RateLimiter
from app.security.tokens import authenticate, generate_token, hash_token, parse_bearer
from app.services.retention import compute_expiry, is_expired


class ConfigTests(unittest.TestCase):
    def test_defaults_are_local_friendly(self):
        s = Settings.from_env({})
        self.assertFalse(s.auth_required)
        self.assertEqual(s.problems(), [])
        self.assertEqual(s.retention_days, 30)

    def test_production_requires_tokens_cors_and_postgres(self):
        s = Settings.from_env({"NEXUS_ENV": "production"})
        problems = " ".join(s.problems())
        self.assertIn("TOKEN_HASHES", problems)
        self.assertIn("PostgreSQL", problems)
        bad = Settings.from_env({"NEXUS_ENV": "production", "NEXUS_CORS_ORIGINS": "*", "NEXUS_API_TOKEN_HASHES": hash_token("x"),
                                 "NEXUS_DATABASE_URL": "postgresql+psycopg://u:p@h/db"})
        self.assertEqual(len(bad.problems()), 1)
        self.assertIn("wildcard", bad.problems()[0])
        ok = Settings.from_env({"NEXUS_ENV": "production", "NEXUS_API_TOKEN_HASHES": hash_token("x"),
                                "NEXUS_DATABASE_URL": "postgresql+psycopg://u:p@h/db"})
        self.assertEqual(ok.problems(), [])
        self.assertTrue(ok.auth_required)

    def test_tokens_force_auth_even_in_development(self):
        self.assertTrue(Settings.from_env({"NEXUS_API_TOKEN_HASHES": hash_token("t")}).auth_required)

    def test_invalid_values_rejected(self):
        with self.assertRaises(ValueError):
            Settings.from_env({"NEXUS_MAX_UPLOAD_MB": "abc"})
        with self.assertRaises(ValueError):
            Settings.from_env({"NEXUS_RETENTION_DAYS": "-1"})
        self.assertTrue(Settings.from_env({"NEXUS_API_TOKEN_HASHES": "not-a-hash"}).problems())

    def test_database_password_is_masked(self):
        s = Settings.from_env({"NEXUS_DATABASE_URL": "postgresql+psycopg://user:hunter2@db:5432/nexus"})
        self.assertNotIn("hunter2", s.safe_database_url)
        self.assertIn("***", s.safe_database_url)


class LoggingTests(unittest.TestCase):
    def test_redaction(self):
        out = redact({"user": "a", "Authorization": "Bearer abc", "nested": {"api_key": "k", "ok": 1}, "list": [{"password": "p"}]})
        self.assertEqual(out["user"], "a")
        self.assertEqual(out["Authorization"], "***")
        self.assertEqual(out["nested"], {"api_key": "***", "ok": 1})
        self.assertEqual(out["list"], [{"password": "***"}])

    def test_formatter_emits_json_and_masks_extras(self):
        rec = logging.LogRecord("t", logging.INFO, __file__, 1, "hello %s", ("w",), None)
        rec.token = "secret-value"
        rec.dataset_id = "ds1"
        data = json.loads(JsonFormatter().format(rec))
        self.assertEqual(data["message"], "hello w")
        self.assertEqual(data["token"], "***")
        self.assertEqual(data["dataset_id"], "ds1")
        self.assertNotIn("secret-value", json.dumps(data))


class TokenTests(unittest.TestCase):
    def test_authentication_roles(self):
        user, admin = generate_token(), generate_token()
        uh, ah = [hash_token(user)], [hash_token(admin)]
        self.assertEqual(authenticate(f"Bearer {user}", uh, ah).role, "user")
        self.assertEqual(authenticate(f"bearer {admin}", uh, ah).role, "admin")
        for bad in (None, "", "Bearer", "Bearer wrong", f"Basic {user}", "Bearer " + "x" * 600):
            self.assertIsNone(authenticate(bad, uh, ah))

    def test_parse_bearer(self):
        self.assertEqual(parse_bearer("Bearer abc"), "abc")
        self.assertIsNone(parse_bearer("Token abc"))

    def test_tokens_are_unique_and_long(self):
        a, b = generate_token(), generate_token()
        self.assertNotEqual(a, b)
        self.assertGreaterEqual(len(a), 40)


class RateLimiterTests(unittest.TestCase):
    def test_limit_window_and_keys(self):
        now = [0.0]
        rl = RateLimiter(3, 60, clock=lambda: now[0])
        self.assertTrue(all(rl.check("a")[0] for _ in range(3)))
        allowed, retry = rl.check("a")
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry, 1)
        self.assertTrue(rl.check("b")[0])
        now[0] = 61.0
        self.assertTrue(rl.check("a")[0])

    def test_disabled_and_bounded_memory(self):
        self.assertTrue(RateLimiter(0).check("x")[0])
        rl = RateLimiter(1, 60, max_keys=10)
        for i in range(100):
            rl.check(f"k{i}")
        self.assertLessEqual(len(rl._hits), 10)


class FileTests(unittest.TestCase):
    def test_display_name_strips_paths_and_junk(self):
        self.assertEqual(display_name("../../etc/passwd"), "passwd")
        self.assertEqual(display_name("C:\\tmp\\evil<script>.csv"), "evilscript.csv")
        self.assertEqual(display_name(None), "upload.csv")
        self.assertEqual(display_name("..."), "upload.csv")
        self.assertLessEqual(len(display_name("a" * 500 + ".csv")), 100)

    def test_stored_names_are_generated_and_unique(self):
        a, b = new_stored_name("ds", "csv"), new_stored_name("ds", "csv")
        self.assertNotEqual(a, b)
        self.assertRegex(a, r"^ds_[0-9a-f]{32}\.csv$")

    def test_resolve_inside_blocks_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self.assertEqual(resolve_inside(base, "ok.csv").parent, base.resolve())
            with self.assertRaises(ValueError):
                resolve_inside(base, "../outside.csv")
            with self.assertRaises(ValueError):
                resolve_inside(base, "/etc/passwd")

    def test_atomic_write(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "f.bin"
            write_atomic(p, b"abc")
            self.assertEqual(p.read_bytes(), b"abc")
            self.assertEqual([x.name for x in p.parent.iterdir()], ["f.bin"])


class RetentionTests(unittest.TestCase):
    def test_expiry(self):
        now = datetime(2026, 1, 1)
        self.assertEqual(compute_expiry(now, 30), now + timedelta(days=30))
        self.assertIsNone(compute_expiry(now, 0))
        self.assertTrue(is_expired(now - timedelta(seconds=1), now))
        self.assertFalse(is_expired(now + timedelta(days=1), now))
        self.assertFalse(is_expired(None, now))


if __name__ == "__main__":
    unittest.main()
