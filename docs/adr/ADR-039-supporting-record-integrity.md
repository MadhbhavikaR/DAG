# ADR-039: Validate lazy supporting records as authoritative managed state

## Decision

When analysis, decisions, or evidence projections exist, startup validation treats their frontmatter and contained record identities as authoritative managed state and validates them before mutation proceeds.

## Why

The specification requires managed files to be durable, restart-safe, and reconstructible. Validating only task and step projections left a corruption window in which duplicate finding/decision/event IDs, malformed decision lifecycle records, or damaged supporting-record metadata could survive until a later command consumed them.

## Rejected alternative

Validate supporting documents only when the corresponding command reads them. That defers detection, makes restart behavior path-dependent, and can permit later writes against corrupted history.

## Consequence

Supporting documents remain lazy, but once created they are fail-closed records. Empty or malformed records stop mutation with a repair-oriented diagnostic. Empty list sections in decisions remain legal because the command schema permits empty alternatives, consequences, and evidence arrays.
