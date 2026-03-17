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
For each page layout, list every component pair that shares a visual context.
For each pair, state their expected dimensional relationship (with units) and
what happens when content sizes differ. Every pair from the Layout Grid must
appear here.

---

## Proposed validator checks (all mechanical, DP-2 compliant)

1. All four headers present under `## Spatial Design`
2. Visual Harmony section contains >= 3 comparative measurements
   (regex: digits + px/rem/%/ratio)
3. Every component pair declared in Layout Grid appears in Visual Harmony
   (string cross-reference)
4. Every pair in Visual Harmony has a mismatch handling rule
   (regex for keywords: stretches/fills/stacks/collapses/matches/independent)

---

## Open questions

- "Siblings" / "row" / "zone" are undefined terms. Current draft uses "component
  pairs that share a visual context" which is more general but harder to validate
  mechanically. The design agent must identify which pairs those are and what axis
  the relationship operates on (horizontal, vertical, containment, cross-axis).
  The validator checks coverage against Layout Grid, not against an undefined
  concept of "siblings."

- Token cost: the Visual Harmony section asks the agent to enumerate pairs with
  measurements. For N components this is O(N^2) pairs in the worst case. In
  practice, the Layout Grid constrains which pairs share a visual context, so
  the set is bounded by the grid structure, not the total component count.

- Balance between enforcement and creativity: sections 1-3 are qualitative
  design thinking (unconstrained). Section 4 is the enforcement gate (must
  contain measurements). The agent can design however it wants; it just has to
  show the receipt.
