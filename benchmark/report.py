"""
Génère un rapport HTML statique auto-contenu avec Chart.js.

Produit results/report_YYYY-MM-DD.html — ouvrir dans un navigateur.
Nécessite Internet pour charger Chart.js depuis CDN (cdnjs.cloudflare.com).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from benchmark.tco_calculator import BreakevenResult, TCOCalculator, TCOResult

RESULTS_DIR = Path(__file__).parent.parent / "results"

PROVIDER_ORDER = ["s3ns", "bleu", "scaleway", "ovh_selfhosted"]
PROVIDER_LABELS = {
    "s3ns":           "S3NS (Thales×GCP)",
    "bleu":           "Bleu (MS×Orange)",
    "scaleway":       "Scaleway FR",
    "ovh_selfhosted": "OVH Self-hosted",
}
PROVIDER_COLORS = {
    "s3ns":           "#4285F4",   # Google blue
    "bleu":           "#00A4EF",   # Microsoft blue
    "scaleway":       "#7B2D8B",   # Scaleway purple
    "ovh_selfhosted": "#123F6D",   # OVH navy
}
PROVIDER_COLORS_LIGHT = {
    "s3ns":           "rgba(66,133,244,0.15)",
    "bleu":           "rgba(0,164,239,0.15)",
    "scaleway":       "rgba(123,45,139,0.15)",
    "ovh_selfhosted": "rgba(18,63,109,0.15)",
}


def build(results: list[TCOResult], breakevens: list[BreakevenResult]) -> Path:
    """Build and write the HTML report. Returns the output path."""
    RESULTS_DIR.mkdir(exist_ok=True)
    today = date.today().isoformat()
    out_path = RESULTS_DIR / f"report_{today}.html"

    # ---- Organise data ------------------------------------------------
    by_scenario: dict[str, dict[str, TCOResult]] = {}
    for r in results:
        by_scenario.setdefault(r.scenario_id, {})[r.provider] = r

    scenario_ids   = sorted(by_scenario.keys())
    scenario_names = [by_scenario[s][next(iter(by_scenario[s]))].scenario_name for s in scenario_ids]
    scenario_labels = [f"{sid} — {name}" for sid, name in zip(scenario_ids, scenario_names)]

    # Chart 1 — monthly cost per scenario
    cost_datasets = []
    for pid in PROVIDER_ORDER:
        values = [
            round(by_scenario[sid][pid].cost_month_eur, 0) if pid in by_scenario[sid] else 0
            for sid in scenario_ids
        ]
        cost_datasets.append({
            "label": PROVIDER_LABELS[pid],
            "data": values,
            "backgroundColor": PROVIDER_COLORS[pid],
            "borderColor": PROVIDER_COLORS[pid],
            "borderWidth": 1,
            "borderRadius": 4,
        })

    # Chart 2 — cost per million tokens
    cpm_datasets = []
    for pid in PROVIDER_ORDER:
        values = [
            round(by_scenario[sid][pid].cost_per_million_tokens_eur, 4) if pid in by_scenario[sid] else 0
            for sid in scenario_ids
        ]
        cpm_datasets.append({
            "label": PROVIDER_LABELS[pid],
            "data": values,
            "backgroundColor": PROVIDER_COLORS[pid],
            "borderColor": PROVIDER_COLORS[pid],
            "borderWidth": 1,
            "borderRadius": 4,
        })

    # Breakeven table data
    be_by_scenario: dict[str, dict[str, BreakevenResult]] = {}
    for be in breakevens:
        be_by_scenario.setdefault(be.scenario_id, {})[be.api_provider] = be

    # Proxy warning badge
    proxy_providers = {
        pid: pcfg.get("pricing_status", "")
        for pid, pcfg in TCOCalculator().pricing["providers"].items()
        if "PROXY" in pcfg.get("pricing_status", "")
    }

    usd_eur = TCOCalculator().usd_to_eur

    html = _render(
        today=today,
        scenario_ids=scenario_ids,
        scenario_labels=scenario_labels,
        cost_datasets=cost_datasets,
        cpm_datasets=cpm_datasets,
        by_scenario=by_scenario,
        be_by_scenario=be_by_scenario,
        proxy_providers=proxy_providers,
        usd_eur=usd_eur,
    )

    out_path.write_text(html, encoding="utf-8")
    return out_path


# ------------------------------------------------------------------
# HTML template
# ------------------------------------------------------------------

def _render(**ctx) -> str:
    today           = ctx["today"]
    scenario_ids    = ctx["scenario_ids"]
    scenario_labels = ctx["scenario_labels"]
    cost_datasets   = ctx["cost_datasets"]
    cpm_datasets    = ctx["cpm_datasets"]
    by_scenario     = ctx["by_scenario"]
    be_by_scenario  = ctx["be_by_scenario"]
    proxy_providers = ctx["proxy_providers"]
    usd_eur         = ctx["usd_eur"]

    # ---- full results table rows
    rows_html = ""
    for sid in scenario_ids:
        for pid in PROVIDER_ORDER:
            r = by_scenario[sid].get(pid)
            if r is None:
                continue
            proxy_badge = ' <span class="badge proxy">PROXY</span>' if pid in proxy_providers else ""
            rows_html += f"""
            <tr>
              <td><strong>{r.scenario_id}</strong> — {r.scenario_name}</td>
              <td>{PROVIDER_LABELS[pid]}{proxy_badge}</td>
              <td>{r.model_display_name}</td>
              <td class="num">{r.tokens_input_per_day + r.tokens_output_per_day:,}</td>
              <td class="num">€{r.cost_day_eur:,.2f}</td>
              <td class="num bold">€{r.cost_month_eur:,.0f}</td>
              <td class="num">€{r.cost_year_eur:,.0f}</td>
              <td class="num">€{r.cost_per_million_tokens_eur:.4f}</td>
            </tr>"""

    # ---- breakeven table rows
    be_rows = ""
    for sid in scenario_ids:
        bes = be_by_scenario.get(sid, {})
        for pid in PROVIDER_ORDER:
            if pid == "ovh_selfhosted":
                continue
            be = bes.get(pid)
            if be is None:
                continue
            if be.breakeven_months == float("inf"):
                be_str = '<span class="never">jamais</span>'
                winner = f'<span class="chip api">{PROVIDER_LABELS[pid]}</span>'
            else:
                be_str = f"{be.breakeven_months:.0f} mois"
                winner = '<span class="chip self">OVH self-hosted</span>'
            be_rows += f"""
            <tr>
              <td><strong>{sid}</strong></td>
              <td>{PROVIDER_LABELS[pid]}</td>
              <td class="num">€{be.selfhosted_cost_month_eur:,.0f}</td>
              <td class="num">€{be.api_cost_month_eur:,.0f}</td>
              <td class="num">{be_str}</td>
              <td>{winner}</td>
            </tr>"""

    # ---- proxy warning list
    proxy_html = ""
    if proxy_providers:
        items = "".join(
            f"<li><strong>{PROVIDER_LABELS.get(pid, pid)}</strong> — {status}</li>"
            for pid, status in proxy_providers.items()
        )
        proxy_html = f'<div class="warning"><strong>⚠ Tarifs proxy</strong><ul>{items}</ul></div>'

    chart_data_json = json.dumps({
        "labels": scenario_labels,
        "cost": cost_datasets,
        "cpm": cpm_datasets,
    }, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sovereign LLM Bench — Rapport TCO {today}</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"
          integrity="sha512-ZwR1/gSZM3ai6vCdI+LVF1zSq/5HznD3oD+sCoJrzXJ+yKen9RtNm9nNkyfknyIF8eFgW8phTKvAanV/oJXg=="
          crossorigin="anonymous" referrerpolicy="no-referrer"></script>
  <style>
    :root {{
      --blue:   #4285F4;
      --ms:     #00A4EF;
      --scw:    #7B2D8B;
      --ovh:    #123F6D;
      --bg:     #F8F9FB;
      --card:   #FFFFFF;
      --border: #E2E6EA;
      --text:   #1A1A2E;
      --muted:  #6C757D;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.5;
    }}
    header {{
      background: var(--text); color: #fff; padding: 28px 40px;
    }}
    header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
    header p  {{ opacity: .7; font-size: 13px; }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 32px; }}
    @media (max-width: 800px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
    .card {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 10px; padding: 24px;
    }}
    .card h2 {{ font-size: 15px; font-weight: 600; margin-bottom: 16px; color: var(--text); }}
    .card .sub {{ font-size: 12px; color: var(--muted); margin-top: 8px; }}
    .chart-wrap {{ position: relative; height: 300px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th {{
      background: var(--bg); text-align: left; padding: 8px 12px;
      font-weight: 600; border-bottom: 2px solid var(--border); white-space: nowrap;
    }}
    td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: #F0F4FF; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .bold {{ font-weight: 700; }}
    .badge {{
      display: inline-block; font-size: 10px; font-weight: 700;
      padding: 1px 5px; border-radius: 3px; vertical-align: middle;
      margin-left: 4px;
    }}
    .badge.proxy {{ background: #FFF3CD; color: #856404; border: 1px solid #FFE69C; }}
    .chip {{
      display: inline-block; font-size: 11px; font-weight: 600;
      padding: 2px 8px; border-radius: 12px;
    }}
    .chip.self {{ background: #D1FAE5; color: #065F46; }}
    .chip.api  {{ background: #DBEAFE; color: #1E40AF; }}
    .never {{ color: var(--muted); font-style: italic; }}
    .warning {{
      background: #FFFBEB; border: 1px solid #FCD34D; border-radius: 8px;
      padding: 14px 18px; margin-bottom: 24px; font-size: 13px;
    }}
    .warning ul {{ margin: 6px 0 0 18px; }}
    .warning li {{ margin-top: 3px; }}
    .meta {{
      font-size: 12px; color: var(--muted); margin-top: 32px;
      padding-top: 16px; border-top: 1px solid var(--border);
    }}
    section {{ margin-bottom: 32px; }}
    section h2 {{ font-size: 17px; font-weight: 700; margin-bottom: 16px; }}
  </style>
</head>
<body>
<header>
  <h1>Sovereign LLM Bench — Analyse TCO Cloud Souverain FR</h1>
  <p>Rapport généré le {today} · 4 scénarios grands comptes × 4 clouds souverains français · jours ouvrés (22/mois)</p>
</header>

<div class="container">

  {proxy_html}

  <div class="grid-2">

    <div class="card">
      <h2>Coût mensuel par scénario (€)</h2>
      <div class="chart-wrap">
        <canvas id="chartCost"></canvas>
      </div>
      <p class="sub">Taux USD/EUR : {usd_eur} · Coût/jour × 22 jours ouvrés</p>
    </div>

    <div class="card">
      <h2>Coût par million de tokens (€)</h2>
      <div class="chart-wrap">
        <canvas id="chartCPM"></canvas>
      </div>
      <p class="sub">Échelle logarithmique — total input + output</p>
    </div>

  </div>

  <section>
    <h2>Seuils de rentabilité — OVH self-hosted vs API</h2>
    <div class="card">
      <table>
        <thead>
          <tr>
            <th>Scénario</th>
            <th>vs Provider</th>
            <th class="num">OVH/mois</th>
            <th class="num">API/mois</th>
            <th class="num">Breakeven</th>
            <th>Plus économique</th>
          </tr>
        </thead>
        <tbody>
          {be_rows}
        </tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>Détail complet des résultats</h2>
    <div class="card" style="overflow-x:auto">
      <table>
        <thead>
          <tr>
            <th>Scénario</th>
            <th>Provider</th>
            <th>Modèle</th>
            <th class="num">Tokens/jour</th>
            <th class="num">Coût/jour</th>
            <th class="num">Coût/mois</th>
            <th class="num">Coût/an</th>
            <th class="num">€/M tokens</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>
  </section>

  <div class="meta">
    <p>Sources prix : Vertex AI (S3NS proxy) · Azure OpenAI (Bleu proxy) · scaleway.com · ovhcloud.com</p>
    <p>Throughput OVH calculé via formule llmfit — <a href="https://github.com/AlexsJones/llmfit">github.com/AlexsJones/llmfit</a> (bandwidth GPU × efficiency 0.55)</p>
    <p>Repo : <a href="https://github.com/desmartinguillaume-a11y/sovereign-llm-bench">sovereign-llm-bench</a> · Licence Apache 2.0</p>
  </div>

</div>

<script>
const D = {chart_data_json};

const opts = (title, log) => ({{
  responsive: true,
  maintainAspectRatio: false,
  plugins: {{
    legend: {{ position: "bottom", labels: {{ boxWidth: 12, font: {{ size: 12 }} }} }},
    tooltip: {{
      callbacks: {{
        label: ctx => ` ${{ctx.dataset.label}}: €${{Number(ctx.raw).toLocaleString("fr-FR")}}`
      }}
    }}
  }},
  scales: {{
    x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 11 }} }} }},
    y: {{
      type: log ? "logarithmic" : "linear",
      grid: {{ color: "#F0F0F0" }},
      ticks: {{
        font: {{ size: 11 }},
        callback: v => "€" + Number(v).toLocaleString("fr-FR")
      }}
    }}
  }}
}});

new Chart(document.getElementById("chartCost"), {{
  type: "bar",
  data: {{ labels: D.labels, datasets: D.cost }},
  options: opts("Coût mensuel (€)", false)
}});

new Chart(document.getElementById("chartCPM"), {{
  type: "bar",
  data: {{ labels: D.labels, datasets: D.cpm }},
  options: opts("€ / million tokens", true)
}});
</script>
</body>
</html>
"""
