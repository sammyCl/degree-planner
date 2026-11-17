# Frontend

React + Vite + TypeScript. Part of the degree planner; see the repository README and `plans/FRONTEND-PLAN.md`.

```
npm install
npm run dev     # http://localhost:5173
npm test
npm run build
npm run lint
```

In development, calls to `/api/...` are proxied to the FastAPI backend at `127.0.0.1:8000` (the `/api` prefix is removed), so start the backend with `uv run uvicorn degree_planner_backend.main:app --reload` from `backend/` to see "Backend: connected".
All backend calls live in `src/api.ts`.
