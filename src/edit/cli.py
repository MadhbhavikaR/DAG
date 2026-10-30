from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from .config import Config
from .editor import FileEditor
from .errors import AgentArgumentParser, ErrorHandler, ToolError
from .filesystem import FileSystemManager
from .output import Output


class CLI:
    PROMPT = """edit PROTOCOL (one text file, JSON out; --human for people)
stdin carries content and search text.

CREATE   printf '%s\\n' 'l1' 'l2' | edit create FILE      (fails if FILE exists)
REWRITE  printf '%s\\n' 'l1' 'l2' | edit rewrite FILE     (replaces all of FILE)
SEARCH   printf '%s' 'text' | edit search FILE      (literal; --regex opt-in; max 5 hits)
READ     edit read FILE HASH [BEFORE AFTER]
REPLACE  printf '%s\\n' 'new' | edit replace FILE HASH
         printf '%s\\n' 'a' 'b' | edit replace FILE START..END
INSERT   printf '%s\\n' 'new' | edit insert before|after FILE HASH
DELETE   edit delete FILE HASH        edit delete FILE START..END

HASH comes only from search/read output. START..END is inclusive. Never invent a hash.
SEARCH returns just the matched lines; use READ for surrounding context.
Long lines are clipped with an ellipsis.

WORKFLOW  search -> read if needed -> edit -> use the returned hashes.

JSON INPUT  edit --json-input
{"command":"replace","file":"app.py","target":"HASH..HASH","input":"new text\\n"}
commands: create, rewrite, read, search, replace, insert, delete

ERRORS
STALE_HASH / STALE_FILE  -> search or read again
AMBIGUOUS_HASH           -> pick another observed hash
HASH_COLLISION           -> change the new content
MISSING_INPUT            -> provide stdin input
"""

    @staticmethod
    def read_stdin_if_available() -> str | None:
        if sys.stdin is None or sys.stdin.isatty():
            return None
        try:
            return sys.stdin.read()
        except OSError as exc:
            ErrorHandler.fail("STDIN_FAILED", f"Unable to read stdin: {exc}")

    @staticmethod
    def split_target(target: str):
        if not target:
            ErrorHandler.fail("MISSING_TARGET", "A target hash is required.")
        parts = target.split("..")
        if len(parts) > 2 or not all(parts):
            ErrorHandler.fail("INVALID_TARGET", "Target must be HASH or START_HASH..END_HASH.")
        return parts[0], parts[1] if len(parts) == 2 else None

    @staticmethod
    def build_parser():
        parser = AgentArgumentParser(
            prog="edit",
            description="Single-file create/search/read/replace/insert/delete tool for LLM/SLM agents.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument("--human", action="store_true", help="Human-readable output. JSON is default.")
        parser.add_argument("--prompt", action="store_true", help="Print the compact agent protocol.")
        parser.add_argument("--json-input", action="store_true", help="Read one JSON request object from stdin.")
        sub = parser.add_subparsers(dest="command")

        p=sub.add_parser("create", help="Create FILE from stdin."); p.add_argument("file")
        p=sub.add_parser("rewrite", help="Replace all of FILE from stdin."); p.add_argument("file")
        p=sub.add_parser("read", help="Read bounded file/context."); p.add_argument("file"); p.add_argument("hash",nargs="?"); p.add_argument("before",nargs="?",type=int,default=None); p.add_argument("after",nargs="?",type=int,default=None)
        p=sub.add_parser("search", help="Search stdin text in FILE."); p.add_argument("file"); p.add_argument("--regex",action="store_true"); p.add_argument("--limit",type=int,default=5); p.add_argument("--before",type=int,default=Config.DEFAULT_PREVIOUS); p.add_argument("--after",type=int,default=Config.DEFAULT_NEXT)
        p=sub.add_parser("replace", help="Replace HASH or HASH..HASH using stdin."); p.add_argument("file"); p.add_argument("target")
        p=sub.add_parser("insert", help="Insert stdin content before or after HASH."); p.add_argument("position",choices=("before","after")); p.add_argument("file"); p.add_argument("hash")
        p=sub.add_parser("delete", help="Delete HASH or HASH..HASH."); p.add_argument("file"); p.add_argument("target")
        sub.add_parser("prompt", help="Print the compact SLM protocol.")
        return parser

    @classmethod
    def json_input(cls, output):
        raw=cls.read_stdin_if_available()
        if raw is None: ErrorHandler.fail("MISSING_JSON","JSON request must be supplied on stdin.")
        try: req=json.loads(raw)
        except json.JSONDecodeError as exc: ErrorHandler.fail("INVALID_JSON",f"Invalid JSON: {exc}")
        if not isinstance(req,dict): ErrorHandler.fail("INVALID_JSON","JSON request must be an object.")
        command=req.get("command")
        if command not in {"create","rewrite","read","search","replace","insert","delete"}: ErrorHandler.fail("INVALID_COMMAND","command must be create, rewrite, read, search, replace, insert, or delete.")
        filename=req.get("file")
        if not isinstance(filename,str) or not filename: ErrorHandler.fail("MISSING_FILE","file is required.")
        path=Path(filename); FileSystemManager.cleanup_transactions(path); editor=FileEditor(path,output); value=req.get("input")
        if value is not None and not isinstance(value,str): ErrorHandler.fail("INVALID_INPUT","input must be a string.")
        if command=="rewrite": editor.rewrite(value)
        elif command=="create":
            if value is None: ErrorHandler.fail("MISSING_INPUT","Create content must be in input.")
            editor.create(value)
        elif command=="read": editor.read(req.get("hash"),cls.json_int(req, "before"),cls.json_int(req, "after"))
        elif command=="search": editor.search(value or "",bool(req.get("regex",False)),cls.json_int(req, "limit", 5),cls.json_int(req, "before", Config.DEFAULT_PREVIOUS),cls.json_int(req, "after", Config.DEFAULT_NEXT))
        elif command=="replace":
            a,b=cls.split_target(str(req.get("target","")))
            if value is None: ErrorHandler.fail("MISSING_INPUT","Replacement content must be in input.")
            editor.mutate("replace",a,b,value)
        elif command=="insert":
            if value is None: ErrorHandler.fail("MISSING_INPUT","Insertion content must be in input.")
            editor.mutate("insert",str(req.get("hash","")),None,value,str(req.get("position","")))
        else:
            a,b=cls.split_target(str(req.get("target",""))); editor.mutate("delete",a,b,None)
        return 0

    @staticmethod
    def json_int(request: dict, name: str, default: int | None = None) -> int | None:
        value = request.get(name, default)
        if value is None:
            return None
        if isinstance(value, bool):
            ErrorHandler.fail("INVALID_NUMBER", f"'{name}' must be an integer.", f"Set '{name}' to a whole number.")
        try:
            return int(value)
        except (TypeError, ValueError):
            ErrorHandler.fail("INVALID_NUMBER", f"'{name}' must be an integer.", f"Set '{name}' to a whole number.")

    @classmethod
    def run(cls):
        parser=cls.build_parser(); output=Output(False)
        try:
            args=parser.parse_args(); output=Output(args.human)
            if args.prompt or args.command=="prompt": print(cls.PROMPT); return 0
            if args.json_input: return cls.json_input(output)
            if not args.command:
                print(cls.PROMPT)
                return 0
            path=Path(args.file); FileSystemManager.cleanup_transactions(path); editor=FileEditor(path,output)
            if args.command=="rewrite":
                editor.rewrite(cls.read_stdin_if_available())
            elif args.command=="create":
                v=cls.read_stdin_if_available()
                if v is None: ErrorHandler.fail("MISSING_INPUT","Create content must be supplied on stdin.")
                editor.create(v)
            elif args.command=="read": editor.read(args.hash,args.before,args.after)
            elif args.command=="search":
                v=cls.read_stdin_if_available()
                if v is None: ErrorHandler.fail("MISSING_QUERY","Search text must be supplied on stdin.")
                editor.search(v,args.regex,args.limit,args.before,args.after)
            elif args.command=="replace":
                v=cls.read_stdin_if_available()
                if v is None: ErrorHandler.fail("MISSING_INPUT","Replacement content must be supplied on stdin.")
                a,b=cls.split_target(args.target); editor.mutate("replace",a,b,v)
            elif args.command=="insert":
                v=cls.read_stdin_if_available()
                if v is None: ErrorHandler.fail("MISSING_INPUT","Insertion content must be supplied on stdin.")
                editor.mutate("insert",args.hash,None,v,args.position)
            elif args.command=="delete":
                a,b=cls.split_target(args.target); editor.mutate("delete",a,b,None)
            return 0
        except ToolError as exc:
            output.error(exc); return 1
        except KeyboardInterrupt:
            output.error(ToolError("CANCELLED","Operation cancelled.")); return 130


def main() -> int:
    """Run the command-line interface."""
    return CLI.run()
