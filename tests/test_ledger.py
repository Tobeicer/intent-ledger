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

    def test_graph_keeps_versions_evidence_and_project_scope(self):
        def decide(message,topic,value,rev,**meta):
            ticket,_ = self.hook(self.a,"author",message,str(rev))
            payload={"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
                "name":"save_decision","arguments":dict(source=ticket,topic=topic,value=value,
                expected_revision=rev,quote=message,**meta)}}
            return json.loads(self.cli("mcp",data=json.dumps(payload)))["result"]
        def rows(path):
            html=Path(path).read_text(encoding="utf-8")
            return json.loads(re.search(r'<script type="application/json" id="ledger-data">(.*?)</script>',html,re.S)[1])["rows"]
        self.assertFalse(decide("一个目标","受众","一个目标",0,kind="goal").get("isError"))
        self.assertTrue(decide("不串项目","导出","PDF",0,goals=["不存在"]).get("isError"))
        for rev,(quote,value) in enumerate([("用 PDF","PDF"),("改成 </script>","</script>"),("不再导出","")]):
            self.assertFalse(decide(quote,"导出",value,rev,**({"goals":["受众"]} if not rev else {})).get("isError"))
        source,_=self.hook(self.b,"other","SECRET-B")
        self.save(source,"SECRET-B","SECRET-B",0)
        out=self.path/"snapshot.html"
        self.cli("graph",str(self.a),"--output",str(out))
        result=rows(out)
        self.assertEqual([r["value"] for r in result],["一个目标","PDF","</script>",""])
        self.assertEqual(result[-1]["goals"],["受众"])
        self.assertEqual(result[-2]["quote"],"改成 </script>")
        self.assertNotIn("SECRET-B",out.read_text(encoding="utf-8"))
        req={"id":2,"method":"tools/call","params":{"name":"project_graph","arguments":{"source":source}}}
        path=json.loads(json.loads(self.cli("mcp",data=json.dumps(req)))["result"]["content"][0]["text"])["path"]
        self.assertEqual([r["value"] for r in rows(path)],["SECRET-B"])
        self.cli("disable",str(self.a))
        blocked=self.path/"disabled.html"
        self.cli("graph",str(self.a),"--output",str(blocked))
        self.assertFalse(blocked.exists())

    def test_old_database_graph_before_first_v2_write(self):
        import sqlite3
        with sqlite3.connect(self.path/"data"/"memory.sqlite3") as db:
            root=db.execute("SELECT root FROM projects ORDER BY root").fetchone()[0]
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='revision_graph'").fetchone())
            msg=db.execute("INSERT INTO messages(ticket,root,chat,turn,body) VALUES('ticket',?,'c','t','before upgrade')",(root,)).lastrowid
            db.execute("INSERT INTO revisions VALUES(?,?,?,?,?,?)",(root,"Old topic",1,msg,"old decision","before upgrade"))
        db.close()
        out=Path(self.cli("graph",root))
        self.assertIn('"kind":"decision","goals":[]',out.read_text(encoding="utf-8"))
