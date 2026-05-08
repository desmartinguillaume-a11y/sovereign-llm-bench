"""
Mistral API client — optional live quality validation.

Set MISTRAL_API_KEY in .env to use. Not required for TCO computation.
"""

from __future__ import annotations

import os
from typing import Any


def call(prompt: str, model: str = "mistral-small-latest", max_tokens: int = 512) -> dict[str, Any]:
    """
    Send a single prompt to the Mistral API.
    Returns the full response dict including usage stats for token accounting.
    """
    try:
        from mistralai import Mistral  # type: ignore[import]
    except ImportError as e:
        raise ImportError("pip install mistralai to use live Mistral calls") from e

    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise EnvironmentError("MISTRAL_API_KEY not set in environment")

    client = Mistral(api_key=api_key)
    response = client.chat.complete(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return {
        "provider": "mistral",
        "model": model,
        "content": response.choices[0].message.content,
        "usage": {
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
        },
    }
