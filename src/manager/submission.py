"""Submission idempotency record model."""

from dataclasses import dataclass


@dataclass
class Submission:
    token: str
    fingerprint: str
    response: str
