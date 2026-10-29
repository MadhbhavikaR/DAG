# ADR-010: Small command surface

## Decision
The primary model loop remains `next`, `context`, and `submit`; structured authoring commands remain secondary.

Machine-assistive secondary commands are part of the stable surface:

- `submit-schema` for schema-only recovery;
- `status --compact` for machine-friendly liveness;
- `verify` for read-only health checks;
- `examples` for minimal phase payloads;
- `learn add|list` for manual improvement logging.

## Rationale
A small stable interaction surface reduces command-selection errors.

Secondary commands reduce retries for weak models without transferring lifecycle authority away from the manager.
