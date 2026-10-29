from __future__ import annotations




class Config:
    HASH_LENGTH = 8
    START_MARKER = "[START]"
    END_MARKER = "[END]"
    DEFAULT_PREVIOUS = 1
    DEFAULT_NEXT = 1
    MAX_CONTEXT_LINES = 12
    MAX_CONTEXT_CHARS = 1200
    MAX_OUTPUT_CHARS = 4000
    # Long lines are clipped in output so one response cannot flood a small context window.
    MAX_LINE_CHARS = 160
    INDEX_VERSION = 8
    INDEX_SUFFIX = ".ctxidx"
    INDEX_DIR_NAME = "edit.py"
    TRANSACTION_MARKER = ".ctxnew."
    UTF8 = "utf-8"
