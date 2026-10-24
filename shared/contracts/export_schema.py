"""Write activity_proposal.schema.json next to this file.

Run from the repository root:  python -m shared.contracts.export_schema
"""

import json
from pathlib import Path

from .activity_proposal import ActivityProposal

if __name__ == "__main__":
    out = Path(__file__).with_name("activity_proposal.schema.json")
    out.write_text(json.dumps(ActivityProposal.model_json_schema(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
