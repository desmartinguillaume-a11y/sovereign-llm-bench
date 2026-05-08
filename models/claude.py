"""
Anthropic Claude API client — optional live quality validation.

Set ANTHROPIC_API_KEY in .env to use. Not required for TCO computation.
"""

from __future__ import annotations

import os
from typing import Any


def call(prompt: str, model: str = "claude-haiku-3-5", max_tokens: int = 512) -> dict[str, Any]:
    """
    Send a single prompt to the Anthropic API.
    Returns the full response dict including usage stats for token accounting.
    """
    try:
        import anthropic  # type: ignore[import]
    except ImportError as e:
        raise ImportError("pip install anthropic to use live Claude calls") from e

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set in environment")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return {
        "provider": "anthropic",
        "model": model,
        "content": response.content[0].text,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }
