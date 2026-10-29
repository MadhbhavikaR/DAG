# ADR-022: Validate cross-record execution consistency on startup

**Decision:** Startup validation must verify that task phase, current step, step state, child completion, workspace metadata, and submission-ledger schema agree before mutation is allowed.

**Why:** Valid individual records can still form an impossible workflow when combined. A restart-safe manager must reject contradictory cross-record state rather than deriving a new state from corrupted metadata.

**Consequence:** Validation is stricter at process startup. Repair of contradictory managed state requires an explicit administrative repair procedure; normal model commands cannot silently reconcile it.

## Replanning after final validation failure

A failed final validation may return the task to planning. The previous terminal plan is archived by the manager before a replacement plan is materialized. This preserves auditability while keeping the active `steps/` directory authoritative for the current plan.
