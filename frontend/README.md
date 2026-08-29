# Admiq Frontend

Staff dashboard for Admiq. React + Vite + Tailwind v4 + shadcn/ui + React Router + TanStack Query.

## Setup

```bash
npm install
cp .env.example .env
```

Edit `.env` and set `VITE_API_BASE_URL` to your running backend (e.g. `http://localhost:8000` if you're running the Docker Compose stack locally).

```bash
npm run dev
```

## What's built so far

- **Auth flow, fully working**: login, silent session restore on page reload, automatic access-token refresh on expiry, logout. This is the foundation everything else depends on - see `src/context/AuthContext.jsx` and `src/lib/api.js` if you want to understand exactly how it works.
- **Dashboard shell**: sidebar nav, protected routing (redirects to `/login` if not authenticated).
- **Pages not yet built**: Low-confidence queue, Staff management, Students - currently placeholder "coming soon" screens, wired into the nav and routing so they're ready to be filled in.

## Important things to know before you touch this

**Access tokens live in memory only, refresh tokens live in localStorage.** This matches how the backend currently works (it returns the refresh token in the JSON response body, not as an httpOnly cookie). If the backend ever switches to httpOnly cookies for the refresh token, this frontend's token storage should be updated to match - `src/lib/tokenStore.js` is the only file that would need to change.

**The refresh-on-401 logic deduplicates concurrent refresh attempts.** Your backend rotates refresh tokens (each one is single-use). If two API calls both hit a 401 at the same moment, they need to share one `/refresh` call, not each fire their own - the second one would fail since the first already rotated the token. This is handled in `src/lib/api.js` via a shared in-flight promise. Don't bypass `api.js`'s `request()` function for authenticated calls, or you'll lose this protection.

**`/token` takes form-encoded data, not JSON.** This is a FastAPI `OAuth2PasswordRequestForm` quirk on the backend - `/refresh` and `/logout` are normal JSON. Already handled correctly in `api.login()`, just worth knowing if you're adding new auth-related calls.

## Project structure

```
src/
├── components/
│   ├── ui/              # shadcn components (button, input, label, card)
│   ├── ProtectedRoute.jsx
│   └── DashboardLayout.jsx
├── context/
│   └── AuthContext.jsx  # login/logout/session state
├── lib/
│   ├── api.js            # all backend calls go through here
│   ├── tokenStore.js      # access/refresh token storage
│   └── utils.js           # shadcn's cn() helper
├── pages/
│   ├── Login.jsx
│   ├── DashboardHome.jsx
│   └── ComingSoon.jsx     # placeholder for unbuilt pages
├── App.jsx                # router + providers setup
└── main.jsx
```

## Adding new shadcn components

This project is set up for the shadcn CLI (`components.json` is configured). To add a new component (e.g. a table):

```bash
npx shadcn@latest add table
```
