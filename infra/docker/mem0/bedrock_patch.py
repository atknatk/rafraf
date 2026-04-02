"""
Bedrock response_format compatibility patch for mem0 REST server.

mem0 >=1.0.9 passes `response_format` kwarg to `generate_response()`,
but AWSBedrockLLM does not accept it, causing fact extraction to fail.

This module patches the Bedrock LLM class at import time so the
unsupported kwarg is silently stripped.

Usage: Import this module before mem0 initializes its LLM.
  import bedrock_patch  # noqa: F401
"""

from __future__ import annotations


def apply_patch() -> None:
    """Monkey-patch AWSBedrockLLM.generate_response to strip response_format."""
    try:
        from mem0.llms.aws_bedrock import AWSBedrockLLM
    except ImportError:
        # Not using Bedrock — nothing to patch
        return

    _original = AWSBedrockLLM.generate_response

    def _patched(self: AWSBedrockLLM, messages: list[dict[str, str]], **kwargs: object) -> str:  # type: ignore[override]
        kwargs.pop("response_format", None)
        return _original(self, messages, **kwargs)

    AWSBedrockLLM.generate_response = _patched  # type: ignore[assignment]


apply_patch()
