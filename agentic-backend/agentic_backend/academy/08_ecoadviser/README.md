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

---

# 🧱 Étape 1 — Inspection des données

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
