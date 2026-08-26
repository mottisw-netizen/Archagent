# Archagent Revit host (Revit 2024)

A Revit add-in that exposes the **active document** over a small HTTP protocol on
loopback, so the Archagent agent can read the model, measure it, and - only after
the plan has been simulated and approved - apply a batch of changes inside a
single undoable transaction group.

The protocol is defined once, in Python, in
[`src/archagent/drawing/protocol.py`](../src/archagent/drawing/protocol.py).
`src/archagent/drawing/mock_host.py` is a working implementation of the same
protocol over a JSON model; it is both the test double and the executable
specification this add-in is written against.

```
Archagent (Python)                        Revit (Windows)
┌──────────────────────┐   HTTP/JSON      ┌───────────────────────────────┐
│ Orchestrator         │  127.0.0.1:8735  │ Archagent.Revit add-in        │
│  └ RevitDriver ──────┼─────────────────▶│  HostServer (HttpListener)    │
│      (drawing/revit) │                  │   └ RevitExecutor             │
└──────────────────────┘                  │      (ExternalEvent → Revit's │
                                          │       own API thread)         │
                                          │        └ Document             │
                                          └───────────────────────────────┘
```

## What this build status actually is

**The C# has not been compiled or run in this environment.** There is no Windows
and no Revit here, so `RevitAPI.dll` cannot be referenced and MSBuild cannot run.
What has been verified:

* every source file is present and syntactically balanced (braces/parens);
* the endpoints, action names, units, error codes and payload shapes match
  `protocol.py` field for field;
* the Python side (`RevitDriver`) runs a **complete pipeline end to end against a
  live host** - the mock host - and produces results identical to the
  file-based run, including batch apply, rollback on a bad action, and
  simulation that leaves the host untouched.

So: the Python half is proven against a live host; the C# half is written to the
same contract but still needs its first compile against real Revit assemblies.
Expect the usual first-compile friction (API signature drift between Revit
versions), not a redesign.

## Build

Requirements: Windows, Revit 2024 installed, .NET Framework 4.8 developer pack,
and either Visual Studio 2022 or the .NET SDK (`dotnet build` works - the project
is SDK-style and targets `net48`).

```powershell
cd revit-addin
dotnet build -c Release
```

The project finds Revit's assemblies at
`C:\Program Files\Autodesk\Revit 2024`. If Revit is installed elsewhere:

```powershell
dotnet build -c Release -p:RevitPath="D:\Autodesk\Revit 2024"
```

`RevitAPI.dll` and `RevitAPIUI.dll` are referenced with `<Private>false</Private>`
- they must **not** be copied next to the add-in, because the add-in is loaded
into Revit's own process where those assemblies already live. For the same reason
JSON is handled with `System.Web.Extensions` (part of the framework) rather than
Newtonsoft: Revit loads its own `Newtonsoft.Json`, and a second copy in the same
process is a classic add-in crash.

### Revit 2025 and later

Revit 2025+ hosts .NET 8. Change `<TargetFramework>` to `net8.0-windows` and
`<RevitVersion>` to the version you are building for; the only source changes are
the two places marked `REVIT2025` in `src/HostServer.cs`.

## Install

The `InstallAddin` target runs after every Windows build and copies:

* `Archagent.Revit.dll` → `%AppData%\Autodesk\Revit\Addins\2024\Archagent\`
* `Archagent.addin` → `%AppData%\Autodesk\Revit\Addins\2024\`

Restart Revit. Copying by hand works just as well; the manifest's `Assembly`
path is relative to the add-ins folder.

## Run

1. Open the permit project in Revit.
2. **Archagent** tab → **Start host**. The button reports the port it bound.
3. Point Archagent at it:

```bash
archagent run examples/project_he --source revit://127.0.0.1:8735
```

The host binds `http://127.0.0.1:{port}/` only - loopback, never a network
interface. Port and token are read from `%APPDATA%\Archagent\host.json`:

```json
{ "port": 8735, "token": "a-long-random-string" }
```

When a token is set, every request must carry it as `X-Archagent-Token`; pass the
same value to the driver (`RevitDriver(token=...)`). With no token the host still
answers loopback only, which is the right default for a single-workstation setup
and the wrong one if anything else on that machine is untrusted.

**Stop host** unbinds the listener. Closing Revit stops it too.

## Rules the add-in enforces

These are enforced in C#, not just in the Python caller, so a bug on the agent
side cannot damage the architect's model:

* **One writer.** `ApplyCommand` is the only code that opens a `Transaction`.
  Every other endpoint is read-only.
* **All or nothing.** `/apply` takes the whole action list, wraps it in one
  `TransactionGroup`, and either `Assimilate()`s it (one undo step for the user)
  or `RollBack()`s the group on the first failure and reports which action
  failed. A half-applied plan cannot exist.
* **No open transactions between requests.** Revit does not allow a transaction
  to span API contexts, so `/transaction/begin|commit|rollback` return
  `unsupported` with an explanation. Simulation happens on a local snapshot on
  the Python side instead.
* **`save_as` never overwrites the open document.** It refuses a target path
  equal to the document's own path; the original permit file is never written.
* **`create` is refused.** Placing new elements needs a family, a type, a level
  and a host - decisions that belong to the architect, not the agent. The agent
  reports the need instead of inventing geometry.
* **Everything crosses the wire in metres and m².** Revit's internal decimal
  feet stop at `Units.cs`.
* **Ids are `UniqueId`.** `ElementId` is not stable across sessions.

## Source map

| File | Role |
| --- | --- |
| `src/ArchagentApp.cs` | `IExternalApplication`; ribbon tab, Start/Stop, settings |
| `src/HostServer.cs` | `HttpListener`, token check, routing, error → HTTP status |
| `src/RevitExecutor.cs` | `IExternalEvent` pump: runs work on Revit's API thread and blocks the listener thread for the answer |
| `src/Protocol.cs` | endpoint/action/error constants - mirrors `protocol.py` |
| `src/Json.cs` | `System.Web.Extensions` reader/writer helpers |
| `src/Units.cs` | feet ↔ metres |
| `src/ElementView.cs` | Revit element → the wire shape (category map, bbox, parameters) |
| `src/Commands/QueryCommands.cs` | `/health` `/find` `/element` `/geometry` `/properties` `/sheets` |
| `src/Commands/MeasureCommand.cs` | `/measure` (width, length, height, area, count, setback, floor area) |
| `src/Commands/DistanceCommand.cs` | `/distance` `/overlap` `/clearance` |
| `src/Commands/ApplyCommand.cs` | `/apply` - the only writer |
| `src/Commands/ExportCommand.cs` | `/export` (PNG), `/save_as` |

## Testing without Revit

```bash
archagent-host examples/project_he/source/project.json --port 8735
archagent run examples/project_he --source revit://127.0.0.1:8735
```

The mock host speaks the same protocol, so anything that works against it is
exercising the exact code path that will talk to Revit - everything above the
driver, and the driver itself.
