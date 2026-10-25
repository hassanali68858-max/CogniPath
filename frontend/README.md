# Frontend (Next.js test UI)

A simple web UI for trying the Planner without Swagger: load demo data, edit the
student's profile, add or withdraw proposals as if you were an agent, make plans,
accept or reject items, and re-plan.

| Page | What you do there | API it uses |
| --- | --- | --- |
| Home `/` | Pick the student, load demo data, reset, see status | `/health`, `/demo/*`, `/profiles`, `/proposals`, `/planner/users/{id}/current` |
| Profile `/profile` | Day hours, daily limit, goal weights, busy time | `GET/PUT /profiles/{user_id}` |
| Proposals `/proposals` | List, add, paste JSON, withdraw | `/proposals`, `/proposals/{user}/{id}/withdraw` |
| Plan `/plan` | Make plans (3 modes), week calendar, accept/reject, re-plan, .ics | `/planner/runs`, `/decisions`, `/replan`, `/ics` |

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

- `app/` — one folder per page (`page.tsx`), `layout.tsx` with the navigation
- `components/WeekCalendar.tsx` — the week grid (plan sessions + busy time)
- `components/LossBars.tsx` — share of each goal left out
- `lib/api.ts` — every backend call in one place, with readable error messages
- `lib/types.ts` — TypeScript copies of `shared/contracts` (update when the contracts change)

This is a test UI with no login: the student id is kept in the browser.
