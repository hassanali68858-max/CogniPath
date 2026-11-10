# Frontend (Next.js test UI)

A simple web UI for trying the Planner without Swagger: load demo data, edit the
student's profile, add or withdraw proposals as if you were an agent, make plans,
accept or reject items, and re-plan.

The UI is a guided journey. A **Next step** banner at the top of every page
always says what to do next, and the sidebar ticks off each step.

| Page | What you do there | API it uses |
| --- | --- | --- |
| Start `/` | What CogniPath does, the journey, load or clear the demo student | `/health`, `/demo/*` |
| 1 · About you `/profile` | Day window, daily limit, days off, goal weights, fixed commitments | `GET/PUT /profiles/{user_id}` |
| 2 · Suggestions `/suggestions` | Agent suggestions as cards; filter by agent/status; withdraw; **Simulate an agent** drawer (form or JSON) | `/proposals`, `/proposals/{user}/{id}/withdraw` |
| 3 · Your plan `/plan` | Compare versions, week calendar, review list with accept/reject/undo, why each item was planned, what didn't fit, re-plan with NEW/MOVED tags, calendar file | `/planner/runs`, `/decisions`, `/replan`, `/ics` |

Light and dark mode follow the system setting. Works on phone widths too.

## Run (two terminals, from the repository root)

```bash
# terminal 1: backend
source .venv/bin/activate
uvicorn backend.main:app --reload            # http://127.0.0.1:8000

# terminal 2: frontend (Node.js 20+)
cd frontend
npm install                                   # first time only
npm run dev                                   # http://localhost:3000
```

The browser calls `/api/...` and Next.js forwards it to the backend (see
`next.config.ts`). If the backend runs elsewhere, set `BACKEND_URL` in
`frontend/.env.local` (see `.env.example`).

## Code map

- `app/` — one folder per page (`page.tsx`); `globals.css` holds the design tokens and all styles
- `components/AppShell.tsx` — sidebar journey; `NextStep.tsx` — the "what to do next" logic
- `components/StatusProvider.tsx` — loads backend / profile / suggestions / plan status for the whole app
- `components/WeekCalendar.tsx` — one week grid (plan sessions + commitments)
- `components/GoalMeters.tsx`, `AgentBadge.tsx`, `Drawer.tsx`, `Toast.tsx` — small UI pieces
- `lib/meta.ts` — agent and goal names, icons and wording
- `lib/api.ts` — every backend call in one place, with readable error messages
- `lib/types.ts` — TypeScript copies of `shared/contracts` (update when the contracts change)

This is a test UI with no login: the student id is kept in the browser.
