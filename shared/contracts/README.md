# Shared contracts

Data models that more than one component uses. Every agent returns
`list[ActivityProposal]`; the Planner reads only that.

Rules:
- Change these files only through a small pull request that all agent owners review.
- Keep models strict (`extra="forbid"`) so mistakes fail early.
- After changing a model, regenerate its JSON Schema (see the Planner README).
