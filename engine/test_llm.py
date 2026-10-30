"""LLM parser hook (engine/llm.py) against a local fake OpenAI-compatible server: no network, no key.

python -m pytest -q engine/test_llm.py
"""
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from engine import llm
from engine.data import store
from engine.kb import kb as load_kb
from engine.route import route


class FakeChat(BaseHTTPRequestHandler):
    reply = {"role_id": "dietitian", "task_ids": ["B10"], "modifiers": {}}
    status = 200
    reject_json_mode = False
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeChat.seen.append(body)
        if FakeChat.reject_json_mode and "response_format" in body:
            self.send_response(400)
            self.end_headers()
            return
        self.send_response(FakeChat.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if FakeChat.status == 200:
            content = json.dumps(FakeChat.reply)
            self.wfile.write(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    def log_message(self, *args):
        pass


class LlmParserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeChat)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.env = {"SECOND_LOOK_LLM": "1", "SECOND_LOOK_LLM_PROVIDER": "openai", "LLM_API_KEY": "test",
                   "LLM_BASE_URL": "http://127.0.0.1:%d/v1" % cls.server.server_address[1],
                   "SECOND_LOOK_LLM_MODEL": "fake-model"}
        cls.kb, cls.store = load_kb(), store()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        llm._cache.clear()
        FakeChat.reply = {"role_id": "dietitian", "task_ids": ["B10"], "modifiers": {}}
        FakeChat.status, FakeChat.reject_json_mode, FakeChat.seen = 200, False, []

    def route(self, text):
        with mock.patch.dict(os.environ, self.env):
            return route(text, self.kb, self.store, self.store.anchor_date(), detail="short", use_llm=True)

    def test_disabled_without_flag(self):
        with mock.patch.dict(os.environ, {"SECOND_LOOK_LLM": "0"}):
            self.assertIsNone(llm.understand("x", ["a"], ["B01"]))

    def test_llm_fills_a_task_the_tags_miss(self):
        u = self.route("Dietitian reviewing her weight.")
        self.assertIn("B10", u["bundles_chosen"])
        self.assertEqual(u["tasks_from"], "kb_llm")
        self.assertIsNone(u["fallback_note"])

    def test_prompt_shows_names_and_titles_not_bare_ids(self):
        self.route("Dietitian reviewing her weight.")
        prompt = FakeChat.seen[0]["messages"][0]["content"]
        self.assertIn("Pre-procedure check (anaesthesia)", prompt)
        self.assertIn("Anaesthetist", prompt)
        self.assertEqual(FakeChat.seen[0]["temperature"], 0)

    def test_unknown_ids_are_dropped(self):
        FakeChat.reply = {"role_id": "astronaut", "task_ids": ["B99", "drop table"], "modifiers": {}}
        u = self.route("Covering doctor at the weekend, needs a quick overview.")
        self.assertEqual(u["tasks_from"], "fallback")
        self.assertNotIn("B99", u["bundle_ids"])

    def test_server_error_falls_back_to_rules(self):
        FakeChat.status = 500
        u = self.route("Dietitian reviewing her weight.")
        self.assertEqual(u["tasks_from"], "fallback")
        self.assertIsNotNone(llm.last_error)

    def test_retries_without_json_mode(self):
        FakeChat.reject_json_mode = True
        u = self.route("Dietitian reviewing her weight.")
        self.assertIn("B10", u["bundles_chosen"])
        self.assertEqual(len(FakeChat.seen), 2)

    def test_tag_match_wins_over_llm(self):
        FakeChat.reply = {"role_id": "anaesthetist", "task_ids": ["B10"], "modifiers": {}}
        u = self.route("Anaesthetist, pre-operative check before surgery")
        self.assertIn("B01", u["bundles_chosen"])
        self.assertNotIn("B10", u["bundles_chosen"])
        self.assertEqual(FakeChat.seen, [], "no API call when the rules already match role and task")

    def test_cache_avoids_second_call(self):
        self.route("Dietitian reviewing her weight.")
        self.route("Dietitian   reviewing her WEIGHT.")
        self.assertEqual(len(FakeChat.seen), 1)


if __name__ == "__main__":
    unittest.main()
