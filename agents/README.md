# Agents

Every agent is a Python package in its own folder and exposes one function:

```python
def propose(profile, context) -> list[ActivityProposal]: ...
```

`ActivityProposal` lives in `shared/contracts/`. An agent must not write to the
user's plan; it only proposes, and the Planner decides.

| Folder | Agent |
| --- | --- |
| `event_agent/` | Event Agent |
| `tutor_agent/` | Tutor Agent (incl. Quiz Agent) |
| `career_agent/` | Career Agent |
| `planner_agent/` | Planner Agent |
