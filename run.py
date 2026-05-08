#!/usr/bin/env python3
"""
sovereign-llm-bench — point d'entrée unique.

Sous-commandes :
  (aucune)                     TCO complet : terminal + CSV + rapport HTML
  compare [--scenario S1]      Matrice de comparaison côte à côte
  calc --input N --output N    Coût pour un volume custom (N = entier ou ex. 10M)
  prices                       Tableau des tarifs unitaires configurés

Options globales :
  --json                       Sortie JSON (compatible pipe / jq)
  --quiet                      Supprime l'affichage terminal, écrit CSV+HTML seulement

Exemples :
  python run.py
  python run.py compare --scenario S2
  python run.py calc --input 27M --output 3M
  python run.py calc --input 27M --output 3M --provider scaleway
  python run.py prices
  python run.py compare --json | jq '.[] | select(.scenario=="S2")'
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from benchmark.cli import print_calc, print_compare, print_prices
from benchmark.report import build as build_report
from benchmark.runner import run as run_tco
from benchmark.tco_calculator import TCOCalculator


# ── token parser ──────────────────────────────────────────────────────────

def _parse_tokens(s: str) -> int:
    """Parse '10M', '500K', '1B', or raw int."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMBkmb]?)", s.strip())
    if not m:
        raise argparse.ArgumentTypeError(f"Volume invalide : '{s}'  (exemples: 10M, 500K, 1B, 1000000)")
    n, suffix = float(m.group(1)), m.group(2).upper()
    mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "": 1}[suffix]
    return int(n * mult)


# ── main ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="sovereign-llm-bench — TCO cloud souverain FR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--json",  action="store_true", help="Sortie JSON")
    parser.add_argument("--quiet", action="store_true", help="Pas d'affichage terminal")

    sub = parser.add_subparsers(dest="cmd")

    # compare
    p_cmp = sub.add_parser("compare", help="Matrice de comparaison côte à côte")
    p_cmp.add_argument("--scenario", metavar="ID", help="Filtrer sur un scénario (S1…S4)")
    p_cmp.add_argument("--json", action="store_true", help="Sortie JSON")

    # calc
    p_calc = sub.add_parser("calc", help="Coût pour un volume custom")
    p_calc.add_argument("--input",    required=True, type=_parse_tokens, metavar="N",
                        help="Tokens input (ex: 27M)")
    p_calc.add_argument("--output",   required=True, type=_parse_tokens, metavar="N",
                        help="Tokens output (ex: 3M)")
    p_calc.add_argument("--provider", metavar="ID",
                        help="Filtrer sur un provider (s3ns, bleu, scaleway, ovh_selfhosted)")
    p_calc.add_argument("--json", action="store_true", help="Sortie JSON")

    # prices
    p_prices = sub.add_parser("prices", help="Tarifs unitaires configurés")
    p_prices.add_argument("--json", action="store_true", help="Sortie JSON")

    args = parser.parse_args()
    _load_dotenv()

    # ── sous-commandes ────────────────────────────────────────────────────

    if args.cmd == "compare":
        calc    = TCOCalculator()
        results = calc.compute_all()
        if args.json:
            _json_out([r.as_dict() for r in results
                       if args.scenario is None or r.scenario_id == args.scenario])
        else:
            print_compare(results, scenario_filter=args.scenario)
        return

    if args.cmd == "calc":
        if args.json:
            _json_calc(args.input, args.output, args.provider)
        else:
            print_calc(args.input, args.output, args.provider)
        return

    if args.cmd == "prices":
        if args.json:
            _json_prices()
        else:
            print_prices()
        return

    # ── commande par défaut : rapport complet ─────────────────────────────

    results, breakevens = run_tco(verbose=not args.quiet and not args.json)

    report_path = build_report(results, breakevens)
    if not args.quiet and not args.json:
        print(f"  {report_path}")

    if args.json:
        _json_out({
            "tco":       [r.as_dict() for r in results],
            "breakeven": [
                {
                    "scenario_id":              be.scenario_id,
                    "reference_provider":        be.reference_provider,
                    "api_provider":             be.api_provider,
                    "selfhosted_cost_month_eur": round(be.selfhosted_cost_month_eur, 2),
                    "api_cost_month_eur":        round(be.api_cost_month_eur, 2),
                    "breakeven_months":          be.breakeven_months if be.breakeven_months != float("inf") else None,
                    "cheaper_at_scale":          be.cheaper_at_scale,
                }
                for be in breakevens
            ],
        })


