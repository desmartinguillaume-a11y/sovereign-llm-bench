# sovereign-llm-bench

**Benchmark reproductible du TCO réel des LLM en environnement souverain européen.**

Audience : DSI / CIO grands comptes EU qui évaluent un déploiement LLM et veulent comparer
le coût total réel — pas un benchmark de performance, pas un classement qualitatif,
mais un coût en euros pour leur volume de production.

> Licence Apache 2.0 — contributions bienvenues.

---

## Ce que ce repo fait

Pour 4 infrastructures souveraines EU × 4 scénarios de charge grands comptes,
il calcule :

- **Coût journalier / mensuel / annuel** en euros
- **Seuil de rentabilité** du self-hosted OVH vs chaque API pay-per-token
- Un **CSV exportable** pour intégration dans un business case

Le calcul TCO tourne **sans aucun appel API** — le pricing est versionné dans `config/pricing.yaml`.

---

## Infrastructures comparées

| Infrastructure | Type | Data residency |
|---|---|---|
| [Mistral API](https://mistral.ai/technology/#pricing) | Pay-per-token | EU (Paris) |
| [Anthropic Claude API](https://www.anthropic.com/pricing) | Pay-per-token | EU (AWS eu-west) |
| [Azure OpenAI EU](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/) | Pay-per-token | West Europe / Sweden Central |
| [OVH Self-hosted](https://www.ovhcloud.com/fr/public-cloud/prices/) | GPU/heure | EU (Gravelines / Strasbourg) |

---

## Scénarios de charge

| ID | Cas d'usage | Tokens/jour |
|---|---|---|
| S1 | RAG léger — 200 users, Q&A doc interne | ~2M |
| S2 | Chatbot support — 1000 users, historique contexte | ~30M |
| S3 | Call center résumé post-appel — 2000 agents | ~176M |
| S4 | Call center temps réel — sentiment + suggestion + résumé | ~562M |

---

## Démarrage rapide

```bash
# 1. Cloner
git clone https://github.com/your-org/sovereign-llm-bench
cd sovereign-llm-bench

# 2. Installer la seule dépendance requise
pip install pyyaml

# 3. Lancer le benchmark TCO (aucune clé API nécessaire)
python run.py
```

Résultat : tableau comparatif en terminal + deux CSV dans `results/`.

### Validation live (optionnel)

Pour comparer la qualité des outputs sur un prompt français réel :

```bash
# Copier et remplir le fichier de clés
cp .env.example .env

# Installer les SDKs optionnels
pip install anthropic mistralai openai python-dotenv

# Lancer avec validation live
python run.py --validate
```

---

## Structure

```
sovereign-llm-bench/
├── config/
│   ├── pricing.yaml        # prix publics versionnés (source + date)
│   └── scenarios.yaml      # définition des 4 scénarios
├── models/                 # clients API optionnels (validation live)
│   ├── mistral.py
│   ├── claude.py
│   ├── azure_openai.py
│   └── ovh_selfhosted.py
├── benchmark/
│   ├── tco_calculator.py   # moteur de calcul TCO (offline)
│   └── runner.py           # orchestration + output CSV + table terminal
├── data/samples/           # prompts exemples synthétiques FR
├── results/                # CSV générés (non versionnés)
├── run.py                  # point d'entrée unique
└── .env.example
```

---

## Mettre à jour les prix

Les prix sont dans `config/pricing.yaml`. Chaque entrée indique la `source_url`
et la `retrieved_date`. Pour mettre à jour :

1. Consulter les pages de pricing listées dans `source_url`
2. Modifier les valeurs dans `pricing.yaml`
3. Mettre à jour `retrieved_date` et `usd_to_eur`
4. Committer (`git log` sert d'historique de prix)

---

## Hypothèses et limites

- **Jours ouvrés** : 22/mois, 12 mois/an. Ajustable dans `tco_calculator.py`.
- **OVH throughput** : calibré sur vLLM + A100 80GB avec batch_size=32, 4-bit GPTQ.
  Le débit réel dépend du hardware effectif, de la config vLLM et du mix input/output.
- **Taux USD/EUR** : stocké dans `pricing.yaml`, à mettre à jour selon le cours du jour.
- **Volume discounts** : non appliqués (prix list publics uniquement).
- **S4 temps réel** : le coût OVH est sous-estimé car il suppose 1 GPU en continu.
  En production avec 2000 agents simultanés, le parallélisme impose un scaling horizontal.

---

## Contribuer

Les PR sont bienvenues pour :
- Mettre à jour les prix après une annonce fournisseur
- Ajouter un nouveau fournisseur EU (Scaleway, Clever Cloud, Outscale…)
- Ajouter un scénario métier (juridique, médical, code…)
- Améliorer le modèle de throughput OVH

Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour les conventions.
