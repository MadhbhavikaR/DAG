# ADR-028: Story Allocation and Explicit New-Story Creation

## Status

Accepted

## Context

The orchestration model defines a story as an ordered group of related tasks and uses manager-owned identifiers for deterministic reconstruction. Root tasks should naturally join the currently open story, but operators may need to stage later stories before current execution completes.

## Decision

Manager-owned root task allocation will:

1. allocate the first root task as `S00001T00001`;
2. keep subsequent root tasks in the highest-numbered story while that story contains any non-done task;
3. automatically advance to the next story when every task in the current story is `done`;
4. allow an explicit `--new-story` request at any time by allocating into the next story number; and
5. continue allocating child tasks within the parent's story/root decomposition scope.

The model cannot bypass this boundary by choosing an ID or story number.

## Consequences

- Natural filename and identifier ordering reflects the actual story execution order.
- Later stories can be prepared without changing the currently active execution story.
- Story progression remains manager-owned and deterministic.
- Existing task IDs remain immutable and are never reused through normal allocation.
