"""
Terminal output — tables ASCII sans dépendance externe.
Appelé par run.py pour les sous-commandes compare, calc, prices.
"""

from __future__ import annotations

from benchmark.tco_calculator import BreakevenResult, TCOCalculator, TCOResult

PROVIDER_ORDER  = ["s3ns", "bleu", "scaleway", "ovh_selfhosted"]
PROVIDER_LABELS = {
    "s3ns":           "S3NS (Thales×GCP) [proxy]",
    "bleu":           "Bleu (MS×Orange)  [proxy]",
    "scaleway":       "Scaleway FR       [officiel]",
    "ovh_selfhosted": "OVH Self-hosted   [GPU €/h]",
}
COL_W = 18


# ── helpers ────────────────────────────────────────────────────────────────

def _e(v: float) -> str:
    return f"€{v:,.0f}".rjust(COL_W)

def _sep(n_cols: int, char: str = "─") -> str:
    return char * (28 + COL_W * n_cols)


# ── compare ────────────────────────────────────────────────────────────────

def print_compare(results: list[TCOResult], scenario_filter: str | None = None) -> None:
    """Heat-map style matrix : scénarios × providers, €/mois."""

    by_s: dict[str, dict[str, TCOResult]] = {}
    for r in results:
        by_s.setdefault(r.scenario_id, {})[r.provider] = r

    sids = sorted(s for s in by_s if scenario_filter is None or s == scenario_filter)
    if not sids:
        print(f"Scénario '{scenario_filter}' introuvable.")
        return

    # Header
    header = f"  {'Scénario':<26}" + "".join(
        PROVIDER_LABELS[p][:COL_W].rjust(COL_W) for p in PROVIDER_ORDER
    )
    sep = _sep(len(PROVIDER_ORDER))
    print("\n" + "═" * len(sep))
    print("  COMPARATIF TCO — CLOUD SOUVERAIN FRANÇAIS  (€/mois, 22 j. ouvrés)")
    print("  API : tarif pay-per-token  |  OVH : GPU cloud, calcul via llmfit")
    print("═" * len(sep))
    print(header)
    print(sep)

    for sid in sids:
        row = by_s[sid]
        costs   = {p: row[p].cost_month_eur for p in PROVIDER_ORDER if p in row}
        min_api = min(v for p, v in costs.items() if p != "ovh_selfhosted") if costs else 0
        min_all = min(costs.values()) if costs else 0

        label = f"{sid} — {row[next(iter(row))].scenario_name}"
        cost_cells = []
        for p in PROVIDER_ORDER:
            if p not in row:
                cost_cells.append(f"{'N/A':>{COL_W}}")
                continue
            v = costs[p]
            marker = " ◀" if v == min_all else ""   # cheapest overall
            cost_cells.append(f"{'€{:,.0f}{}'.format(v, marker):>{COL_W}}")

        print(f"  {label:<26}" + "".join(cost_cells))

        # €/M tokens sub-row
        cpm_cells = []
        for p in PROVIDER_ORDER:
            if p not in row:
                cpm_cells.append(f"{'':>{COL_W}}")
                continue
            v = row[p].cost_per_million_tokens_eur
            cpm_cells.append(f"{'(€{:.3f}/M tok)'.format(v):>{COL_W}}")
        print(f"  {'':26}" + "".join(cpm_cells))

        # model sub-row
        model_cells = []
        for p in PROVIDER_ORDER:
            name = row[p].model_display_name[:COL_W - 2] if p in row else ""
            model_cells.append(f"{'({})'.format(name):>{COL_W}}")
        print(f"  {'':26}" + "".join(model_cells))
        print(sep)

    print()
    print("  ◀ = moins cher sur ce scénario   [proxy] = tarif estimé via plateforme sous-jacente")
    print(f"  Taux USD/EUR : {TCOCalculator().usd_to_eur}")
    print()


# ── calc ───────────────────────────────────────────────────────────────────

