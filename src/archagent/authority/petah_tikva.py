"""The bundled Petah Tikva authority profile.

Loads from ``.claude/skills/municipal-permit-review/authorities/petah-tikva/``
in the repository checkout - a repo-level skill asset, the same way
``SKILL.md`` itself is, not a packaged wheel resource. :func:`load` therefore
only works from a source checkout; a project using an installed distribution
should load its own authority profile directory directly with
:func:`archagent.authority.load_authority`.
"""

from __future__ import annotations

from pathlib import Path

from .base import Authority, load_authority

#: src/archagent/authority/petah_tikva.py -> repo root is four parents up.
PROFILE_DIR = (Path(__file__).resolve().parents[3] / ".claude" / "skills" /
              "municipal-permit-review" / "authorities" / "petah-tikva")

_cached: Authority | None = None


def load(refresh: bool = False) -> Authority:
    """The Petah Tikva authority profile, cached after the first load."""
    global _cached
    if _cached is None or refresh:
        _cached = load_authority(PROFILE_DIR)
    return _cached
