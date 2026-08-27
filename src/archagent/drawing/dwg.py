"""Driver for a live AutoCAD or Civil 3D document, over the same host protocol.

There is nothing Revit-specific in :class:`~archagent.drawing.revit.RevitDriver`
- it is an HTTP client for ``archagent.drawing.protocol``, and that protocol was
written once for every host to share (``revit-addin/README.md``). A DWG host
(the AutoCAD/Civil 3D add-in in ``autocad-addin/``) speaks the identical wire
format, so this is a subclass in name only: it exists so a DWG source shows up
as ``dwg``, not ``revit``, in the workspace and the change set.
"""

from __future__ import annotations

from .revit import RevitDriver


class DwgDriver(RevitDriver):
    """A live AutoCAD or Civil 3D document, reached through the Archagent add-in."""

    name = "dwg"
    host_label = "AutoCAD/Civil 3D"
