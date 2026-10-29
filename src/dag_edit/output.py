from __future__ import annotations

import json
import sys
from .errors import ToolError


class Output:
    def __init__(self, human: bool):
        self.human = human

    def ok(self, data: dict) -> None:
        if self.human:
            self._human_ok(data)
        else:
            self._json({"ok": True, **data})

    def error(self, exc: ToolError) -> None:
        payload = {"ok": False, "error": exc.code, "message": exc.message}
        if exc.solution:
            payload["action"] = exc.solution
        if self.human:
            print(f"ERROR [{exc.code}]: {exc.message}", file=sys.stderr)
            if exc.solution:
                print(f"Solution: {exc.solution}", file=sys.stderr)
        else:
            self._json(payload, stderr=True)

    @staticmethod
    def _json(data: dict, stderr: bool = False) -> None:
        stream = sys.stderr if stderr else sys.stdout
        print(json.dumps(data, ensure_ascii=False, separators=(",", ":")), file=stream)

    @staticmethod
    def _human_ok(data: dict) -> None:
        op = data.get("operation", "ok")
        print(f"OK: {op}")
        for key, value in data.items():
            if key == "operation":
                continue
            if key == "context":
                print("CONTEXT:")
                for row in value:
                    print(f"{row['offset']:+d} {row['hash']}: {row['text']}")
            elif key == "matches":
                for row in value:
                    print(f"{row['line']}: {row['hash']}: {row['text']}")
            else:
                print(f"{key}: {value}")
