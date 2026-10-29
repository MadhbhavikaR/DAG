# ADR-024: Direct final-validation correction path

## Decision

When final validation classifies exactly one review finding as an implementation defect, the manager returns the active task directly to `implementation` by creating a new corrective step. Previously completed steps remain terminal.

## Why

The specification explicitly permits `final_validation -> implementation` based on the submitted failure classification. Reopening a completed step would contradict the step lifecycle, so a new manager-owned corrective execution unit preserves both requirements.

## Consequence

The corrective step uses the approved application-path union and the prior implementation validation policy. Multiple or planning-classified review findings continue through the planning phase, where the planner can construct a new ordered plan.
