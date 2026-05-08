#!/usr/bin/env python3
"""
sovereign-llm-bench — point d'entrée unique.

Usage:
    python run.py                  # TCO computation only (no API calls)
    python run.py --validate       # TCO + live API quality spot-check
    python run.py --scenario S1    # TCO for a single scenario
    python run.py --quiet          # suppress terminal table, write CSV only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent))

from benchmark.report import build as build_report
from benchmark.runner import run


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sovereign LLM Bench — TCO comparatif EU",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run live API quality spot-check (requires API keys in .env)",
    )
    parser.add_argument(
        "--scenario",
        metavar="ID",
        help="Restrict computation to a single scenario (e.g. S1, S2, S3, S4)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress terminal table; write CSV only",
    )
    args = parser.parse_args()

    # Load .env if present (no hard dependency on python-dotenv)
    _load_dotenv()

    results, breakevens = run(verbose=not args.quiet)

    report_path = build_report(results, breakevens)
    print(f"  {report_path}")

    if args.validate:
        _run_validation(args.scenario)


def _load_dotenv() -> None:
    """Best-effort .env loader; skips silently if file or package absent."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore[import]
        load_dotenv(env_path)
    except ImportError:
        # Manual fallback: parse KEY=VALUE lines
        with open(env_path) as f:
            import os
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())


def _run_validation(scenario_filter: str | None) -> None:
    """Quick live API spot-check using a sample French prompt."""
    import importlib

    prompt = (
        "Résume en 3 points le contenu suivant : "
        "L'intelligence artificielle transforme les centres d'appels en permettant "
        "l'analyse en temps réel des conversations, la suggestion de réponses aux agents "
        "et la génération automatique de comptes-rendus post-appel."
    )

    providers = {
        "mistral": ("models.mistral", "mistral-small-latest"),
        "anthropic": ("models.claude", "claude-haiku-3-5"),
        "azure_openai": ("models.azure_openai", "gpt-4o-mini"),
        "ovh_selfhosted": ("models.ovh_selfhosted", "meta-llama/Meta-Llama-3-70B-Instruct"),
    }

    print("\n── Live API Validation ─────────────────────────────────────────")
    for provider, (module_path, model) in providers.items():
        try:
            mod = importlib.import_module(module_path)
            result = mod.call(prompt, model=model, max_tokens=200)
            print(f"\n[{provider}] {result['model']}")
            print(f"  tokens: {result['usage']['input_tokens']} in / {result['usage']['output_tokens']} out")
            print(f"  {result['content'][:200]}")
        except Exception as e:
            print(f"\n[{provider}] SKIP — {e}")


if __name__ == "__main__":
    main()
