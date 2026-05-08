"""
TCO calculator for sovereign LLM deployments.

Computes daily / monthly / annual cost for each (scenario, provider, model)
combination using static pricing from config/pricing.yaml.

OVH throughput estimated via the llmfit bandwidth formula:
    tps = (bandwidth_gbps / model_size_gb) * efficiency_factor
See: https://github.com/AlexsJones/llmfit (src/fit.rs + src/hardware.rs)

No API calls are made here — fully offline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).parent.parent / "config"
WORKING_DAYS_PER_MONTH = 22
MONTHS_PER_YEAR = 12


@dataclass
class TCOResult:
    scenario_id: str
    scenario_name: str
    provider: str
    model_id: str
    model_display_name: str
    tokens_input_per_day: int
    tokens_output_per_day: int
    cost_day_eur: float
    cost_month_eur: float
    cost_year_eur: float
    gpus_required: int = 1
    cost_per_million_tokens_eur: float = 0.0
    pricing_status: str = ""
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "provider": self.provider,
            "model": self.model_display_name,
            "tokens_input_day": self.tokens_input_per_day,
            "tokens_output_day": self.tokens_output_per_day,
            "cost_day_eur": round(self.cost_day_eur, 2),
            "cost_month_eur": round(self.cost_month_eur, 2),
            "cost_year_eur": round(self.cost_year_eur, 2),
            "cost_per_m_tokens_eur": round(self.cost_per_million_tokens_eur, 4),
            "gpus_required": self.gpus_required,
            "pricing_status": self.pricing_status,
            "notes": self.notes,
        }


@dataclass
class BreakevenResult:
    scenario_id: str
    scenario_name: str
    reference_provider: str = "ovh_selfhosted"
    api_provider: str = ""
    api_model: str = ""
    selfhosted_cost_month_eur: float = 0.0
    api_cost_month_eur: float = 0.0
    breakeven_months: float = 0.0
    cheaper_at_scale: str = ""
    notes: str = ""


class TCOCalculator:
    """Compute TCO for all (scenario, provider) pairs from static YAML config."""

    def __init__(
        self,
        pricing_path: Path = CONFIG_DIR / "pricing.yaml",
        scenarios_path: Path = CONFIG_DIR / "scenarios.yaml",
    ) -> None:
        self.pricing = self._load_yaml(pricing_path)
        self.scenarios = self._load_yaml(scenarios_path)
        self.usd_to_eur: float = self.pricing["metadata"]["usd_to_eur"]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_all(self) -> list[TCOResult]:
        results: list[TCOResult] = []
        for scenario_id, scenario in self.scenarios["scenarios"].items():
            for provider_id in self.pricing["providers"]:
                result = self._compute_one(scenario_id, scenario, provider_id)
                results.append(result)
        return results

    def compute_breakeven(self, results: list[TCOResult]) -> list[BreakevenResult]:
        """Compare OVH self-hosted against each API provider per scenario."""
        breakevens: list[BreakevenResult] = []

        by_scenario: dict[str, dict[str, TCOResult]] = {}
        for r in results:
            by_scenario.setdefault(r.scenario_id, {})[r.provider] = r

        for scenario_id, providers in by_scenario.items():
            selfhosted = providers.get("ovh_selfhosted")
            if selfhosted is None:
                continue

            for provider_id, api_result in providers.items():
                if provider_id == "ovh_selfhosted":
                    continue

                be = BreakevenResult(
                    scenario_id=scenario_id,
                    scenario_name=selfhosted.scenario_name,
                    api_provider=provider_id,
                    api_model=api_result.model_display_name,
                    selfhosted_cost_month_eur=selfhosted.cost_month_eur,
                    api_cost_month_eur=api_result.cost_month_eur,
                )

                if selfhosted.cost_month_eur < api_result.cost_month_eur:
                    diff = api_result.cost_month_eur - selfhosted.cost_month_eur
                    be.cheaper_at_scale = "ovh_selfhosted"
                    be.notes = f"OVH économise €{diff:,.0f}/mois vs {provider_id}"
                else:
                    diff = selfhosted.cost_month_eur - api_result.cost_month_eur
                    be.cheaper_at_scale = provider_id
                    be.notes = f"API moins chère de €{diff:,.0f}/mois"

                # Breakeven = capex proxy (12 mois GPU) / économie mensuelle
                if api_result.cost_month_eur > selfhosted.cost_month_eur:
                    monthly_saving = api_result.cost_month_eur - selfhosted.cost_month_eur
                    capex_proxy = self._monthly_gpu_cost_eur(scenario_id) * 12
                    be.breakeven_months = capex_proxy / monthly_saving if monthly_saving > 0 else math.inf
                else:
                    be.breakeven_months = math.inf

                breakevens.append(be)

        return breakevens

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_one(self, scenario_id: str, scenario: dict, provider_id: str) -> TCOResult:
        model_id = scenario["model_selection"][provider_id]
        provider_cfg = self.pricing["providers"][provider_id]

        tokens_in = scenario["tokens_input_per_day"]
        tokens_out = scenario["tokens_output_per_day"]

        if provider_id == "ovh_selfhosted":
            return self._compute_selfhosted(scenario_id, scenario, provider_id, provider_cfg, model_id, tokens_in, tokens_out)
        else:
            return self._compute_api(scenario_id, scenario, provider_id, provider_cfg, model_id, tokens_in, tokens_out)

    def _compute_api(
        self,
        scenario_id: str,
        scenario: dict,
        provider_id: str,
        provider_cfg: dict,
        model_id: str,
        tokens_in: int,
        tokens_out: int,
    ) -> TCOResult:
        model_cfg = provider_cfg["models"][model_id]
        currency = model_cfg.get("currency", "USD")

        price_in = model_cfg["input_per_1m_tokens"] / 1_000_000
        price_out = model_cfg["output_per_1m_tokens"] / 1_000_000

        cost_day = tokens_in * price_in + tokens_out * price_out

        # Convert to EUR if priced in USD
        cost_day_eur = cost_day * self.usd_to_eur if currency == "USD" else cost_day
        cost_month_eur = cost_day_eur * WORKING_DAYS_PER_MONTH
        cost_year_eur = cost_month_eur * MONTHS_PER_YEAR

        total_tokens = tokens_in + tokens_out
        cost_per_m = (cost_day_eur / total_tokens * 1_000_000) if total_tokens else 0

        return TCOResult(
            scenario_id=scenario_id,
            scenario_name=scenario["name"],
            provider=provider_id,
            model_id=model_id,
            model_display_name=model_cfg["display_name"],
            tokens_input_per_day=tokens_in,
            tokens_output_per_day=tokens_out,
            cost_day_eur=cost_day_eur,
            cost_month_eur=cost_month_eur,
            cost_year_eur=cost_year_eur,
            cost_per_million_tokens_eur=cost_per_m,
            pricing_status=provider_cfg.get("pricing_status", ""),
        )

    def _compute_selfhosted(
        self,
        scenario_id: str,
        scenario: dict,
        provider_id: str,
        provider_cfg: dict,
        model_id: str,
        tokens_in: int,
        tokens_out: int,
    ) -> TCOResult:
        model_cfg = provider_cfg["models"][model_id]
        hw_id = model_cfg["hardware"]
        hw_cfg = provider_cfg["hardware"][hw_id]

        price_gpu_hour = hw_cfg["price_per_hour_eur"]
        gpus = model_cfg["gpus_required"]

        # --- llmfit throughput estimation ---
        # Formula: single_tps = (bandwidth_gbps / model_size_gb) * efficiency
        # Source: github.com/AlexsJones/llmfit src/fit.rs
        bandwidth = hw_cfg["bandwidth_gbps"]
        model_gb = model_cfg["model_size_gb"]
        efficiency = model_cfg.get("llmfit_efficiency", 0.55)
        batch_efficiency = model_cfg.get("llmfit_batch_efficiency", 0.70)

        single_tps = (bandwidth / model_gb) * efficiency

        # Effective batch size = available VRAM / KV cache per stream
        # KV cache per stream at avg context (1024 tokens) for Llama3-70B GQA:
        #   2 (K+V) * context * d_head * n_kv_heads * n_layers * dtype_bytes
        n_layers = model_cfg.get("n_layers", 80)
        n_kv_heads = model_cfg.get("n_kv_heads", 8)
        d_head = model_cfg.get("d_head", 128)
        kv_dtype_bytes = model_cfg.get("kv_dtype_bytes", 2)
        avg_context = 1024  # conservative estimate

        kv_per_stream_bytes = 2 * avg_context * d_head * n_kv_heads * n_layers * kv_dtype_bytes
        kv_per_stream_gb = kv_per_stream_bytes / 1e9

        available_vram_gb = hw_cfg["vram_gb"] - model_gb
        max_concurrent = max(1, int(available_vram_gb / kv_per_stream_gb))

        # Aggregate throughput (output tokens/sec)
        aggregate_tps = single_tps * max_concurrent * batch_efficiency

        # GPU-hours needed to generate all output tokens
        gpu_hours_output = (tokens_out / aggregate_tps / 3600) * gpus

        # Prefill is ~10× faster than decode for bandwidth-bound inference
        gpu_hours_input = gpu_hours_output * 0.10

        gpu_hours_compute = gpu_hours_output + gpu_hours_input

        # Minimum daily uptime from scenarios.yaml (operational reality per use case)
        min_uptime_hours_per_day = scenario.get("ovh_min_hours_per_day", 1.0) * gpus
        billed_hours = max(gpu_hours_compute, min_uptime_hours_per_day)

        cost_day_eur = billed_hours * price_gpu_hour
        cost_month_eur = cost_day_eur * WORKING_DAYS_PER_MONTH
        cost_year_eur = cost_month_eur * MONTHS_PER_YEAR

        total_tokens = tokens_in + tokens_out
        cost_per_m = (cost_day_eur / total_tokens * 1_000_000) if total_tokens else 0

        notes = (
            f"llmfit: single_tps={single_tps:.1f}, "
            f"max_concurrent={max_concurrent}, "
            f"aggregate_tps={aggregate_tps:.0f} | "
            f"GPU-h/jour: {billed_hours:.1f} (compute {gpu_hours_compute:.1f})"
        )

        return TCOResult(
            scenario_id=scenario_id,
            scenario_name=scenario["name"],
            provider=provider_id,
            model_id=model_id,
            model_display_name=model_cfg["display_name"],
            tokens_input_per_day=tokens_in,
            tokens_output_per_day=tokens_out,
            cost_day_eur=cost_day_eur,
            cost_month_eur=cost_month_eur,
            cost_year_eur=cost_year_eur,
            gpus_required=gpus,
            cost_per_million_tokens_eur=cost_per_m,
            pricing_status=provider_cfg.get("pricing_status", ""),
            notes=notes,
        )

    def _monthly_gpu_cost_eur(self, scenario_id: str) -> float:
        scenario = self.scenarios["scenarios"][scenario_id]
        model_id = scenario["model_selection"]["ovh_selfhosted"]
        provider_cfg = self.pricing["providers"]["ovh_selfhosted"]
        model_cfg = provider_cfg["models"][model_id]
        hw_cfg = provider_cfg["hardware"][model_cfg["hardware"]]
        gpus = model_cfg["gpus_required"]
        return hw_cfg["price_per_hour_eur"] * gpus * 24 * WORKING_DAYS_PER_MONTH

    @staticmethod
    def _load_yaml(path: Path) -> dict:
        with open(path) as f:
            return yaml.safe_load(f)
