# Archagent AutoCAD / Civil 3D host

An add-in that exposes the **active AutoCAD or Civil 3D drawing** over the same
loopback HTTP protocol as the Revit add-in, so the Archagent agent can read a
consultant's DWG, measure it, and - only after a plan has been simulated and
approved - apply a batch of changes inside one transaction (one undo step).

The protocol is defined once, in Python, in
[`src/archagent/drawing/protocol.py`](../src/archagent/drawing/protocol.py), and
is identical to the one `revit-addin/` speaks - that is the whole point of the
adapter design: one contract, every host. `src/archagent/drawing/mock_host.py`
implements it over a JSON model and is both the test double and the executable
specification this add-in is written against; `src/archagent/drawing/dwg.py`
(`DwgDriver`) is a two-line subclass of the Revit driver, because the client
side needed nothing new either.

## What this build status actually is

**The C# has not been compiled or run in this environment** - no Windows, no
AutoCAD, same limitation as `revit-addin/`. What has been verified:

* every endpoint, action, error code and payload shape matches `protocol.py`
  and mirrors `revit-addin/` field for field;
* the **Python side is fully proven**: `DwgAdapter`/`DwgDriver` run a complete
  pipeline end to end against the mock host addressed as `autocad://...`, in a
  run that simultaneously edits a live "Revit" host and a live "AutoCAD" host
  and merges the result - see `tests/test_multi_source.py` and
  `tests/test_adapters.py`.
* the C# is written to the identical contract, following the same patterns as
  the Revit add-in (which itself is unverified C# but structurally complete).

The one piece with no Revit-side precedent at all is **exporting a picture**
(`ExportCommand.PlotToPng`): AutoCAD has no single "export image" call the way
Revit does, so it drives the Plot API against the built-in `PublishToWeb
PNG.pc3` device. Plot device names and behaviour vary by AutoCAD version and
locale more than anything else in this add-in - if one part needs adjustment on
first real use, it is this one.

## Why a DWG entity needs tagging, and how

Revit elements arrive typed - a family, a category - out of the box. A plain
AutoCAD `Polyline` or `BlockReference` does not, so this add-in reads an
entity's category two ways, in order:

1. **XDATA** under the registered application `ARCHAGENT`: one JSON string per
   entity (`category`, `label`, `level`, `sheet`, `properties`). This is what
   `set_text`/`set_parameter` write, and what a firm's own drawing-prep step
   would write for entities the agent should be able to act on.
2. Failing that, the entity's **layer name**, matched against the same
   AIA-style keywords the reference JSON model already uses - `A-PARK` →
   parking, `A-BLDG` → building, `A-ROAD` → driveway, `A-DIMS` → dimension, and
   so on (`EntityView.LayerCategories`).

A drawing that already follows a layer-naming standard participates with no
prep at all; one that does not needs entities tagged via XDATA first. Either
way, an entity with neither is read as `"generic"` - visible, measurable by
bounding box, but not matched by a category selector.

## Civil 3D scope

Civil 3D is AutoCAD with an additional API layer, so this same DLL loads into
either host and works identically for plain AutoCAD entities - lines,
polylines, block references, dimensions, tables. It does **not** read or write
Civil 3D-specific objects (an `Alignment`, a `Corridor`, a pipe network); a
site plan built from those needs its extents exported to plain geometry (or
tagged some other way) before Archagent can measure it. Extending
`EntityView`/`ApplyCommand` to the Civil 3D API is a real next step, not
attempted here.

## Build

Requirements: Windows, AutoCAD or Civil 3D 2024 installed, .NET Framework 4.8
developer pack, and the .NET SDK or Visual Studio 2022.

```powershell
cd autocad-addin
dotnet build -c Release
```

The project finds AutoCAD's managed assemblies at
`C:\Program Files\Autodesk\AutoCAD 2024` (Civil 3D installs alongside AutoCAD
and exposes the same assemblies). If installed elsewhere:

```powershell
dotnet build -c Release -p:AcadPath="D:\Autodesk\AutoCAD 2024"
```

`accoremgd.dll`, `acdbmgd.dll` and `acmgd.dll` are referenced with
`<Private>false</Private>` - they must not be copied next to the add-in, for
the same reason as Revit: the add-in loads into the host's own process, where
those assemblies already live. JSON uses `System.Web.Extensions`, not
Newtonsoft, for the same reason `revit-addin/` does.

## Install

`InstallBundle` runs after every Windows build and copies the DLL plus
`Archagent.bundle/PackageContents.xml` into
`%AppData%\Autodesk\ApplicationPlugins\Archagent.bundle\`, AutoCAD's standard
autoload location (`LoadOnAutoCADStartup="true"` in the manifest) - no
`NETLOAD` needed. Restart AutoCAD or Civil 3D.

## Run

1. Open the consultant's drawing in AutoCAD or Civil 3D.
2. Type **`ARCHAGENT`** at the command line to start the host; type it again to
   stop it. The command line reports the port.
3. Point Archagent at it - `autocad://` and `civil3d://` both resolve to this
   same add-in:

```bash
archagent run project --source revit://127.0.0.1:8735 --source autocad://127.0.0.1:8736
```

Port and token are read from `%APPDATA%\Archagent\host_acad.json` (a separate
file from the Revit add-in's, since both can run on the same machine on
different ports):

```json
{ "port": 8736, "token": "a-long-random-string" }
```

## Rules the add-in enforces

Same posture as `revit-addin/`, adapted to AutoCAD's model:

* **One writer.** `ApplyCommand` is the only code that opens a write
  `Transaction`. In AutoCAD a single transaction already is one undo step, so
  a whole plan runs inside one transaction and is aborted as a whole on any
  failure - a half-applied plan cannot exist.
* **No open transactions between requests**, for the identical reason as
  Revit: `/transaction/begin|commit|rollback` return `unsupported`. Simulation
  happens on a local snapshot on the Python side.
* **`save_as` never overwrites the open document** - it refuses a target path
  equal to the drawing's own path.
* **`create` is refused.** A new polyline or block needs a family/type-like
  decision - a block definition, a layer, a level - that belongs to the
  architect, not the agent.
* **Everything crosses the wire in metres and m².** `Units.cs` reads the
  drawing's own `INSUNITS` and converts at the boundary, since (unlike Revit's
  fixed internal feet) a DWG's unit is whatever the consultant set.
