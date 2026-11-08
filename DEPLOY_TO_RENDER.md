# Deploying to Render — checklist

This repository is set up for a fully automated Render Blueprint deployment. The
Blueprint is in `render.yaml` and describes:

- a Python Web Service built with `pip install -r requirements.txt`
- started with `uvicorn app.server:app --host 0.0.0.0 --port $PORT`
- with `PYTHON_VERSION=3.12.0`
- with a 1 GB persistent disk mounted at `/app/app/_generated`

There is no `runtime.txt` in the repository. Do not add one unless you
deliberately want to override Python 3.12; if you do, it must say `3.12.0` and
agree with `render.yaml` and the `Dockerfile`.

## Before you connect the repo

1. Create the empty public repository on GitHub if you have not already:
   `Reverb135b7/cradle-to-gate-hdpe`
2. Push the local `main` branch once so the Blueprint has a branch to build
   from:
   ```bash
   git push -u origin main
   ```
3. Confirm the push landed:
   ```bash
   git ls-remote --heads origin
   ```
   You should see `refs/heads/main` pointing at the same commit as local
   `HEAD`.

## Environment variables

The Blueprint declares the following environment variables. Render will set
these automatically from `render.yaml` when you apply the Blueprint.

| Variable | Value | Notes |
| --- | --- | --- |
| `PYTHON_VERSION` | `3.12.0` | Keep this aligned with the Dockerfile |
| `HOST` | `0.0.0.0` | Required only if you run outside Render; Render injects its own bind |
| `PORT` | `$PORT` | Render injects the real port at runtime |
| `GENERATED_DIR` | `/app/app/_generated` | Must match the disk mount path |
| `OPENLCA_HOST` | `127.0.0.1` | Unused on Render unless you run an openLCA IPC server there |
| `OPENLCA_PORT` | `8080` | Unused on Render unless you run an openLCA IPC server there |

For the first deploy, **leave openLCA disabled**. The dashboard and LCA
console both work without it. The openLCA card and
`GET /api/lca/openlca/methods` will return `503` when there is no openLCA IPC
server, which is expected behavior, not a deployment failure.

## Persistent disk

The service writes generated outputs into `GENERATED_DIR`, which is mounted from
a persistent disk. This is what makes these endpoints survive redeploys:

- `POST /api/report` writes the PDF report and figures into
  `$GENERATED_DIR/<run_id>/`
- `GET /lca/files/openlca/characterisation_coverage.csv` writes a coverage CSV
  into `$GENERATED_DIR/openlca_characterisation_coverage.csv`

If the disk is not attached, report generation still runs, but the generated
files are lost on the next redeploy or restart.

## What works on the first deploy

- `/` — PCF control room
- `/lca` — LCA study console
- `GET /api/meta` — parameter metadata, defaults, presets
- `POST /api/simulate` — full PCF recompute
- `POST /api/report` — on-demand PDF report into the mounted disk
- `GET /api/lca` — LCA console payload
- `POST /api/lca/compute` — primary-data recompute
- `GET /lca/files/...` — serves files that already exist on the mounted disk

What does **not** work without extra infrastructure:

- The openLCA cross-check card and `GET /api/lca/openlca/methods` require a
  live openLCA IPC server

## First-deploy acceptance criteria

- Service health endpoint responds: `GET /api/health` returns `{"status":"ok"}`
- The two dashboards render in a browser
- `POST /api/lca/compute` returns a focused LCA recompute payload
- `POST /api/report` returns a run id and a `/generated/...` URL, and the PDF
  is retrievable from that URL
- The openLCA card shows the graceful offline state instead of crashing

## Rollback note

Render keeps previous deployments. If a deploy introduces a problem, roll back
to the previous successful deployment from the Render dashboard before changing
the source. Do not force-push over a live production service unless you intend
to replace the current deployment.
