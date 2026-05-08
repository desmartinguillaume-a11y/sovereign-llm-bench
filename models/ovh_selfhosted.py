"""
OVH self-hosted inference client — optional live quality validation.

Assumes a vLLM-compatible OpenAI endpoint running on OVH infrastructure.
Set OVH_INFERENCE_BASE_URL in .env (e.g. http://your-ovh-instance:8000/v1).
Not required for TCO computation.
"""

from __future__ import annotations

import os
from typing import Any


def call(prompt: str, model: str = "meta-llama/Meta-Llama-3-70B-Instruct", max_tokens: int = 512) -> dict[str, Any]:
    """
    Send a single prompt to a vLLM-served endpoint on OVH.
    Uses the OpenAI-compatible API exposed by vLLM.
    """
    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError as e:
        raise ImportError("pip install openai to use live OVH self-hosted calls") from e

    base_url = os.getenv("OVH_INFERENCE_BASE_URL")
    if not base_url:
        raise EnvironmentError("OVH_INFERENCE_BASE_URL not set (e.g. http://host:8000/v1)")

    # vLLM's OpenAI-compatible endpoint does not require a real API key,
    # but the openai client requires a non-empty string.
    client = OpenAI(api_key="not-used", base_url=base_url)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return {
        "provider": "ovh_selfhosted",
        "model": model,
        "content": response.choices[0].message.content,
        "usage": {
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
        },
    }
