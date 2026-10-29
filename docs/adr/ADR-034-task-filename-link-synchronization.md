# ADR-034: Synchronize managed links when task filenames change

**Decision:** When a task lifecycle transition changes its natural-sortable task filename, the manager rewrites all managed step links to the task's new canonical filename in the same locked mutation.

**Why:** Task filenames encode lifecycle state. A legal transition such as `active -> blocked` therefore changes the task path. Leaving step frontmatter pointing at the previous filename creates stale managed references and can make restart validation reject otherwise valid state.

**Rejected alternative:** Permit stale step links and resolve them by task ID alone. This weakens canonical rendering and allows managed records to disagree about the authoritative task path.

**Consequence:** Task saves remain the single lifecycle-file naming authority, while step back-references remain canonical after every filename-changing transition.
