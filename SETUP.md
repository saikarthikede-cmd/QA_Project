# Sharing This Project & Running It On a New Device

Two ways to hand this off: **git** (recommended — teammate gets updates later
with `git pull`) or a **zip** (one-time snapshot, no git needed on their end).

## 1. Share it

### Option A — Git (recommended)

On your machine, push what you have:

```powershell
git add -A
git commit -m "your message"
git push
```

Send them the repo URL:

```
https://github.com/saikarthikede-cmd/QA_PROJECTS.git
```

### Option B — Zip (no git needed)

Zip the folder but **exclude** these — they're either huge, machine-specific,
or regenerated automatically, and shipping them bloats the zip for nothing:

```
.venv312/       (your local Python virtual env — 100s of MB)
.git/           (only needed if they'll use git themselves)
__pycache__/    (every app has one, all regenerated automatically)
.pytest_cache/
logs/
```

In PowerShell, from one level above the project folder:

```powershell
Compress-Archive -Path "QA_Projects-main" -DestinationPath "QA_Projects-main.zip" -Force
```

(This still includes `.venv312`/`.git` — for a truly clean zip, copy the
folder somewhere temporary first, delete those four items, then zip that
copy. Not worth automating for an occasional handoff.)

## 2. Set it up on a new device

Nothing to configure first — **no `.env` file, no API key setup**. Each app
asks the person running it to pick a provider (Groq or OpenAI) and paste
their own key the moment its page loads.

### Option A — Docker (recommended: one command, no Python install needed)

Prerequisite: [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.

```powershell
git clone https://github.com/saikarthikede-cmd/QA_PROJECTS.git
cd QA_PROJECTS
.\docker-run.ps1
```

That builds all 7 containers, waits for them to actually respond, then
prints the URL for each one. Open the dashboard at http://localhost:8000,
or any app directly (8001-8006).

Stop everything later with:

```powershell
docker compose down
```

### Option B — Local Python (no Docker)

Prerequisite: **Python 3.11** installed (`py -3.11` must work).

```powershell
git clone https://github.com/saikarthikede-cmd/QA_PROJECTS.git
cd QA_PROJECTS
py -3.11 -m pip install -r requirements.txt
.\run_all.ps1
```

Same result: dashboard at http://localhost:8000, apps on 8001-8006. Stop
them with `.\run_all.ps1` again (it kills existing instances before
restarting) or by closing the terminal windows.

To run just one app instead of all six: `.\run.ps1 <1-6>`.

## 3. First use (either option)

Open any app — a popup blocks the page asking you to pick **Groq** or
**OpenAI** and paste your own API key. It's validated against that
provider's real API before the app unlocks. The key is held in memory only
for that run; refreshing the page or restarting asks again.
