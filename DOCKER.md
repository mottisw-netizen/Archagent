# Running Archagent in Docker

This packages the web application - the agent, the API, the browser UI - into
one image. It does **not** package the Revit/AutoCAD add-in: that runs
*inside* Revit or AutoCAD, on Windows, as its own native install
(`revit-addin/README.md`, `autocad-addin/README.md`). The two talk to each
other over the network exactly as they would without Docker; this file is
about the one detail Docker changes - how the container reaches something
listening on the host machine.

## What this build status actually is

**The image has not been built or run in this environment.** This session's
network policy blocks Docker Hub (`docker build` fails pulling the
`python:3.12-slim` base image - a proxy/egress restriction of this sandbox,
not a Dockerfile problem), so an end-to-end `docker build && docker run` could
not be completed here. What *has* been verified:

* every Python dependency the image installs (`fastapi`, `uvicorn`,
  `anthropic`, `ezdxf`, `claude-agent-sdk`) is the exact same set already
  installed and exercised by the tests passing in this repository - the
  Dockerfile does not introduce a new, untested Python dependency. The `claude`
  CLI itself (installed via `npm`) is a separate, prebuilt binary this repo
  does not test - only that `docker build` installs it and puts it on PATH.
* the Dockerfile was reviewed line by line against how `archagent-web` is
  actually invoked and configured (`ARCHAGENT_WORKSPACE`, `--host`/`--port`,
  `examples/` needing to sit next to `src/` for the bundled projects to
  appear - see `web/projects.py`);
* the shell script (`run.sh`) was checked with `bash -n` (syntax only, no
  Docker available to run it end to end here).

Run `./run.sh` (or `run.bat` on plain Windows) yourself the first time and
watch the build - it is a standard Python image and should behave exactly as
written, but this is the one piece of this project not proven end to end by
an actual run in this session, and you should treat the first launch as that
proof.

## Quick start

```bash
./run.sh                              # Linux, macOS, WSL, Git Bash
# or, from plain Windows cmd/PowerShell, no WSL needed:
run.bat
```

Both build the image and start it on `http://127.0.0.1:8000`. Project data
(uploaded files, versions, run output) persists in a Docker volume
(`archagent-data`) across restarts. To use an Anthropic API key from the
start: `ANTHROPIC_API_KEY=sk-ant-... ./run.sh` (or set it before `run.bat` on
Windows) - or paste it into the connection dialog in the browser once it is
up, which is kept in the container's memory only, never written to disk.

`docker compose up --build` does the same thing, declaratively, if you prefer
Compose.

## Connecting to a live Revit/AutoCAD from inside the container

This is the one thing that is genuinely different with Docker, and it is a
networking detail, not a limitation of the product: **inside a container,
`127.0.0.1` means the container itself**, not the Windows machine the
container is running on. Revit (with the Archagent add-in loaded and
started) is listening on the *host* machine's loopback - so from inside the
container, that address is `host.docker.internal`, not `127.0.0.1`.

Concretely, on a Windows machine running both Docker Desktop and Revit:

1. Open the permit project in Revit; **Archagent** tab → **Start host**. Say
   it reports port 8735.
2. Start Archagent in Docker (`run.bat` or `run.sh`).
3. Open `http://localhost:8000` in a browser on that same machine.
4. In the launch screen's **שרטוט חי** (live drawing) field, enter:
   ```
   revit://host.docker.internal:8735
   ```
   **not** `revit://127.0.0.1:8735` - that would point the container at
   itself, and it would report the add-in unreachable.
5. **בדיקת חיבור** (check connection) should report the open document's own
   name, the Revit version, and its element count - the proof it found the
   right file.
6. Run the review. The customer watches it happen in Revit itself, live, and
   approves each decision in the browser exactly as an uncontainerized run
   would - Docker only changes the address in step 4.

The same applies to the AutoCAD/Civil 3D add-in: `autocad://host.docker.internal:8736`.

`docker-compose.yml` and `run.sh`/`run.bat` already add the
`host.docker.internal` alias explicitly (`--add-host`/`extra_hosts`) so this
resolves the same way on Linux Docker Engine too, where it is not automatic
the way it is on Docker Desktop (Windows/Mac).

If Revit is on a **different** machine from the one running the container,
use that machine's real network address instead of `host.docker.internal`
(e.g. `revit://192.168.1.50:8735`) - the add-in binds to loopback only by
design, so it has to be reached from wherever it is actually running, and
`host.docker.internal` only ever means "the machine hosting this container."

## Connecting the "Claude Code" engine (your Claude.ai Pro/Max subscription)

The web app's launch screen lets you pick which engine drives a run:
**pipeline** (in-process, needs an Anthropic API key or runs rules-only with
`--no-llm`) or **claude-code** (`web/engines.py: ClaudeCodeEngine`, drives the
same pipeline through an actual Claude Code session). The image now installs
the `claude` CLI itself (via `npm`, alongside the `claude-agent-sdk` Python
package), so `claude-code` is available out of the box - it just needs to be
logged in once, the same as installing Claude Code on a normal machine.

You do **not** need an `ANTHROPIC_API_KEY` for this - a Claude.ai Pro/Max
subscription authenticates through your browser instead:

1. Start Archagent as usual (`./run.sh`, `run.bat`, or `docker compose up`).
2. In a **second** terminal, open an interactive session inside the running
   container:
   ```bash
   docker exec -it archagent claude
   ```
   (with Compose: `docker compose exec archagent claude`.)
3. The CLI walks you through picking an auth method the first time - choose
   the Claude.ai account / subscription option, not the API key option. It
   prints a URL (and a code); open it in a browser on any device signed into
   your Claude.ai account and approve it.
4. Exit that session (`Ctrl+D` or `exit`). The login itself is saved under
   `/root/.claude` inside the container, which is a separate named Docker
   volume (`archagent-claude-auth`) - so it survives container restarts and
   even `docker compose up --build` again. You only do this once per volume.
5. Back in the web app, pick **claude-code** as the engine for a run - it now
   authenticates as you, through your subscription, with no key stored
   anywhere in the image or in plaintext on disk.

To start over with a fresh login (e.g. switching accounts), remove the
volume: `docker volume rm archagent-claude-auth` (Compose) or
`docker volume rm archagent-claude-auth` after `docker rm -f archagent` (plain
`run.sh`/`run.bat`) - then repeat the steps above.

## What's inside, and what isn't

* Installed: the web app (`archagent-web`), the CLI, the JSON reference
  driver, the headless DXF driver (`ezdxf`), and the `claude` CLI (Node-based,
  via `npm`) for the "claude-code" engine - see the section above to log it
  in. A plain `.dxf` opens and edits with nothing else installed, in the
  container or out of it.
* `poppler-utils` (`pdftotext`) for reading PDF municipal comments.
* **Not installed**: the ODA File Converter, for a real `.dwg` (not `.dxf`)
  file source - it is free but not open source, so it is never bundled; a
  `.dwg` source reports that reason explicitly rather than failing
  silently. Install it in the container (or point `PATH` at a copy mounted
  in) if you need it.
* **Not included at all**: `revit-addin/`, `autocad-addin/` - Windows-native,
  built and installed separately, as documented in their own READMEs.
