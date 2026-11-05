import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import login_notify

ENV = {
    "PREGRADER_SMTP_HOST": "smtp.example.com",
    "PREGRADER_SMTP_USER": "bot@example.com",
    "PREGRADER_SMTP_PASSWORD": "secret",
    "PREGRADER_NOTIFY_TO": "a@example.com, b@example.com",
}


class LoginNotifyTests(unittest.TestCase):
    def test_disabled_without_config(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("threading.Thread") as thread:
            self.assertFalse(login_notify.notify_login("ana", "1.2.3.4"))
            thread.assert_not_called()

    def test_enabled_starts_background_send(self):
        with mock.patch.dict(os.environ, ENV, clear=True), mock.patch("threading.Thread") as thread:
            self.assertTrue(login_notify.notify_login("ana", "1.2.3.4"))
            cfg, text = thread.call_args.kwargs["args"]
            self.assertEqual(cfg["recipients"], ["a@example.com", "b@example.com"])
            self.assertEqual(cfg["sender"], "bot@example.com")
            self.assertEqual(cfg["port"], 587)
            self.assertIn("ana", text)
            self.assertIn("1.2.3.4", text)
            thread.return_value.start.assert_called_once()

    def test_message_strips_untrusted_characters(self):
        msg = login_notify.build_message("ana\nBcc: x@evil.com <b>", "1.2.3.4, 9.9.9.9")
        self.assertNotIn("\n", msg)
        self.assertNotIn("<", msg)
        self.assertNotIn(" 9.9.9.9", msg)

    def test_send_sends_email_over_starttls(self):
        with mock.patch.dict(os.environ, ENV, clear=True):
            cfg = login_notify._config()
        with mock.patch("login_notify.smtplib.SMTP") as smtp_cls:
            login_notify._send(cfg, "hola")
            smtp = smtp_cls.return_value.__enter__.return_value
            smtp.starttls.assert_called_once()
            smtp.login.assert_called_once_with("bot@example.com", "secret")
            sent = smtp.send_message.call_args.args[0]
            self.assertEqual(sent["To"], "a@example.com, b@example.com")

    def test_send_errors_are_swallowed(self):
        with mock.patch.dict(os.environ, ENV, clear=True):
            cfg = login_notify._config()
        with mock.patch("login_notify.smtplib.SMTP", side_effect=OSError("down")):
            login_notify._send(cfg, "hola")


if __name__ == "__main__":
    unittest.main()
