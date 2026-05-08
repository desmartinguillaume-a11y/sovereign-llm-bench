# sovereign-llm-bench

**Benchmark reproductible du TCO réel des LLM en environnement souverain français.**

> Licence Apache 2.0 — contributions bienvenues.

---

## ⚠️ Disclaimer

Ce benchmark est construit exclusivement à partir d'informations publiques
(tarifs publiés sur les sites officiels des fournisseurs, documentation
technique publique, benchmarks communautaires open source).

Il ne s'appuie sur aucune donnée contractuelle, confidentielle ou interne.
Les prix S3NS et Bleu sont des proxies basés sur les tarifs publics
des plateformes sous-jacentes (Vertex AI / Azure OpenAI) —
les tarifs souverains réels peuvent différer significativement.

Ce repo est un outil d'estimation indicative, pas un devis.
Les résultats ne constituent pas un engagement tarifaire de la part
des fournisseurs mentionnés.

Dernière mise à jour des prix : 2026-05-08.
Vérifiez toujours les tarifs en vigueur avant toute décision d'achat.

---

## Ce que ce repo fait

Pour 4 infrastructures souveraines françaises × 4 scénarios de charge,
il calcule :

- **Coût journalier / mensuel / annuel** en euros par (scénario, provider, modèle)
- **Seuil de rentabilité** du self-hosted OVH vs chaque API pay-per-token
- Un **rapport HTML** auto-contenu avec heat-map et tableaux breakeven
- Des **CSV exportables**

Le calcul TCO tourne **sans aucun appel API** — le pricing est versionné dans `config/pricing.yaml`.

---

## Infrastructures comparées

