# ADR-020: Re-enter planning after final validation failure

**Status:** Accepted

## Decision

When final validation fails after all implementation steps are complete, the manager returns the task to `planning` and clears `current_step`.

## Why

The final-validation gate is reached only after every implementation step is terminal. Returning to `implementation` would therefore create an execution phase without a current actionable step and violate the bounded-step lifecycle.

A new planning pass lets the planner incorporate the final-validation failure into a new ordered implementation plan.

## Consequence

Final validation failures are durable evidence and require a fresh planning decision before additional implementation work can begin.
