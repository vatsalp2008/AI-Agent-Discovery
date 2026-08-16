# Working with the pages

Search is the front door; these are the pages that keep something between
visits. All of them store what they hold in `localStorage` — the premise of the
project is that what you look for never leaves your machine, and a list of the
questions somebody keeps asking is about as revealing as data gets.

- [Saved searches](#saved-searches)
- [Comparing agents](#comparing-agents)
- [Collections](#collections)

## Saved searches

A catalogue that grows is a catalogue whose answers change, and nothing tells
you. **Save this search** stores the query with a snapshot of what it returned;
`/saved` re-runs it and reports agents that **now match**, ones that **dropped
out**, and projects whose **stars moved** by more than 5% — a fraction, so
40 → 400 registers and 40,000 → 40,300 does not.

Re-ranking alone is not a change, checking adopts the fresh results so nothing
is reported twice, and searches run one at a time to stay inside the rate
limit. Kept in `localStorage`, like collections: the questions you keep asking
never leave your machine.

## Comparing agents

Up to `COMPARE_MAX_AGENTS` (default **8**) go side by side, one column each.

Past three the table scrolls sideways with the attribute labels pinned. Without
that, a fifth column is a list of values with nothing naming them — which is why
the limit used to be four. The scrolling region is keyboard focusable and
labelled, so the later columns are reachable without a mouse, and no focus stop
is added when there is nothing to scroll.

The picker stops at the limit rather than letting you build a selection the API
then refuses with a `400`; the limit should arrive as a control that stops, not
as a failed request.

## Collections

Named shortlists of agents. Each one offers a **Compare** link that takes its
first eight, and its own **Export** for sharing a single shortlist — the same
format as a full export, so it merges back on the other side rather than being
refused as a different file.

## Project health

Entries carry an optional `status`. Absent means `active` and shows nothing;
`archived` and `dormant` show a badge on the card, because a directory that
does not say a project has been archived is misleading in the one way that
matters when choosing a tool.

The search page offers **Only maintained projects**, which leaves those
entries out. The filter runs during the scan, so the page stays full: an
archived project is replaced by the next live one rather than leaving a gap.

It is set by `audit.py` from what GitHub reports — see
[CATALOGUE.md](CATALOGUE.md) — and cleared again when a project comes back, so
a stale warning does not outlive the thing it warned about. The editor can
correct one; a public submission cannot set one.
