# 🌍 Démo “EcoAdvisor” – Mobilité Bas Carbone

### _Écosystème Fred – Données publiques Rhône / Lyon_

## 🎯 Objectif de la démo

Cette démo illustre comment un agent **Fred** peut aider un collaborateur (ou citoyen) à :

- Estimer son **impact CO₂** sur son trajet domicile ↔ travail
- Comparer des **alternatives bas carbone** (vélo, TCL, covoiturage, marche)
- Exploiter des **données ouvertes locales** (métropole de Lyon)
- Produire un **rapport synthétique et actionnable**

Cette démonstration est destinée à un contexte “**AI for Good**”, notamment pour la **Compagnie Nationale du Rhône (CNR)**.

---

# 📂 Données publiques utilisées (OpenData Lyon)

Les fichiers bruts doivent être placés dans `~/Documents/Rhone/` :

- **Aménagements cyclables**  
  `amenagements-cyclables-metropole-lyon.csv`

- **Points d’arrêt TCL**  
  `points-arret-reseau-transports-commun-lyonnais.csv`

- **Codes postaux (optionnel, unused v1)**  
  `geo_codes.csv`

Ressources :

- https://data.grandlyon.com
- https://transport.data.gouv.fr

## ⚙️ Étape 0 — Baseline stable

1. **Charger les CSV via l’UI Fred / Knowledge Flow**  
   - Ouvrir l’interface d’ingestion tabulaire.  
   - Importer `bike_infra_demo.csv` et `tcl_stops_demo.csv` dans la base DuckDB exposée par le serveur MCP tabulaire (mêmes noms de tables).  
   - Vérifier via l’outil “Lister les datasets” que les deux tables sont bien disponibles.
2. **Démarrer Knowledge Flow + Agentic Backend** puis sélectionner l’agent *EcoAdvisor*.
3. **Conduite attendue** : l’agent suit le pattern Tessa (reasoner → tools → reasoner) et produit un bilan CO₂ markdown avec :
   - un tableau comparant voiture / TCL / vélo,
   - des hypothèses explicites (distance, fréquence, facteurs),
   - 2–3 suggestions pour réduire l’empreinte.

Extrait attendu :

```markdown
| Mode | CO₂ / semaine | Hypothèses |
| --- | --- | --- |
| Voiture | 19.2 kg | 10 km x 2 trajets x 5 j, 0.192 kg/km |
| TCL | 1.0 kg | même distance, 0.01 kg/km |
| Vélo | 0 kg | émission nulle |

**Hypothèses** : distance estimée via utilisateur, facteurs ADEME simplifiés.  
**Pistes bas carbone** : tester TCL les jours de pluie, mix vélo + TCL quand météo clémente.
```

---

## 🧱 Étape 1 — Workflow structuré (reasoner → tools → compute_co2 → reasoner_final)

Cette étape applique la roadmap :

- `EcoState` transporte désormais des champs structurés (`distance_km`, `frequency_days`, `mode`).  
  Ils sont extraits automatiquement des derniers messages utilisateur (regex FR/EN basiques).
- Nouveau nœud LangGraph `compute_co2` (Python pur) qui :
  - applique les facteurs d’émission (`voiture=0.192`, `tcl=0.01`, `vélo=0`)
  - produit un tableau Markdown standard + hypothèses + suggestions bas carbone
  - renvoie un `ToolMessage` interne consommé par `reasoner_final`.
- Le graphe suit la séquence :  
  `START → reasoner → tools ↺ (…) → compute_co2 → reasoner_final → END`
  - Tant que le LLM demande un tool MCP, on boucle `reasoner ↔ tools`.  
  - Dès que `tools_condition` signale la fin des appels, on passe par `compute_co2`.  
  - `reasoner_final` réutilise **strictement** le tableau fourni pour rédiger la réponse.

✅ Résultat : calculs auditables, structure claire entre raisonnement LLM et calcul Python, et format de sortie stable pour la démo.

---

## 🧱 Étape 2 — Référentiel CO₂ externe (HTTP)

- Lancer le serveur MCP de référence CO₂ (`academy/co2-estimation-service`):  
  `uvicorn co2_estimation_service.server_mcp:app --host 127.0.0.1 --port 9798`
- Ajouter sa configuration MCP (`mcp-co2-demo`) côté Agentic Backend, puis relancer l’app.
- EcoAdvisor n’embarque plus de facteurs dans le prompt :  
  - les tools `list_emission_modes`, `get_emission_factor`, `compare_trip_modes` fournissent les facteurs, la source et la date de mise à jour,  
  - le nœud `compute_co2` consomme ces tools pour bâtir le tableau Markdown,  
  - `reasoner_final` cite explicitement les sources ADEME renvoyées par le service.
- En cas d’indisponibilité du service, un calcul de secours (facteurs statiques) est conservé pour la démo.

---

## 🧱 Préparation des données (pipeline historique)

Fichier : `rhone_inspect.py`

Permet de :

- détecter séparateurs
- visualiser colonnes
- valider structure des datasets
- préparer le nettoyage

**Rationale Fred :**

> Toujours inspecter un dataset tel quel avant de le transformer.  
> Décision réfléchie sur les colonnes à garder → meilleur raisonnement agentique.

---

# 🧱 Étape 2 — Préparation des CSV “démo-ready”

Fichier à générer : `prepare_rhone_demo_tables.py`

Sortie :

- `bike_infra_demo.csv`
- `tcl_stops_demo.csv`

**Idée générale :**

- normaliser les nombres (virgule → point)
- renommer colonnes de manière explicite
- supprimer bruit administratif
- préparer une table simple et stable pour un agent tabulaire

**Rationale Fred :**

> Un agent tabulaire travaille mieux avec des colonnes explicites et nettoyées.  
> Mieux vaut une table réduite, propre et stable qu'un dump complet illisible.

---

# 🧠 Agent principal : **EcoAdvisor**

## 🎛 Architecture LangGraph (version simple)

1. **Node 1 — Input utilisateur**

   - distance
   - adresse
   - mode de transport actuel

2. **Node 2 — Tabular lookup**

   - interroger `bike_infra_demo.csv`
   - interroger `tcl_stops_demo.csv`
   - récupérer pistes cyclables / arrêts proches

3. **Node 3 — CO₂ compute (Python pur)**

   - facteurs statiques ADEME (v1)
   - calcul impact km × facteur
   - comparaison alternatives

4. **Node 4 — Explication / synthèse LLM**

   - tableau clair
   - reformulation accessible
   - “meilleure alternative”

5. **Node 5 — Sortie formatée**
   - markdown lisible
   - éventuellement mini-carte ou pseudo-carte ASCII

---

# 🧪 Exemple utilisateur

> “J’habite Villeurbanne Rue Masséna, je vais à Gerland.  
> 10 km en voiture matin et soir.  
> Quel est mon impact CO₂ et quelles alternatives bas carbone existent ?”

---

# 📊 Facteurs d’émission (version simple v1)

```python
EMISSION_FACTORS = {
    "voiture_thermique": 0.192,  # kg CO₂/km – source ADEME
    "tcl": 0.01,
    "velo": 0.0,
    "marche": 0.0,
    "voiture_electrique": 0.012,
}
```
