# AdmiQ Frontend

Staff dashboard for AdmiQ. React 19 + Vite + Tailwind v4 + shadcn/ui + React Router + TanStack Query.

This repo also builds the static marketing landing page (`index.html`, served at `/`) alongside the React SPA (`home/index.html`, served at `/home/`) - see `vite.config.js`'s `rollupOptions.input`.

## Setup

```bash
npm install
cp .env.example .env
```

Edit `.env` and set `VITE_API_BASE_URL` to your running backend (e.g. `http://localhost:8000` if you're running the Docker Compose stack locally).

```bash
npm run dev
```

Other scripts: `npm run build`, `npm run preview`, `npm run lint` (oxlint), `npm test` / `npm run test:watch` (vitest).

## What's built

Everything in the nav is fully implemented and wired to the backend:

- **Auth**: login, silent session restore on page reload, automatic access-token refresh on expiry, logout, forgot/reset password.
- **Dashboard shell**: sidebar nav (with a live low-confidence-queue count badge), college switcher for staff on more than one college, light/dark theme toggle, protected routing.
- **Overview**: stat cards + a lead-score distribution chart.
- **Low-confidence queue**: open/resolved queries the assistant flagged, with a reply dialog that shows prior conversation context.
- **Staff management**: list/search/export, add/edit/remove staff, invite-by-email or set-password-directly.
- **Students**: list/search/filter-by-assignment/export, and a per-student detail page (conversation thread, direct messaging, internal notes, staff assignment, extracted profile signals).
- **Documents**: drag-and-drop PDF upload with per-file progress, processing status polling, search/filter, single and bulk delete, retry on failure.
- **College settings**: contact info + an ordered list of "key strengths" the assistant leans on for re-engagement messages.

## Important things to know before you touch this

**Access tokens live in memory only; refresh tokens live in an httpOnly cookie set by the backend.** The access token (`src/lib/tokenStore.js`) is never persisted - it's gone on every page reload by design, which limits the blast radius if it's ever read off the page. The refresh token is **not** readable from JS at all anymore; the browser sends it automatically via `credentials: "include"`. If you're used to an older version of this app that kept a refresh token in `localStorage`, that's gone - don't reintroduce it.

**The refresh-on-401 logic deduplicates concurrent refresh attempts.** The backend rotates refresh tokens (each one is single-use). If two API calls both hit a 401 at the same moment, they need to share one `/refresh` call, not each fire their own - the second one would fail since the first already rotated the token. This is handled in `src/lib/api.js` via a shared in-flight promise (see `api.test.js` for the exact scenario it protects against). Don't bypass `api.js`'s `request()` function for authenticated calls, or you'll lose this protection.

**`/token` takes form-encoded data, not JSON.** This is a FastAPI `OAuth2PasswordRequestForm` quirk on the backend - `/refresh`, `/logout`, and everything else are normal JSON. Already handled correctly in `api.login()`, just worth knowing if you're adding new auth-related calls.

**Single-college assumption.** `useCurrentCollege()` (in `src/context/CollegeContext.jsx`) picks the first college for a staff member and persists the choice in `localStorage`; the sidebar's college switcher only renders when a staff member actually belongs to more than one. There's exactly one place this decision is made, so extending it isn't a big lift if it's ever needed.

**Client-side pagination on a couple of endpoints.** `src/hooks/usePagination.js` slices an already-fully-fetched list rather than hitting a paginated backend endpoint - see the comment in that file for which lists this applies to and why. Staff/students/documents/queue lists use real server-side pagination via their hooks in `src/hooks/`.

## Project structure

```
src/
├── components/
│   ├── ui/                    # shadcn primitives (button, dialog, table, checkbox, ...)
│   ├── DashboardLayout.jsx    # sidebar, nav, college switcher, theme toggle
│   ├── ProtectedRoute.jsx
│   ├── ErrorBoundary.jsx
│   ├── ConfirmDialog.jsx      # shared "are you sure?" dialog
│   └── ...                    # feature components (StaffFormDialog, ReplyToQueryDialog, etc.)
├── context/
│   ├── AuthContext.jsx        # login/logout/session state
│   └── CollegeContext.jsx     # selected college + switcher state
├── hooks/                     # one file per resource - useStaff, useStudents, useDocuments, ...
├── lib/
│   ├── api.js                 # all backend calls go through here
│   ├── tokenStore.js          # in-memory access token
│   ├── dates.js                # shared date helpers (expiry-date inputs)
│   ├── leadScore.js / studentSignals.js  # display logic shared across pages
│   └── utils.js                # shadcn's cn() helper + a couple of shared style constants
├── pages/                      # one file per route, lazy-loaded in App.jsx (except Login)
├── App.jsx                     # router + providers setup
└── main.jsx
```

## Adding new shadcn components

This project is set up for the shadcn CLI (`components.json` is configured):

```bash
npx shadcn@latest add table
```

## Tests

`npm test` runs vitest. Coverage today is strongest on `src/lib/` (API client, formatting, scoring/signal logic) and a few pages/components with tricky interaction logic (`Login`, `StudentsList`, `ReplyToQueryDialog`). The data-fetching hooks in `src/hooks/` - especially the ones with optimistic updates and rollback (`useDocuments`'s bulk delete, `useLowConfidenceQueue`'s resolve mutation) - are the highest-value next place to add tests, since that's where a subtle regression would be easiest to miss by hand.
