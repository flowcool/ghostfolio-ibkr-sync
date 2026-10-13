# Domain Docs

How engineering skills should consume this repository's domain documentation when exploring the codebase.

## Before exploring, read these

- **`GLOSSARY.md`** at the repository root.
- **`docs/adr/`**: read ADRs that touch the area about to be changed.

If either location does not contain relevant documentation, proceed silently. The `/domain-modeling` skill creates missing vocabulary or decisions lazily when terms or decisions are resolved.

## File structure

This is a single-context repository:

```
/
├── GLOSSARY.md
├── docs/adr/
└── src/
```

## Use the glossary's vocabulary

When naming a domain concept in an issue title, refactor proposal, hypothesis, or test, use the term defined in `GLOSSARY.md`. If the required concept is absent, reconsider whether the project already uses another term, or note the gap for `/domain-modeling`.

## Flag ADR conflicts

Surface a contradiction with an existing ADR explicitly instead of silently overriding it.
