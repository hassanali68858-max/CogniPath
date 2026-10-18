# CogniPath – Career Agent

## Overview
The Career Agent is a component of the CogniPath multi-agent system. It analyzes student skills, identifies skill gaps for career opportunities, and proposes career development activities.

## Current Prototype
- OWL ontology for career-related knowledge
- RDFLib and SPARQL queries
- Student skill identification
- Skill gap analysis
- Learning resource recommendations
- Career activity generation
- JSON output for future Planner Agent integration

## Requirements
- Python 3.11
- Dependencies listed in `requirements.txt`

## Installation
From the CogniPath repository root:

```bash
python -m pip install -r career_agent/requirements.txt
```

## Run
From the repository root:

```bash
python career_agent/src/career.py
```

## Current Limitations
The prototype uses predefined ontology data. CV extraction, real job discovery, and Planner Agent integration are planned for later development.
