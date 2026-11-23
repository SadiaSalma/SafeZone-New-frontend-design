"""
conftest.py - pytest reads this file FIRST, before any test.

We point the app at a separate test database ("safezone_test"), so tests can
write and delete freely without ever touching the real "safezone" data.
(A real environment variable wins over the value in .env.)
"""
import os

os.environ["MONGODB_DB"] = "safezone_test"
os.environ["BACKGROUND_JOBS"] = "false"  # tests run the alert job themselves (Task 22)
os.environ["OTP_CHANNEL"] = "console"  # codes are printed (tests read them there); demo_screen is tested on its own