def print_calc(
    tokens_input: int,
    tokens_output: int,
    provider_filter: str | None = None,
) -> None:
    """Calcule le coût pour un volume custom sur tous les providers (ou un seul)."""
    calc = TCOCalculator()
    usd_eur = calc.usd_to_eur

    print(f"\n  CALCULATEUR — {tokens_input:,} tokens input  +  {tokens_output:,} tokens output")
    print("  " + "─" * 74)
    print(f"  {'Provider':<34} {'Modèle':<28} {'Coût (€)'}")
    print("  " + "─" * 74)

    for pid, pcfg in calc.pricing["providers"].items():
        if provider_filter and pid != provider_filter:
            continue
        for mid, mcfg in pcfg["models"].items():
            currency = mcfg.get("currency", "USD")
            if pid == "ovh_selfhosted":
                # coût GPU approximatif sur la base du débit llmfit
                hw  = pcfg["hardware"][mcfg["hardware"]]
                bw  = hw["bandwidth_gbps"]
                msz = mcfg["model_size_gb"]
                eff = mcfg.get("llmfit_efficiency", 0.55)
                beff= mcfg.get("llmfit_batch_efficiency", 0.70)
                n_layers = mcfg.get("n_layers", 80)
                n_kv_heads = mcfg.get("n_kv_heads", 8)
                d_head = mcfg.get("d_head", 128)
                kv_bytes = mcfg.get("kv_dtype_bytes", 2)
                kv_per = 2 * 1024 * d_head * n_kv_heads * n_layers * kv_bytes / 1e9
                avail_vram = hw["vram_gb"] - msz
                max_conc = max(1, int(avail_vram / kv_per))
                agg_tps = (bw / msz) * eff * max_conc * beff
                gpu_h = (tokens_output / agg_tps / 3600) * mcfg["gpus_required"]
                gpu_h = max(gpu_h, 1.0)
                cost_eur = gpu_h * hw["price_per_hour_eur"]
                note = f"({gpu_h:.1f} GPU-h × €{hw['price_per_hour_eur']}/h)"
            else:
                p_in  = mcfg["input_per_1m_tokens"]  / 1_000_000
                p_out = mcfg["output_per_1m_tokens"] / 1_000_000
                cost  = tokens_input * p_in + tokens_output * p_out
                cost_eur = cost * usd_eur if currency == "USD" else cost
                note = ""
            label = f"{PROVIDER_LABELS[pid]}"
            print(f"  {label:<34} {mcfg['display_name']:<28} €{cost_eur:>10,.2f}  {note}")

    print()


# ── prices ─────────────────────────────────────────────────────────────────

def print_prices() -> None:
    """Affiche le tarif unitaire de tous les modèles configurés."""
    calc = TCOCalculator()
    usd_eur = calc.usd_to_eur

    print("\n  TARIFS UNITAIRES — config/pricing.yaml")
    print("  " + "─" * 80)
    print(f"  {'Provider':<26} {'Modèle':<30} {'Input/1M':>10} {'Output/1M':>10}  Statut")
    print("  " + "─" * 80)

    for pid, pcfg in calc.pricing["providers"].items():
        status = pcfg.get("pricing_status", "")
        flag = "⚠ PROXY" if "PROXY" in status else ("✓ OFFICIEL" if "OFFICIEL" in status else "GPU €/h")

        if pid == "ovh_selfhosted":
            for mid, mcfg in pcfg["models"].items():
                hw = pcfg["hardware"][mcfg["hardware"]]
                print(
                    f"  {PROVIDER_LABELS[pid]:<26} {mcfg['display_name']:<30}"
                    f" {'GPU':>10} {hw['price_per_hour_eur']:>9.2f}€/h  {flag}"
                )
        else:
            for mid, mcfg in pcfg["models"].items():
                cur = mcfg.get("currency", "USD")
                p_in  = mcfg["input_per_1m_tokens"]
                p_out = mcfg["output_per_1m_tokens"]
                p_in_eur  = p_in  * usd_eur if cur == "USD" else p_in
                p_out_eur = p_out * usd_eur if cur == "USD" else p_out
                suffix = " (USD)" if cur == "USD" else " (EUR)"
                print(
                    f"  {PROVIDER_LABELS[pid]:<26} {mcfg['display_name']:<30}"
                    f" €{p_in_eur:>8.4f} €{p_out_eur:>8.4f}  {flag}"
                )
    print(f"\n  Taux USD/EUR : {usd_eur}   Source date : {calc.pricing['metadata']['retrieved_date']}")
    print()
