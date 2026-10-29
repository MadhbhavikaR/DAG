# ADR-016: Constrain validation evidence

## Decision
Accepted validation commands use one executable command expression without shell chaining, redirection, pipelines, or control operators. Submitted summaries are rejected when they match known secret-material patterns.

## Rationale
The manager must not turn model-provided evidence into an uncontrolled command surface or persist obvious credentials in durable evidence.

## Consequence
The protocol remains model-executable while keeping validation evidence bounded and safer to persist.
