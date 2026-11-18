"""Exercise real hook/MCP subprocess boundaries with two isolated project roots."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ENTRY = Path(__file__).resolve().parents[1] / "plugin" / "ledger.py"


class LedgerTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)
        self.env = dict(os.environ, INTENT_LEDGER_HOME=str(self.path / "data"), PYTHONUTF8="1")
        self.a, self.b = (self.path / k / "same-name" for k in ("left", "right"))
        for p in (self.a, self.b):
            p.mkdir(parents=True)
            self.cli("enable", str(p))

    def cli(self, *args, data=""):
        return subprocess.run([sys.executable, "-B", str(ENTRY), *args], input=data,
                              encoding="utf-8", env=self.env, check=True,
                              capture_output=True, timeout=10).stdout.strip()

    def hook(self, project, chat, text, turn="1"):
        payload = {"cwd":str(project),"session_id":chat,"turn_id":turn,
                   "hook_event_name":"UserPromptSubmit","prompt":text}
        reply = self.cli("hook",data=json.dumps(payload))
        if not reply:
            return None, []
        context = json.loads(reply)["hookSpecificOutput"]["additionalContext"]
        source = re.search(r"Source ID: ([0-9a-f]+)", context)[1]
        return source, json.loads(context.split("\n",1)[1])

    def save(self, source, value, quote, rev):
        req = {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
            "name":"save_decision","arguments":{"source":source,"value":value,
            "topic":"Export format","quote":quote,"expected_revision":rev}}}
        return json.loads(self.cli("mcp",data=json.dumps(req)+"\n"))["result"]

    def test_revision_recall_and_isolation(self):
        old, _ = self.hook(self.a,"one","以后用 CSV。\n  原话。 ")
        self.assertFalse(self.save(old,"CSV","以后用 CSV",0).get("isError"))
        other, view = self.hook(self.b,"two","Use XML from now on.")
        self.assertEqual(view, [])
        self.assertFalse(self.save(other,"XML","Use XML",0).get("isError"))
        new, view = self.hook(self.a,"three","以后用 JSON，不用 CSV。")
        self.assertEqual(view[0]["value"],"CSV")
        self.assertTrue(self.save(new,"JSON","未说过的理由",1)["isError"])
        self.assertFalse(self.save(new,"JSON","以后用 JSON",1).get("isError"))
        self.assertTrue(self.save(old,"obsolete","CSV",2)["isError"])
        for project, value in ((self.a,"JSON"),(self.b,"XML")):
            _, found = self.hook(project,"new-chat","我们上次定了什么？")
            self.assertEqual([r["value"] for r in found],[value])
        raw = [json.loads(x)["body"] for x in self.cli("messages",str(self.a)).splitlines()]
        self.assertEqual(raw,["以后用 CSV。\n  原话。 ","以后用 JSON，不用 CSV。","我们上次定了什么？"])

    def test_opt_in_git_boundary_and_disable(self):
        sub = self.a / "sub"
        sub.mkdir()
        self.assertIsNotNone(self.hook(sub,"x","ordinary prompt")[0])
        (sub / ".git").mkdir()
        self.assertIsNone(self.hook(sub,"y","private")[0])
        self.cli("disable",str(self.a))
        self.assertIsNone(self.hook(self.a,"x","disabled")[0])
        self.cli("enable",str(self.a))
        self.assertNotIn("disabled",self.cli("messages",str(self.a)))