# ── JSON helpers ──────────────────────────────────────────────────────────

def _json_out(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _json_calc(tokens_in: int, tokens_out: int, provider_filter: str | None) -> None:
    calc = TCOCalculator()
    out = []
    for pid, pcfg in calc.pricing["providers"].items():
        if provider_filter and pid != provider_filter:
            continue
        for mid, mcfg in pcfg["models"].items():
            if pid == "ovh_selfhosted":
                hw   = pcfg["hardware"][mcfg["hardware"]]
                bw   = hw["bandwidth_gbps"]
                msz  = mcfg["model_size_gb"]
                eff  = mcfg.get("llmfit_efficiency", 0.55)
                beff = mcfg.get("llmfit_batch_efficiency", 0.70)
                n_layers   = mcfg.get("n_layers", 80)
                n_kv_heads = mcfg.get("n_kv_heads", 8)
                d_head     = mcfg.get("d_head", 128)
                kv_bytes   = mcfg.get("kv_dtype_bytes", 2)
                kv_per     = 2 * 1024 * d_head * n_kv_heads * n_layers * kv_bytes / 1e9
                avail_vram = hw["vram_gb"] - msz
                max_conc   = max(1, int(avail_vram / kv_per))
                agg_tps    = (bw / msz) * eff * max_conc * beff
                gpu_h      = max((tokens_out / agg_tps / 3600) * mcfg["gpus_required"], 1.0)
                cost_eur   = gpu_h * hw["price_per_hour_eur"]
            else:
                cur      = mcfg.get("currency", "USD")
                p_in     = mcfg["input_per_1m_tokens"]  / 1_000_000
                p_out    = mcfg["output_per_1m_tokens"] / 1_000_000
                cost     = tokens_in * p_in + tokens_out * p_out
                cost_eur = cost * calc.usd_to_eur if cur == "USD" else cost

            out.append({
                "provider":    pid,
                "model":       mcfg["display_name"],
                "tokens_input":  tokens_in,
                "tokens_output": tokens_out,
                "cost_eur":    round(cost_eur, 4),
            })
    _json_out(out)


def _json_prices() -> None:
    calc = TCOCalculator()
    out = []
    for pid, pcfg in calc.pricing["providers"].items():
        for mid, mcfg in pcfg["models"].items():
            if pid == "ovh_selfhosted":
                hw = pcfg["hardware"][mcfg["hardware"]]
                out.append({
                    "provider": pid,
                    "model_id": mid,
                    "model":    mcfg["display_name"],
                    "billing":  "gpu-per-hour",
                    "price_eur": hw["price_per_hour_eur"],
                    "status":   pcfg.get("pricing_status", ""),
                })
            else:
                cur  = mcfg.get("currency", "USD")
                rate = calc.usd_to_eur if cur == "USD" else 1.0
                out.append({
                    "provider":             pid,
                    "model_id":             mid,
                    "model":                mcfg["display_name"],
                    "billing":              "pay-per-token",
                    "input_per_1m_eur":     round(mcfg["input_per_1m_tokens"]  * rate, 4),
                    "output_per_1m_eur":    round(mcfg["output_per_1m_tokens"] * rate, 4),
                    "original_currency":    cur,
                    "status":               pcfg.get("pricing_status", ""),
                })
    _json_out(out)


# ── .env loader ───────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        import os
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


if __name__ == "__main__":
    main()