* **Ids are `Handle`s**, not `ObjectId`s - a handle is stable across sessions.

## Source map

| File | Role |
| --- | --- |
| `src/ArchagentApp.cs` | `IExtensionApplication`; the `ARCHAGENT` command, settings |
| `src/HostServer.cs` | `HttpListener`, token check, routing, error → HTTP status |
| `src/AcadExecutor.cs` | Marshals work onto AutoCAD's thread via `ExecuteInApplicationContext`, with the document locked |
| `src/Protocol.cs` | endpoint/action/error constants - mirrors `protocol.py` and `revit-addin/src/Protocol.cs` |
| `src/Json.cs` | `System.Web.Extensions` reader/writer helpers |
| `src/Units.cs` | `INSUNITS` ↔ metres |
| `src/EntityView.cs` | entity → the wire shape (XDATA tag, layer-name category, bbox) |
| `src/Commands/QueryCommands.cs` | `/health` `/find` `/element` `/geometry` `/properties` `/sheets` |
| `src/Commands/MeasureCommand.cs` | `/measure` |
| `src/Commands/DistanceCommand.cs` | `/distance` `/overlap` `/clearance` |
| `src/Commands/ApplyCommand.cs` | `/apply` - the only writer |
| `src/Commands/ExportCommand.cs` | `/export` (PNG via the Plot API), `/save_as` |
| `src/Commands/HighlightCommand.cs` | `/highlight` |

## Testing without AutoCAD

```bash
archagent-host examples/project/source/project.json --port 8736
archagent run examples/project --source autocad://127.0.0.1:8736
```

The mock host speaks the same protocol under any URL scheme, so this exercises
the exact code path that will talk to AutoCAD - everything above the driver,
and the driver itself.
