"""Submission idempotency record model."""

@dataclass
class Submission:
    token: str
    fingerprint: str
    response: str
