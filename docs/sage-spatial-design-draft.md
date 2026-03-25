# SageGate — Spatial Design Prompt (DRAFT)

> Status: Under consideration. Not yet integrated into prompts.py or validators.
> S.A.G.E. = Simple. Actionable. Generalizable. Enforceable.

---

## Spatial Design

Every spatial decision is free. Every spatial decision must declare its intent and measurement.

### Positive Space
Define how content-bearing areas relate locally. For component pairs that share
a visual context (horizontal, vertical, or containment), state which pairs share
a dimensional relationship and which are intentionally independent.

### Negative Space
Define where whitespace is deliberate and where it must not appear. Every empty
region must trace to a spacing token or rule in this document.

### Spatial Hierarchy
Define primary, secondary, and tertiary content zones. State how their relative
proportions reinforce importance. Where proportion breaks from hierarchy, state why.

### Visual Harmony & Cohesion
For each page layout, list every component pair that shares a row, column or zone.
For each pair, state their expected dimensional relationship (with units) and
what happens when device or viewport sizes differ. Every pair from the Layout
Grid must appear here.

---

## Proposed validator checks (all mechanical, DP-2 compliant)

For every component pair declared in Layout Grid:
1. The pair appears in Visual Harmony & Cohesion
2. The entry contains a dimensional relationship (regex: digits + px/rem/%/ratio)
3. The entry contains a viewport/device variance rule (what changes and when)

That's the whole gate. Sections 1-3 are design thinking. Section 4 is the receipt.

---

## Open questions

- "Row, column or zone" is concrete for grid-based layouts. For non-grid
  relationships (containment, cross-axis breaks like a full-width section
  interrupting a multi-column grid), the design agent needs to identify those
  as zone relationships. The validator checks coverage against Layout Grid
  pairs regardless of axis.

- Token cost: the Visual Harmony section asks the agent to enumerate pairs with
  measurements. For N components this is O(N^2) pairs in the worst case. In
  practice, the Layout Grid constrains which pairs share a row/column/zone, so
  the set is bounded by the grid structure, not the total component count.

- Mismatch handling now covers device/viewport variance (responsive) rather than
  content variance. Content-driven height mismatches (e.g., one card has more
  data than another) may need separate treatment or may be covered by the
  responsive rules depending on how the agent interprets "viewport sizes differ."
