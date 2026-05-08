"""
Rapport HTML statique auto-contenu.
Visualisation : heat-map matrix + provider cards + breakeven interactif.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from benchmark.tco_calculator import BreakevenResult, TCOCalculator, TCOResult

RESULTS_DIR = Path(__file__).parent.parent / "results"

PROVIDER_ORDER = ["s3ns", "bleu", "scaleway", "ovh_selfhosted"]
PROVIDER_META = {
    "s3ns": {
        "label":  "S3NS",
        "sub":    "Thales × Google Cloud",
        "color":  "#4285F4",
        "light":  "#EAF1FF",
        "badge":  "proxy",
        "cert":   "SecNumCloud 3.2",
        "type":   "API souverain",
    },
    "bleu": {
        "label":  "Bleu",
        "sub":    "Microsoft × Orange",
        "color":  "#00A4EF",
        "light":  "#E5F6FF",
        "badge":  "proxy",
        "cert":   "SecNumCloud (en cours)",
        "type":   "API souverain",
    },
    "scaleway": {
        "label":  "Scaleway",
        "sub":    "Generative APIs",
        "color":  "#7B2D8B",
        "light":  "#F5EEF8",
        "badge":  "officiel",
        "cert":   "HDS · ISO 27001",
        "type":   "API souverain",
    },
    "ovh_selfhosted": {
        "label":  "OVH",
        "sub":    "Self-hosted GPU",
        "color":  "#123F6D",
        "light":  "#E8EEF4",
        "badge":  "infra",
        "cert":   "HDS · SecNumCloud",
        "type":   "Infrastructure",
    },
}


def build(results: list[TCOResult], breakevens: list[BreakevenResult]) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    today = date.today().isoformat()
    out_path = RESULTS_DIR / f"report_{today}.html"

    by_scenario: dict[str, dict[str, TCOResult]] = {}
    for r in results:
        by_scenario.setdefault(r.scenario_id, {})[r.provider] = r

    scenario_ids = sorted(by_scenario.keys())

    be_by_scenario: dict[str, dict[str, BreakevenResult]] = {}
    for be in breakevens:
        be_by_scenario.setdefault(be.scenario_id, {})[be.api_provider] = be

    calc = TCOCalculator()
    usd_eur = calc.usd_to_eur
    retrieved = calc.pricing["metadata"]["retrieved_date"]

    html = _render(
        today=today,
        retrieved=retrieved,
        usd_eur=usd_eur,
        scenario_ids=scenario_ids,
        by_scenario=by_scenario,
        be_by_scenario=be_by_scenario,
    )
    out_path.write_text(html, encoding="utf-8")
    return out_path


# ── HTML builder ─────────────────────────────────────────────────────────

def _render(today, retrieved, usd_eur, scenario_ids, by_scenario, be_by_scenario) -> str:

    # ── Provider cards ──────────────────────────────────────────────────
    cards_html = ""
    for pid in PROVIDER_ORDER:
        m = PROVIDER_META[pid]
        badge_cls = {"proxy": "badge-warn", "officiel": "badge-ok", "infra": "badge-info"}[m["badge"]]
        badge_lbl = {"proxy": "⚠ Proxy", "officiel": "✓ Officiel", "infra": "GPU €/h"}[m["badge"]]

        # best €/M tokens across scenarios for this provider
        cpm_vals = [
            by_scenario[s][pid].cost_per_million_tokens_eur
            for s in scenario_ids if pid in by_scenario.get(s, {})
        ]
        cpm_range = (
            f"€{min(cpm_vals):.3f} – €{max(cpm_vals):.3f} /M tok"
            if cpm_vals else "N/A"
        )
        cards_html += f"""
        <div class="card provider-card" style="border-top:4px solid {m['color']}">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div>
              <div class="provider-name" style="color:{m['color']}">{m['label']}</div>
              <div class="provider-sub">{m['sub']}</div>
            </div>
            <span class="badge {badge_cls}">{badge_lbl}</span>
          </div>
          <div class="provider-type">{m['type']}</div>
          <div class="provider-cert">{m['cert']}</div>
          <div class="provider-cpm">{cpm_range}</div>
        </div>"""

    # ── Heat-map matrix ─────────────────────────────────────────────────
    # Per column (provider), compute min/max for % colouring
    col_min: dict[str, float] = {}
    col_max: dict[str, float] = {}
    for pid in PROVIDER_ORDER:
        vals = [by_scenario[s][pid].cost_month_eur for s in scenario_ids if pid in by_scenario.get(s, {})]
        col_min[pid] = min(vals) if vals else 0
        col_max[pid] = max(vals) if vals else 1

    # Per row (scenario), find cheapest provider
    row_winner: dict[str, str] = {}
    for sid in scenario_ids:
        row = by_scenario[sid]
        row_winner[sid] = min(row, key=lambda p: row[p].cost_month_eur) if row else ""

    header_cells = "".join(
        f'<th style="color:{PROVIDER_META[p]["color"]}">'
        f'{PROVIDER_META[p]["label"]}<br>'
        f'<small>{PROVIDER_META[p]["sub"]}</small></th>'
        for p in PROVIDER_ORDER
    )

    matrix_rows = ""
    for sid in scenario_ids:
        row = by_scenario[sid]
        scenario_name = row[next(iter(row))].scenario_name if row else sid
        cells = ""
        for pid in PROVIDER_ORDER:
            if pid not in row:
                cells += "<td>—</td>"
                continue
            r = row[pid]
            v = r.cost_month_eur
            # colour intensity relative to column range
            pct = (v - col_min[pid]) / max(col_max[pid] - col_min[pid], 1)
            bg  = _heat_color(pct, PROVIDER_META[pid]["color"], PROVIDER_META[pid]["light"])
            winner = pid == row_winner[sid]
            cls = " winner" if winner else ""
            model_short = r.model_display_name[:22]
            cells += (
                f'<td class="cell{cls}" style="background:{bg}" '
                f'data-pid="{pid}" data-sid="{sid}">'
                f'<span class="cell-cost">€{v:,.0f}</span>'
                f'<span class="cell-cpm">€{r.cost_per_million_tokens_eur:.3f}/M tok</span>'
                f'<span class="cell-model">{model_short}</span>'
                f'</td>'
            )

        winner_label = PROVIDER_META.get(row_winner[sid], {}).get("label", "")
        matrix_rows += f"""
        <tr>
          <td class="scenario-cell">
            <strong>{sid}</strong><br>
            <span class="scenario-name">{scenario_name}</span>
          </td>
          {cells}
          <td class="winner-cell">
            <span class="chip-winner" style="background:{PROVIDER_META[row_winner[sid]]['light']};color:{PROVIDER_META[row_winner[sid]]['color']}">
              {winner_label}
            </span>
          </td>
        </tr>"""

    # ── Breakeven table ─────────────────────────────────────────────────
    be_rows = ""
    for sid in scenario_ids:
        bes = be_by_scenario.get(sid, {})
        for pid in PROVIDER_ORDER:
            if pid == "ovh_selfhosted":
                continue
            be = bes.get(pid)
            if be is None:
                continue
            m = PROVIDER_META[pid]
            ovh_m = PROVIDER_META["ovh_selfhosted"]
            if be.breakeven_months == float("inf"):
                be_str = '<span class="muted">jamais</span>'
                winner_html = f'<span class="chip" style="background:{m["light"]};color:{m["color"]}">{m["label"]}</span>'
            else:
                be_str = f"{be.breakeven_months:.0f} mois"
                winner_html = f'<span class="chip" style="background:{ovh_m["light"]};color:{ovh_m["color"]}">OVH self-hosted</span>'
            diff = abs(be.api_cost_month_eur - be.selfhosted_cost_month_eur)
            be_rows += f"""
            <tr>
              <td><strong>{sid}</strong></td>
              <td><span style="color:{m['color']};font-weight:600">{m['label']}</span></td>
              <td class="num">€{be.selfhosted_cost_month_eur:,.0f}</td>
              <td class="num">€{be.api_cost_month_eur:,.0f}</td>
              <td class="num">€{diff:,.0f}/mois</td>
              <td class="num">{be_str}</td>
              <td>{winner_html}</td>
            </tr>"""

    # ── Full data table ──────────────────────────────────────────────────
    rows_html = ""
    for sid in scenario_ids:
        for pid in PROVIDER_ORDER:
            r = by_scenario[sid].get(pid)
            if r is None:
                continue
            m = PROVIDER_META[pid]
            badge = (
                f'<span class="badge badge-warn">Proxy</span>'
                if "PROXY" in r.pricing_status else
                f'<span class="badge badge-ok">Officiel</span>'
                if "OFFICIEL" in r.pricing_status else
                f'<span class="badge badge-info">GPU</span>'
            )
            rows_html += f"""
            <tr>
              <td><strong>{r.scenario_id}</strong> — {r.scenario_name}</td>
              <td style="color:{m['color']};font-weight:600">{m['label']} {badge}</td>
              <td>{r.model_display_name}</td>
              <td class="num">{r.tokens_input_per_day + r.tokens_output_per_day:,}</td>
              <td class="num">€{r.cost_day_eur:,.2f}</td>
              <td class="num bold">€{r.cost_month_eur:,.0f}</td>
              <td class="num">€{r.cost_year_eur:,.0f}</td>
              <td class="num">€{r.cost_per_million_tokens_eur:.4f}</td>
            </tr>"""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Sovereign LLM Bench — {today}</title>
  <style>
    :root{{--bg:#F7F8FA;--card:#fff;--border:#E2E6EA;--text:#111827;--muted:#6B7280;
          --radius:10px;--shadow:0 1px 4px rgba(0,0,0,.08)}}
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
          background:var(--bg);color:var(--text);font-size:14px;line-height:1.5}}
    a{{color:inherit}}

    /* layout */
    header{{background:#111827;color:#fff;padding:28px 40px}}
    header h1{{font-size:20px;font-weight:700;margin-bottom:4px}}
    header p{{opacity:.65;font-size:12px}}
    .container{{max-width:1280px;margin:0 auto;padding:28px 24px}}
    section{{margin-bottom:36px}}
    section > h2{{font-size:16px;font-weight:700;margin-bottom:14px;
                  display:flex;align-items:center;gap:8px}}
    .card{{background:var(--card);border:1px solid var(--border);
           border-radius:var(--radius);box-shadow:var(--shadow)}}

    /* provider cards */
    .provider-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:28px}}
    @media(max-width:900px){{.provider-grid{{grid-template-columns:repeat(2,1fr)}}}}
    .provider-card{{padding:18px;border-radius:var(--radius);border:1px solid var(--border);
                    box-shadow:var(--shadow)}}
    .provider-name{{font-size:20px;font-weight:800;letter-spacing:-.3px}}
    .provider-sub{{font-size:11px;color:var(--muted);margin-top:1px}}
    .provider-type{{font-size:11px;font-weight:600;margin-top:10px;text-transform:uppercase;
                    letter-spacing:.5px;color:var(--muted)}}
    .provider-cert{{font-size:11px;color:var(--muted);margin-top:3px}}
    .provider-cpm{{font-size:12px;font-weight:600;margin-top:10px;font-variant-numeric:tabular-nums}}

    /* badges */
    .badge{{display:inline-flex;align-items:center;font-size:10px;font-weight:700;
            padding:2px 7px;border-radius:999px;white-space:nowrap}}
    .badge-warn{{background:#FEF3C7;color:#92400E}}
    .badge-ok  {{background:#D1FAE5;color:#065F46}}
    .badge-info{{background:#DBEAFE;color:#1E40AF}}

    /* heat-map matrix */
    .matrix-wrap{{overflow-x:auto}}
    .matrix{{width:100%;border-collapse:collapse;font-size:13px}}
    .matrix th{{padding:10px 14px;text-align:center;font-size:12px;
                border-bottom:2px solid var(--border);background:var(--bg)}}
    .matrix th:first-child{{text-align:left}}
    .matrix td{{padding:0;border-bottom:1px solid var(--border);vertical-align:middle}}
    .scenario-cell{{padding:12px 14px;min-width:180px}}
    .scenario-name{{font-size:11px;color:var(--muted)}}
    .cell{{padding:10px 12px;text-align:center;cursor:default;transition:opacity .15s}}
    .cell:hover{{opacity:.85}}
    .cell.winner{{outline:2px solid currentColor;outline-offset:-2px;border-radius:4px}}
    .cell-cost{{display:block;font-weight:700;font-size:14px;font-variant-numeric:tabular-nums}}
    .cell-cpm,.cell-model{{display:block;font-size:10px;color:var(--muted);margin-top:1px}}
    .winner-cell{{padding:8px 12px;min-width:110px}}
    .chip-winner{{display:inline-block;font-size:11px;font-weight:700;
                  padding:3px 10px;border-radius:999px}}

    /* breakeven */
    table.be{{width:100%;border-collapse:collapse;font-size:13px}}
    table.be th{{background:var(--bg);padding:8px 14px;text-align:left;
                 border-bottom:2px solid var(--border);font-weight:600;white-space:nowrap}}
    table.be td{{padding:9px 14px;border-bottom:1px solid var(--border);vertical-align:middle}}
    table.be tr:last-child td{{border-bottom:none}}
    table.be tr:hover td{{background:#F9FAFB}}
    .num{{text-align:right;font-variant-numeric:tabular-nums}}
    .bold{{font-weight:700}}
    .muted{{color:var(--muted);font-style:italic}}
    .chip{{display:inline-block;font-size:11px;font-weight:700;
           padding:2px 10px;border-radius:999px}}

    /* detail table */
    .data-wrap{{overflow-x:auto}}
    table.data{{width:100%;border-collapse:collapse;font-size:12px}}
    table.data th{{background:var(--bg);padding:7px 10px;text-align:left;
                   border-bottom:2px solid var(--border);font-weight:600;white-space:nowrap}}
    table.data td{{padding:7px 10px;border-bottom:1px solid var(--border)}}
    table.data tr:hover td{{background:#F9FAFB}}

    /* legend */
    .legend{{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);
             margin-top:8px}}
    .legend-dot{{width:10px;height:10px;border-radius:2px;display:inline-block}}

    /* footer */
    footer{{font-size:11px;color:var(--muted);margin-top:32px;padding-top:14px;
            border-top:1px solid var(--border)}}
    footer a{{text-decoration:underline}}
  </style>
</head>
<body>
<header>
  <h1>Sovereign LLM Bench — TCO Cloud Souverain Français</h1>
  <p>
    4 scénarios grands comptes &nbsp;·&nbsp;
    4 clouds souverains FR &nbsp;·&nbsp;
    Tarifs au {retrieved} &nbsp;·&nbsp;
    Taux USD/EUR {usd_eur} &nbsp;·&nbsp;
    <code style="opacity:.7">python run.py compare --json | jq .</code>
  </p>
</header>

<div class="container">

  <!-- PROVIDER CARDS -->
  <section>
    <h2>Providers comparés</h2>
    <div class="provider-grid">
      {cards_html}
    </div>
    <div class="legend">
      <span><span class="badge badge-warn">Proxy</span> Prix estimé via plateforme sous-jacente (pas de tarif public LLM)</span>
      <span><span class="badge badge-ok">Officiel</span> Prix publics sur le site du provider</span>
      <span><span class="badge badge-info">GPU €/h</span> Coût GPU converti en coût/token via llmfit</span>
    </div>
  </section>

  <!-- HEAT-MAP MATRIX -->
  <section>
    <h2>Matrice de comparaison — coût mensuel (€)</h2>
    <div class="card" style="padding:0">
      <div class="matrix-wrap">
        <table class="matrix">
          <thead>
            <tr>
              <th>Scénario</th>
              {header_cells}
              <th>Plus économique</th>
            </tr>
          </thead>
          <tbody>
            {matrix_rows}
          </tbody>
        </table>
      </div>
    </div>
    <div style="font-size:11px;color:var(--muted);margin-top:8px">
      Intensité de couleur = position dans la fourchette min–max de chaque provider.
      Encadré = moins cher sur ce scénario.
    </div>
  </section>

  <!-- BREAKEVEN -->
  <section>
    <h2>Seuils de rentabilité — OVH self-hosted vs API</h2>
    <div class="card" style="padding:0">
      <table class="be">
        <thead>
          <tr>
            <th>Scénario</th>
            <th>vs Provider API</th>
            <th class="num">OVH / mois</th>
            <th class="num">API / mois</th>
            <th class="num">Écart</th>
            <th class="num">Breakeven*</th>
            <th>Verdict</th>
          </tr>
        </thead>
        <tbody>{be_rows}</tbody>
      </table>
    </div>
    <p style="font-size:11px;color:var(--muted);margin-top:8px">
      * Breakeven = mois nécessaires pour amortir 12 mois de GPU (proxy capex) grâce à l'économie mensuelle.
    </p>
  </section>

  <!-- FULL DATA TABLE -->
  <section>
    <h2>Données complètes</h2>
    <div class="card data-wrap" style="padding:0">
      <table class="data">
        <thead>
          <tr>
            <th>Scénario</th><th>Provider</th><th>Modèle</th>
            <th class="num">Tokens/jour</th>
            <th class="num">€/jour</th>
            <th class="num bold">€/mois</th>
            <th class="num">€/an</th>
            <th class="num">€/M tok</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
  </section>

  <footer>
    <p><strong>Sources de tarifs</strong> (prix list publics au {retrieved}, sans remise volume)</p>
    <p>
      S3NS proxy →
      <a href="https://cloud.google.com/vertex-ai/generative-ai/pricing">cloud.google.com/vertex-ai/generative-ai/pricing</a>
      &nbsp;·&nbsp;
      Bleu proxy →
      <a href="https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/aoai/">azure.microsoft.com pricing/ai-foundry-models/aoai</a>
      &nbsp;·&nbsp;
      Scaleway →
      <a href="https://www.scaleway.com/en/pricing/model-as-a-service/">scaleway.com/pricing/model-as-a-service</a>
      &nbsp;·&nbsp;
      OVH GPU →
      <a href="https://www.ovhcloud.com/en/public-cloud/prices/">ovhcloud.com/public-cloud/prices</a>
    </p>
    <p>
      Throughput OVH : formule <a href="https://github.com/AlexsJones/llmfit">llmfit</a>
      — tps = (bandwidth_gbps / model_size_gb) × 0.55
      &nbsp;·&nbsp;
      ⚠ S3NS / Bleu : tarifs proxy — contacter les providers pour les tarifs contractuels souverains réels
    </p>
    <p>
      CLI : <code>python run.py --help</code> ·
      JSON : <code>python run.py compare --json</code> ·
      Repo : <a href="https://github.com/desmartinguillaume-a11y/sovereign-llm-bench">sovereign-llm-bench</a>
      · Apache 2.0
    </p>
  </footer>

</div>

</body>
</html>"""


# ── colour helper ─────────────────────────────────────────────────────────

def _heat_color(pct: float, dark_hex: str, light_hex: str) -> str:
    """Interpolate between light (0%) and a tinted version (100%)."""
    def h2rgb(h: str):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    light = h2rgb(light_hex)
    dark  = h2rgb(dark_hex)
    # blend: 0% = light background, 100% = 30% dark tint on white
    tint = tuple(int(255 - (255 - d) * 0.35 * pct) for d in dark)
    r = tuple(int(light[i] + (tint[i] - light[i]) * pct) for i in range(3))
    return f"rgb({r[0]},{r[1]},{r[2]})"
