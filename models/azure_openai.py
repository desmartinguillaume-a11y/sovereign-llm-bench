"""
Azure OpenAI client — optional live quality validation.

Set AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION in .env.
Not required for TCO computation.
"""

from __future__ import annotations

import os
from typing import Any


def call(prompt: str, model: str = "gpt-4o-mini", max_tokens: int = 512) -> dict[str, Any]:
    """
    Send a single prompt to Azure OpenAI.
    `model` must match the deployment name configured in your Azure workspace.
    Returns response dict including usage stats for token accounting.
    """
    try:
        from openai import AzureOpenAI  # type: ignore[import]
    except ImportError as e:
        raise ImportError("pip install openai to use live Azure OpenAI calls") from e

    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")

    if not api_key or not endpoint:
        raise EnvironmentError("AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT must be set")

    client = AzureOpenAI(api_key=api_key, azure_endpoint=endpoint, api_version=api_version)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return {
        "provider": "azure_openai",
        "model": model,
        "content": response.choices[0].message.content,
        "usage": {
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
        },
    }
