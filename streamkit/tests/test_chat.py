import queue
import random
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from streamkit import MockChat, TwitchChat, load_env


class TestLoadEnv(unittest.TestCase):
    def test_parses_key_value_and_skips_comments(self):
        with TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("# comment\nTWITCH_TOKEN=oauth:abc123\n\nX = 1 \n",
                         encoding="utf-8")
            env = load_env(p)
        self.assertEqual(env, {"TWITCH_TOKEN": "oauth:abc123", "X": "1"})

    def test_missing_file_returns_empty(self):
        self.assertEqual(load_env("definitely_missing.env"), {})


class TestTwitchChat(unittest.TestCase):
    def test_raises_without_token(self):
        with self.assertRaises(RuntimeError):
            TwitchChat(lambda u, t: None, "somechannel",
                       env_path="definitely_missing.env")

    def test_raises_without_channel(self):
        with TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("TWITCH_TOKEN=oauth:abc\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                TwitchChat(lambda u, t: None, "", env_path=p)

    def test_update_drains_queue_into_callback(self):
        received = []
        chat = TwitchChat.__new__(TwitchChat)  # no network thread
        chat.on_message = lambda u, t: received.append((u, t))
        chat.incoming = queue.Queue()
        chat.incoming.put(("alice", "u1"))
        chat.incoming.put(("bob", "hello"))
        chat.update()
        self.assertEqual(received, [("alice", "u1"), ("bob", "hello")])
        self.assertTrue(chat.incoming.empty())


class TestMockChat(unittest.TestCase):
    def test_sends_pool_messages_only_after_interval(self):
        received = []
        chat = MockChat(lambda u, t: received.append((u, t)),
                        messages=["u1", "spam"], users=["alice"],
                        interval=0.5, rng=random.Random(1))
        chat.update(0.4)
        self.assertEqual(received, [])
        chat.update(0.2)
        self.assertTrue(received)
        for user, text in received:
            self.assertEqual(user, "alice")
            self.assertIn(text, ("u1", "spam"))
        n = len(received)
        chat.update(0.2)  # timer was reset to the interval: no new burst yet
        self.assertEqual(len(received), n)


if __name__ == "__main__":
    unittest.main()
