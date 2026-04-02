# Problem Merging Guidance

Understand when individual alarm events (dt.davis.event) are merged into one problem and why they may stay separate.

## Overview

Dynatrace can merge multiple events into one problem when they look like the same incident context.

Merging decisions are mainly driven by:
- Time overlap of active event windows
- Shared source entity context
- Topology relationship (for example, vertical stack relationships, horizontal trace dependency relationship)
- Merge policy flags on the events

## Events Usually Merge When

1. Active time windows overlap
- The active duration of both events overlaps from `event.start` to `event.end`.
- In practice, event start times should be close (roughly within about 3 minutes).

2. Source entity is the same
- Preferred field: `dt.smartscape_source.id` is the same.
- Backward-compatible/older field: `dt.source_entity` is the same.

3. Events are in the same vertical deployment stack
- Example: a process runs on a host.
- A CPU-high event on the process and a CPU-high event on the host can merge because both describe the same stack context.

## Events Usually Do Not Merge When

1. Time windows do not overlap
- If active intervals are separate (no overlap), events typically remain in different problems.

2. Start times are too far apart
- If starts are not close (outside the rough ~3 minute proximity), events are less likely to merge.

3. Merging is explicitly disabled
- If an event has `dt.davis.is_merging_allowed == false`, Davis does not merge that event into other problems.

## Field Checklist

Use these fields when investigating merge behavior:
- `event.start`
- `event.end`
- `dt.smartscape_source.id`
- `dt.source_entity`
- `dt.davis.is_merging_allowed`

## Investigation Tips

1. Compare event intervals first
- Check if active windows overlap.

2. Compare entity identity next
- Check both `dt.smartscape_source.id` and `dt.source_entity`.

3. Validate topology relationship
- If entities differ, check whether they are still part of the same vertical stack (for example process on host).
- If entities differ, check whether they are still part of the same horizontal stack (for example service calls service or frontend calls service).

4. Check merge policy flags
- Confirm whether `dt.davis.is_merging_allowed` is false on any involved event.