| Infrastructure | Type | Certification | Source des prix |
|---|---|---|---|
| [S3NS](https://s3ns.io) (Thales × GCP) | API pay-per-token | SecNumCloud 3.2 | [Vertex AI pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing) ⚠ proxy |
| [Bleu](https://bleu.cloud) (Microsoft × Orange) | API pay-per-token | SecNumCloud en cours | [Azure OpenAI pricing](https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/aoai/) ⚠ proxy |
| [Scaleway](https://www.scaleway.com/en/pricing/model-as-a-service/) Generative APIs | API pay-per-token | HDS · ISO 27001 | [scaleway.com/pricing](https://www.scaleway.com/en/pricing/model-as-a-service/) ✓ officiel |
| [OVH Self-hosted](https://www.ovhcloud.com/en/public-cloud/prices/) GPU cloud | GPU/heure | HDS · SecNumCloud | [ovhcloud.com/prices](https://www.ovhcloud.com/en/public-cloud/prices/) ✓ officiel |
| On-prem OpenShift GPU | Capex amorti | Votre datacenter | `config/assumptions.yaml` ⚠ hypothèses documentées 2024 |

---

## Scénarios de charge

| ID | Cas d'usage | Tokens input/jour | Tokens output/jour |
|---|---|---|---|
| S1 | RAG léger — 200 users, Q&A doc interne | 1 000 000 | 400 000 |
| S2 | Chatbot support — 1 000 users, historique contexte | 18 000 000 | 8 000 000 |
| S3 | Call center résumé post-appel — 2 000 agents | 144 000 000 | 32 000 000 |
| S4 | Call center temps réel — sentiment + suggestion | 432 000 000 | 130 000 000 |

---

## Démarrage rapide

```bash
# 1. Cloner
git clone https://github.com/desmartinguillaume-a11y/sovereign-llm-bench
cd sovereign-llm-bench

# 2. Installer la seule dépendance requise
pip install pyyaml

# 3. Rapport complet : terminal + CSV + HTML
python run.py

# 4. Ouvrir le rapport
open results/report_$(date +%F).html
```

### CLI

```bash
# Matrice de comparaison (terminal)
python run.py compare

# Filtrer sur un scénario
python run.py compare --scenario S2

# Calculer un volume custom
python run.py calc --input 27M --output 3M
python run.py calc --input 27M --output 3M --provider scaleway

# Tarifs unitaires configurés
python run.py prices

# Sortie JSON (compatible jq)
python run.py compare --json | jq '.[] | select(.scenario_id=="S2")'
python run.py prices --json
```

---

## Sources de données

| Provider | URL directe | Type | Date |
|---|---|---|---|
| S3NS (proxy Vertex AI) | [cloud.google.com/vertex-ai/generative-ai/pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing) | Liste publique | 2026-05-08 |
| Bleu (proxy Azure OpenAI) | [azure.microsoft.com/.../aoai](https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/aoai/) | Liste publique | 2026-05-08 |
| Scaleway | [scaleway.com/en/pricing/model-as-a-service](https://www.scaleway.com/en/pricing/model-as-a-service/) | Liste publique | 2026-05-08 |
| OVH GPU cloud | [ovhcloud.com/en/public-cloud/prices](https://www.ovhcloud.com/en/public-cloud/prices/) | Liste publique | 2026-05-08 |
| Throughput OVH | [github.com/AlexsJones/llmfit](https://github.com/AlexsJones/llmfit) | Formule llmfit | — |

Les prix sont versionnés dans `config/pricing.yaml` avec leur `source_url` et `retrieved_date`.
Pour mettre à jour, consulter les URLs ci-dessus, modifier le YAML et committer (`git log` = historique de prix).

---

## Structure

```
sovereign-llm-bench/
├── config/
│   ├── pricing.yaml        # prix publics versionnés (source + date)
│   └── scenarios.yaml      # définition des 4 scénarios
├── benchmark/
│   ├── tco_calculator.py   # moteur de calcul TCO (offline, formule llmfit)
│   ├── runner.py           # orchestration + export CSV
│   ├── cli.py              # affichage terminal (compare, calc, prices)
│   └── report.py           # rapport HTML statique auto-contenu
├── results/
│   └── report_YYYY-MM-DD.html   # rapport pré-généré
├── run.py                  # point d'entrée unique
└── requirements.txt
```

---

## Hypothèses et limites

- **Jours ouvrés** : 22/mois, 12 mois/an. Ajustable dans `tco_calculator.py`.
- **Taux USD/EUR** : 0.92 (mai 2026). Stocké dans `pricing.yaml`, à mettre à jour selon le cours.
- **OVH throughput** : formule llmfit — `tps = (bandwidth_gbps / model_size_gb) × 0.55`.
  Le débit réel dépend du hardware effectif, de la config vLLM et du mix input/output.
- **Volume discounts** : non appliqués (prix list publics uniquement).
- **S3NS / Bleu** : les prix proxy sont des minima — le surcoût souverain contractuel peut être significatif.

---

## Hypothèses on-prem

Le modèle on-prem calcule un **coût annuel fixe** indépendant du volume de tokens :

```
coût_annuel = (prix_achat / durée_amortissement)   # capex
            + (prix_achat × taux_maintenance)       # maintenance constructeur
            + (tdp_watts / 1000 × PUE × 8760h × prix_kWh)  # électricité
            + licence_openshift_annuelle
            + (ETP_ops × coût_ETP_annuel)
```

Le nombre de serveurs est calculé par scénario selon le TPS de sortie requis :
`serveurs = max(1, ceil(tps_requis / (tps_par_gpu × gpus_par_serveur)))`

Le coût mensuel on-prem est `coût_annuel / 12` (serveurs en 24/7, pas seulement les jours ouvrés).

Toutes les hypothèses sont dans [`config/assumptions.yaml`](config/assumptions.yaml) — serveur de référence : Dell PowerEdge / HPE ProLiant 4× A100 80GB, amorti sur 4 ans, avec licence OpenShift et 0,3 ETP ops.

---

## Contribuer

Les PR sont bienvenues pour :
- Mettre à jour les prix après une annonce fournisseur
- Ajouter un nouveau provider EU (Clever Cloud, Outscale, Mistral AI…)
- Ajouter un scénario métier (juridique, médical, code…)
- Améliorer le modèle de throughput OVH
