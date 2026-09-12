# Deploying the monitoring stack to Render

Your backend is already a Render web service and your frontend is already on
Vercel - **neither needs any changes for this.** This only adds three new
Render services (Prometheus, Grafana, redis-exporter) that sit beside your
existing backend, plus one DB migration.

## 0. One-time setup, before touching Render

**Run the cost_events migration.** `backend/app/schema.sql` has a new
`cost_events` table. This repo has no migration tool (no Alembic) - the
schema.sql file is the source of truth, applied by hand. Open Supabase's
SQL Editor (or `psql` your `DATABASE_URL`) and run the `CREATE TABLE
cost_events (...)` block (and its `CREATE INDEX` lines) near the end of
`backend/app/schema.sql`. Skip everything else in that file - your other
tables already exist.

**Add two things to your EXISTING backend Render service** (Dashboard >
your backend service > Environment):
- `COST_REPORTING_TOKEN` - a long random string, e.g. `openssl rand -hex 32`.
  This is what gates `GET /internal/costs/{college_id}/stats`.
- `WHATSAPP_SESSION_MESSAGE_COST_USD` / `WHATSAPP_UTILITY_CONVERSATION_COST_USD`
  / `WHATSAPP_MARKETING_CONVERSATION_COST_USD` - optional, default to 0.0.
  Fill in from Meta Business Manager if you want WhatsApp cost to show up
  as non-zero.

Redeploy the backend once after adding these (or it'll pick them up on its
next natural deploy).

## 1. Fix two placeholders in `render.yaml` before syncing it

Open `render.yaml` and:
- Replace every `admiq-backend` with **your backend service's actual name**
  in the Render dashboard (Blueprint `fromService` references work across
  services outside the Blueprint, but only if the name matches exactly).
- Replace `region: oregon` on all three new services with whatever region
  your existing backend is deployed in. **Private networking only works
  within the same region** - if Prometheus ends up in a different region
  than your backend, it simply won't be able to reach it.

## 2. Get the values you'll be prompted for

The Blueprint will ask for these at sync time (they're marked `sync: false`
in `render.yaml` so they're never committed to git):

| Variable | Where to get it |
|---|---|
| `SUPABASE_METRICS_PASSWORD` | Whatever you set as the Supabase metrics endpoint password (same one that would've gone in `secrets/supabase_metrics_password.txt` locally) |
| `REDIS_ADDR` | Copy the exact value of `REDIS_URL` from your backend service's env vars |
| `GF_SECURITY_ADMIN_PASSWORD` | Pick a real password - this logs into Grafana |
| `GRAFANA_PG_HOST` | Supabase Dashboard > Project Settings > Database > Connection info (host, e.g. `db.<ref>.supabase.co`) |
| `GRAFANA_PG_USER` | Same page - usually `postgres`, but see the read-only role note below |
| `GRAFANA_PG_PASSWORD` | Same page - your Supabase DB password |

**Worth doing before you connect Grafana:** create a dedicated read-only
Postgres role in Supabase (`CREATE ROLE grafana_reader LOGIN PASSWORD
'...'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_reader;`)
instead of using your app's main `postgres` user. Grafana never needs to
write anything, and this limits the blast radius if that password ever
leaks.

## 3. Push, then sync the Blueprint

Commit `render.yaml`, `deploy/`, and the updated `grafana/` directory to
the branch Render deploys from. Then, in the Render Dashboard: **New >
Blueprint**, pick this repo, and Render will detect `render.yaml` and show
you the three new services (`admiq-prometheus`, `admiq-redis-exporter`,
`admiq-grafana`) with prompts for the values above. Confirm, and it builds
and deploys all three.

## 4. Open it

Once `admiq-grafana` finishes deploying, its URL is in the Render
dashboard (`https://admiq-grafana-xxxx.onrender.com` by default). Log in
with `admin` / whatever you set `GF_SECURITY_ADMIN_PASSWORD` to. Both
dashboards ("AdmiQ - Cost & Unit Economics" and "AdmiQ - Operations") are
already there under the **AdmiQ** folder - nothing left to configure.

## 5. Lock Grafana down further (recommended)

Grafana is the one new service here with a public URL, and it's showing
your internal cost data - worth tightening beyond just a strong password:

- **Simplest:** if your Render workspace is on a paid tier that supports
  it, add an IP allow list to `admiq-grafana` restricting it to your own
  IP(s) (Render Dashboard > service > Settings > Maintenance/Access, name
  varies by plan).
- **Most locked-down:** change `admiq-grafana`'s `type` in `render.yaml`
  from `web` to `pserv`. It then has **no public URL at all** - you reach
  it by running `render ssh` (or the dashboard's web shell) against any
  SSH-compatible service on the same private network and port-forwarding:
  `ssh -L 3000:<grafana-internal-host>:3000 <ssh-address-of-some-other-service>`,
  then open `http://localhost:3000` locally. More friction to open, but
  genuinely unreachable from the internet.

Either way: nothing in the Vercel frontend or the staff-facing app links to
Grafana or to `/internal/costs` - that separation from the last round of
changes still holds here.

## What's deliberately not included

- **node-exporter** - it reports on the host machine's `/proc`/`/sys`,
  which you don't have access to in Render's PaaS model. Render's own
  dashboard already gives you per-service CPU/memory graphs, which covers
  the same need.
- **Alertmanager / alert rules** - `prometheus.yml` used to reference both
  and neither actually existed (this would have failed to start even
  locally under docker-compose) - removed for now. Worth its own pass
  later if you want paging/alerting, not part of this change.
