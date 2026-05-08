"""
TCO calculator for sovereign LLM deployments.

Computes daily / monthly / annual cost for each (scenario, provider, model)
combination using static pricing from config/pricing.yaml.

No API calls are made here — this module is fully offline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
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
    # Only set for OVH self-hosted
    gpus_required: int = 1
    cost_per_million_tokens_eur: float = 0.0
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
            "notes": self.notes,
        }


@dataclass
class BreakevenResult:
    scenario_id: str
    scenario_name: str
    selfhosted_provider: str = "ovh_selfhosted"
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
        """Return one TCOResult per (scenario, provider) combination."""
        results: list[TCOResult] = []
        for scenario_id, scenario in self.scenarios["scenarios"].items():
            for provider_id in self.pricing["providers"]:
                result = self._compute_one(scenario_id, scenario, provider_id)
                results.append(result)
        return results

    def compute_breakeven(self, results: list[TCOResult]) -> list[BreakevenResult]:
        """
        For each scenario, compare OVH self-hosted against each API provider.
        Returns a BreakevenResult showing at what monthly volume self-hosted wins.
        """
        breakevens: list[BreakevenResult] = []

        # Group results by (scenario_id, provider)
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
                    be.cheaper_at_scale = "self-hosted"
                    be.notes = f"Self-hosted saves €{diff:,.0f}/month vs {provider_id}"
                else:
                    diff = selfhosted.cost_month_eur - api_result.cost_month_eur
                    be.cheaper_at_scale = provider_id
                    be.notes = f"API cheaper by €{diff:,.0f}/month at this scale"

                # Breakeven in months = upfront GPU capex / monthly API saving
                # We approximate upfront capex as 12 months of GPU rental at current rate.
                # This is a conservative proxy; real capex would be purchase + amortisation.
                monthly_gpu_cost = self._monthly_gpu_cost_eur(scenario_id)
                if api_result.cost_month_eur > selfhosted.cost_month_eur:
                    monthly_saving = api_result.cost_month_eur - selfhosted.cost_month_eur
                    capex_proxy = monthly_gpu_cost * 12
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
        price_in_usd = model_cfg["input_per_1m_tokens"] / 1_000_000
        price_out_usd = model_cfg["output_per_1m_tokens"] / 1_000_000

        cost_day_usd = tokens_in * price_in_usd + tokens_out * price_out_usd
        cost_day_eur = cost_day_usd * self.usd_to_eur
        cost_month_eur = cost_day_eur * WORKING_DAYS_PER_MONTH
        cost_year_eur = cost_month_eur * MONTHS_PER_YEAR

        total_tokens_day = tokens_in + tokens_out
        cost_per_m = (cost_day_eur / total_tokens_day * 1_000_000) if total_tokens_day else 0

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

        price_gpu_hour_eur = hw_cfg["price_per_hour_eur"]
        gpus_per_instance = model_cfg["gpus_required"]
        effective_tps = model_cfg["effective_tokens_per_second"]

        # Tokens to generate per day (only output tokens consume compute)
        tokens_to_generate = tokens_out
        # Seconds of compute required to generate all output tokens
        compute_seconds_needed = tokens_to_generate / effective_tps
        # GPU-hours required for output generation
        gpu_hours_for_output = (compute_seconds_needed / 3600) * gpus_per_instance

        # Prefill (input tokens) is ~10× faster than decode; rough factor 0.1
        prefill_factor = 0.10
        gpu_hours_for_input = (tokens_in / effective_tps / 3600) * gpus_per_instance * prefill_factor

        gpu_hours_total = gpu_hours_for_output + gpu_hours_for_input

        # We also pay for at-minimum the wall-clock hours the server runs.
        # For S4 (real-time), the server must run 8h/day minimum to cover agent shifts.
        # Conservatively: bill max(compute_hours, minimum_uptime_hours).
        if scenario_id == "S4":
            minimum_uptime_hours = 8.0 * gpus_per_instance
        else:
            minimum_uptime_hours = max(1.0, gpu_hours_total * 0.5) * gpus_per_instance

        billed_gpu_hours = max(gpu_hours_total, minimum_uptime_hours)

        cost_day_eur = billed_gpu_hours * price_gpu_hour_eur
        cost_month_eur = cost_day_eur * WORKING_DAYS_PER_MONTH
        cost_year_eur = cost_month_eur * MONTHS_PER_YEAR

        total_tokens_day = tokens_in + tokens_out
        cost_per_m = (cost_day_eur / total_tokens_day * 1_000_000) if total_tokens_day else 0

        notes = (
            f"GPU-hours/day: {billed_gpu_hours:.1f} "
            f"(compute: {gpu_hours_total:.1f}, min uptime: {minimum_uptime_hours:.1f})"
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
            gpus_required=gpus_per_instance,
            cost_per_million_tokens_eur=cost_per_m,
            notes=notes,
        )

    def _monthly_gpu_cost_eur(self, scenario_id: str) -> float:
        """Return monthly GPU rental cost for a given scenario's self-hosted config."""
        scenario = self.scenarios["scenarios"][scenario_id]
        model_id = scenario["model_selection"]["ovh_selfhosted"]
        provider_cfg = self.pricing["providers"]["ovh_selfhosted"]
        model_cfg = provider_cfg["models"][model_id]
        hw_cfg = provider_cfg["hardware"][model_cfg["hardware"]]
        gpus = model_cfg["gpus_required"]
        # 24h/day × 22 days for a continuously running server
        return hw_cfg["price_per_hour_eur"] * gpus * 24 * WORKING_DAYS_PER_MONTH

    @staticmethod
    def _load_yaml(path: Path) -> dict:
        with open(path) as f:
            return yaml.safe_load(f)
