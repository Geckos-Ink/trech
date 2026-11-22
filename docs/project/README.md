# Project context

[Documentation index](../README.md)

Planning, funding discussion drafts and historical notes. The active implementation backlog lives in the repository’s categorized AGENTS roadmaps; the original trech-roadmap.md is reference-only.

To keep the next piece of work evenly spread across the project, the root
[`AGENTS.md`](../../AGENTS.md#the-roadmap-12-implementations-to-do-bucket) holds a bucket of 12
open roadmap items: 5 high (P1), 4 medium (P2) and 3 low (P3) priority, drawn at random with no two
from the same roadmap. When one lands, its slot is refilled by another random draw at the same
priority. For example, `python3 scripts/draw_roadmap_bucket.py --draw P2` prints a replacement row,
and `python3 scripts/draw_roadmap_bucket.py --check` confirms every slot is still open.

## Keeping the documentation current

When you change TRECH’s code or how the project works, update the documentation in the
same change. Use the [documentation index](../README.md) to find the relevant guide or
reference. Explain what changed, why it matters and how a reader can use or verify it.
If you add or move a page, update its topic index and related links.
[Contributor workflow](../../AGENTS/project/AGENTS.md#docs--docs)

## Files

| Document or asset | Purpose |
| --- | --- |
| [Author notes](AUTHOR_NOTES.md) | Original author context. |
| [Research funding discussion](investors-presentation.md) | Draft presentation with explicit planning assumptions and prospective contacts. |
| [Historical implementation notes](notes.md) | Dated design discussion, including retired artifact names. |
| [Original roadmap concept](trech-roadmap.md) | Reference-only initial concept; active work is tracked in AGENTS roadmaps. |
