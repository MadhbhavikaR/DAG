"""Public CLI contract tests."""
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ENTRY=ROOT/"edit.py"
def run_cli(*args: str,input_text: str|None=None)->subprocess.CompletedProcess[str]:
 return subprocess.run([sys.executable,str(ENTRY),*args],input=input_text,text=True,capture_output=True,cwd=ROOT,check=False)
def test_prompt()->None:
 r=run_cli("--prompt"); assert r.returncode==0 and "SEARCH" in r.stdout and not r.stderr
def test_create_search_read(tmp_path:Path)->None:
 p=tmp_path/"sample.txt"; c=run_cli("create",str(p),input_text="alpha\nbeta\n"); assert c.returncode==0
 assert json.loads(c.stdout)=={"ok":True,"operation":"create","lines":2}
 s=json.loads(run_cli("search",str(p),input_text="beta").stdout); assert s["count"]==1
 h=s["matches"][0]["hash"]; r=json.loads(run_cli("read",str(p),h).stdout); assert any(x["text"]=="beta" for x in r["context"])
def test_replace_and_fresh_anchor(tmp_path:Path)->None:
 p=tmp_path/"sample.txt"; run_cli("create",str(p),input_text="alpha\nbeta\n"); s=json.loads(run_cli("search",str(p),input_text="beta").stdout)
 r=run_cli("replace",str(p),s["matches"][0]["hash"],input_text="gamma\n"); data=json.loads(r.stdout)
 assert r.returncode==0 and data["operation"]=="replace" and data["anchor"] and p.read_text()=="alpha\ngamma\n"
def test_stale_anchor_error(tmp_path:Path)->None:
 p=tmp_path/"sample.txt"; run_cli("create",str(p),input_text="alpha\nbeta\n"); r=run_cli("replace",str(p),"deadbeef",input_text="gamma\n"); data=json.loads(r.stderr)
 assert r.returncode==1 and data["ok"] is False and data["error"]=="STALE_HASH"
def test_create_never_overwrites(tmp_path:Path)->None:
 p=tmp_path/"sample.txt"; p.write_text("keep\n"); r=run_cli("create",str(p),input_text="overwrite\n"); data=json.loads(r.stderr)
 assert r.returncode==1 and data["error"]=="FILE_EXISTS" and p.read_text()=="keep\n"
