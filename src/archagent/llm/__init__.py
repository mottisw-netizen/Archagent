"""Language-model layer.

Claude interprets language; the drawing driver measures geometry.  Nothing in
this package is allowed to produce a dimension, an area or a compliance
verdict - those come from measurement tools only (SKILL.md 17.14).
"""

from .client import (
    DEFAULT_EFFORT,
    DEFAULT_MODEL,
    AnthropicClient,
    CachingClient,
    LLMClient,
    LLMError,
    LLMResponse,
    ScriptedClient,
    from_env,
)
from .interpret import (
    Interpretation,
    LLMCommentInterpreter,
    describe_disagreement,
    inventory_from_driver,
    requirements_agree,
)

__all__ = [
    "AnthropicClient", "CachingClient", "DEFAULT_EFFORT", "DEFAULT_MODEL",
    "Interpretation", "LLMClient", "LLMCommentInterpreter", "LLMError", "LLMResponse",
    "ScriptedClient", "describe_disagreement", "from_env", "inventory_from_driver",
    "requirements_agree",
]
