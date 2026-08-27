"""Municipality authority profiles (Petah Tikva spec §4).

An :class:`~.base.Authority` is a municipality-specific rule pack: department
names, terminology, example geometry numbers and evidence expectations - kept
out of the generic parser so a new municipality is a new profile, not a
change to :mod:`archagent.comments` or :mod:`archagent.constraints`.
"""

from .base import Authority, load_authority

__all__ = ["Authority", "load_authority"]
