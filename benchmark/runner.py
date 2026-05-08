"""
Benchmark runner: computes TCO for all scenarios, writes CSV, prints terminal table.
"""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

from benchmark.tco_calculator import BreakevenResult, TCOCalculator, TCOResult

RESULTS_DIR = Path(__file__).parent.parent / "results"

PROVIDER_ORDER = ["s3ns", "bleu", "scaleway", "ovh_selfhosted", "onprem_openshift"]
PROVIDER_LABELS = {
    "s3ns": "S3NS (Thales×GCP)",
    "bleu": "Bleu (MS×Orange)",
    "scaleway": "Scaleway FR",
    "ovh_selfhosted": "OVH Self-hosted",
    "onprem_openshift": "On-prem OpenShift",
}


def run(verbose: bool = True) -> tuple[list[TCOResult], list[BreakevenResult]]:
    calc = TCOCalculator()
    results = calc.compute_all()
    breakevens = calc.compute_breakeven(results)

    _write_csv(results, breakevens)

    if verbose:
        _print_table(results)
        _print_breakeven(breakevens)

    return results, breakevens


# ------------------------------------------------------------------
# CSV output
# ------------------------------------------------------------------

def _write_csv(results: list[TCOResult], breakevens: list[BreakevenResult]) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    today = date.today().isoformat()

    tco_path = RESULTS_DIR / f"tco_{today}.csv"
    fieldnames = [
        "scenario_id", "scenario_name", "provider", "model",
        "tokens_input_day", "tokens_output_day",
        "cost_day_eur", "cost_month_eur", "cost_year_eur",
        "cost_per_m_tokens_eur", "gpus_required", "pricing_status", "notes",
    ]
    with open(tco_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r.as_dict())

    be_path = RESULTS_DIR / f"breakeven_{today}.csv"
    be_fields = [
        "scenario_id", "scenario_name", "reference_provider", "api_provider", "api_model",
        "selfhosted_cost_month_eur", "api_cost_month_eur",
        "breakeven_months", "cheaper_at_scale", "notes",
    ]
    with open(be_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=be_fields)
        writer.writeheader()
        for be in breakevens:
            writer.writerow({
                "scenario_id": be.scenario_id,
                "scenario_name": be.scenario_name,
                "reference_provider": be.reference_provider,
                "api_provider": be.api_provider,
                "api_model": be.api_model,
                "selfhosted_cost_month_eur": round(be.selfhosted_cost_month_eur, 2),
                "api_cost_month_eur": round(be.api_cost_month_eur, 2),
                "breakeven_months": round(be.breakeven_months, 1) if be.breakeven_months != float("inf") else "never",
                "cheaper_at_scale": be.cheaper_at_scale,
                "notes": be.notes,
            })

    print(f"\nResults written to:\n  {tco_path}\n  {be_path}", file=sys.stderr)


# ------------------------------------------------------------------
# Terminal table
# ------------------------------------------------------------------

def _eur_fmt(x: float, w: int = 18) -> str:
    return f"€{x:,.0f}".rjust(w)


def _print_table(results: list[TCOResult]) -> None:
    # Group by scenario
    by_scenario: dict[str, dict[str, TCOResult]] = {}
    for r in results:
        by_scenario.setdefault(r.scenario_id, {})[r.provider] = r

    col_w = 18
    h_provider = [f"{PROVIDER_LABELS.get(p, p):<{col_w}}" for p in PROVIDER_ORDER]
    separator = "─" * (22 + col_w * len(PROVIDER_ORDER))

    print("\n" + "═" * len(separator))
    print("  SOVEREIGN LLM BENCH — TCO COMPARATIF (€/mois, API=22j ouvrés, on-prem=mensuel fixe)")
    print("═" * len(separator))
    print(f"  {'Scénario':<20}" + "".join(h_provider))
    print(separator)

    for scenario_id in sorted(by_scenario.keys()):
        providers = by_scenario[scenario_id]
        first = next(iter(providers.values()))
        label = f"{scenario_id} — {first.scenario_name}"

        costs = []
        for p in PROVIDER_ORDER:
            r = providers.get(p)
            costs.append(_eur_fmt(r.cost_month_eur) if r else f"{'N/A':>{col_w}}")

        print(f"  {label:<20}" + "".join(costs))

        # Model row
        models = []
        for p in PROVIDER_ORDER:
            r = providers.get(p)
            name = (r.model_display_name[:col_w - 1] if r else "")
            models.append(f"  {'(' + name + ')':<{col_w - 2}}")
        print(f"  {'':20}" + "".join(models))

        print(separator)

    print()
    print("  Coût mensuel = coût/jour × 22 jours ouvrés")
    print(f"  Taux USD/EUR appliqué : {TCOCalculator().usd_to_eur}")
    print()


def _print_breakeven(breakevens: list[BreakevenResult]) -> None:
    print("═" * 90)
    print("  SEUILS DE RENTABILITÉ — infra gérée vs cloud souverain API")
    print("═" * 90)
    print(f"  {'Scénario':<8} {'Référence':<20} {'vs provider':<20} {'Géré/mois':>14} {'API/mois':>12} {'Breakeven':>12}  Verdict")
    print("─" * 90)

    for be in breakevens:
        be_str = f"{be.breakeven_months:.0f} mois" if be.breakeven_months not in (float("inf"), 0) else ("jamais" if be.breakeven_months == float("inf") else "immédiat")
        ref_label = PROVIDER_LABELS.get(be.reference_provider, be.reference_provider)
        verdict = f"✓ {ref_label}" if be.cheaper_at_scale == be.reference_provider else f"✓ {be.api_provider}"
        print(
            f"  {be.scenario_id:<8} "
            f"{ref_label:<20} "
            f"{PROVIDER_LABELS.get(be.api_provider, be.api_provider):<20} "
            f"€{be.selfhosted_cost_month_eur:>10,.0f}   "
            f"€{be.api_cost_month_eur:>8,.0f}   "
            f"{be_str:>10}  {verdict}"
        )

    print()
