# EcoAdvisor — Roadmap vers une démo enrichie avec données live

Ce document décrit l’évolution progressive de l’agent **EcoAdvisor**, depuis la v1 actuelle (datasets Rhône + calcul CO₂) jusqu’à une démonstration avancée intégrant **données live**, **référentiels externes**, et **workflow structuré**.

---

## 0️⃣ Étape 0 — Stabiliser la v1 (baseline démo)

Avant d’ajouter du live ou de la complexité, on fixe une version stable d’EcoAdvisor :

- Fonctionne avec les datasets tabulaires locaux :
  - `bike_infra_demo`
  - `tcl_stops_demo`
- Script `load_demo_tables.py` charge ces CSV dans la base DuckDB exposée par MCP.
- Utilise le pattern Tessa : `reasoner → tools → reasoner` (tool-calling)
- Produit un bilan CO₂ clair en Markdown :
  - comparaison voiture / TCL / vélo
  - hypothèses explicites
  - suggestions bas carbone

**Justification Fred** :  
Toujours garder une base stable pour sécuriser les démonstrations.

---

## 1️⃣ Étape 1 — Workflow plus structuré (sans HTTP)

### 1.1 Champs structurés dans l’état

Ajouter dans `EcoState` les champs :

- `distance_km`
- `frequency_days`
- `mode`

Ils peuvent provenir :
- du LLM via prompt,
- d’un mini outil Python (parse d’une phrase décrivant la distance et la fréquence).

### 1.2 Ajout d’un nœud LangGraph : `compute_co2`

Créer un nœud dédié :

START → reasoner → tools → compute_co2 → reasoner_final → END

yaml
Copy code

`compute_co2` :
- applique les facteurs d’émission,
- valide les hypothèses,
- renvoie un tableau Markdown standard avec résultats CO₂ hebdomadaires.

### 1.3 Bénéfices

- Séparation logique : LLM (raisonnement) vs Python (calculs fiables)
- Calculs audités, testables
- Base solide pour ajouter d’autres sources de données

---

## 2️⃣ Étape 2 — Ajouter un référentiel CO₂ externe (HTTP)

Objectif : ne plus stocker les facteurs CO₂ dans le prompt.

### Option A — Service interne Python

Créer un service :

get_emission_factor(mode: str) → { factor_kg_per_km, source, last_update }

yaml
Copy code

Ce service peut :
- appeler une API (ADEME / Base Carbone / open data),
- ou lire un JSON/CSV mis à jour quotidiennement,
- renvoyer un facteur fiable + source + date.

### Option B — Tool MCP HTTP

Exposer ce service en tant que tool pour que le LLM puisse l’appeler.

### Bénéfices

- EcoAdvisor cite les sources :  
  “Facteur CO₂ automobile : 0.192 kg/km (source ADEME 2024)”
- Données vivantes, crédibles, reproductibles.

**Justification Fred** :  
Montre que l’agent repose sur des référentiels offerts par des APIs publiques.

---

## 3️⃣ Étape 3 — Intégrer des données “live” (trafic, TCL, météo)

C’est la partie qui crée un **effet “wow”** en démo.

### 3A — Données TCL en temps réel

Tool :

get_public_transport_status(line_or_city)
→ { disruptions, next_departures, message }

yaml
Copy code

- Utilisation :  
  “Ligne C7 : retards de 10 minutes aujourd’hui, travaux près du Tonkin.”

### 3B — Trafic routier live

Tool :

get_traffic_level(area)
→ { level: low/medium/high, avg_speed_kmh, congestion_factor }

yaml
Copy code

- Utilisation :  
  “Trafic élevé sur Villeurbanne → +15 min estimées en voiture.”

### 3C — Météo pour la mobilité

Tool :

get_weather_summary(city)
→ { conditions, temperature, rain_risk }

yaml
Copy code

- Utilisation :
  “Pluie légère prévue. Vélo possible mais moins confortable.”

### Bénéfices

- L’agent combine :
  - données tabulaires locales,
  - facteurs CO₂ externes,
  - signaux live de mobilité.

---

## 4️⃣ Étape 4 — Enrichir la démo côté frontend

Une fois les capacités logiques en place, renforcer l’impact visuel.

### 4.1 Cartes et visualisations

- Retourner (`lat`, `lon`) pour les arrêts TCL
- Lignes cyclables proches
- Affichage sur une carte (Leaflet / Mapbox) ou pseudo-carte simple

### 4.2 Tableaux UI enrichis

Transformer le tableau Markdown en UI :

- Mode  
- CO₂ / semaine  
- Temps estimé  
- Score bas carbone  
- Badges : *-95 % CO₂*, *0 émissions*, etc.

### 4.3 Scénarios de démonstration pré-packagés

Préparer 2–3 scénarios :

- Villeurbanne → Gerland en voiture (10 km)
- Oullins → Part-Dieu en TCL + marche
- Secteur rural → alternative covoiturage

**Justification Fred** :  
Une démo fluide et rassurante, sans dépendre à 100% de la spontanéité.

---

# Résumé global

| Étape | Objectif | Valeur |
|------|----------|--------|
| 0 | Stabiliser la v1 | Démo immédiatement fiable |
| 1 | Structurer workflow + `compute_co2` | Architecture propre, calcul déterministe |
| 2 | Référentiel CO₂ externe | Données crédibles, citations de sources |
| 3 | Intégrer trafic / TCL / météo live | “Wow effect”, démonstration moderne |
| 4 | UI riche + scénarios | Narration fluide, impact visuel fort |

---

# Prochaine action recommandée

Commencer par **Étape 1 : ajouter le nœud `compute_co2`**.

C’est la fondation qui permet ensuite :
- facteurs CO₂ externes,
- données live,
- UI enrichie,
- scénarios packagés.

Et qui ancre EcoAdvisor dans une architecture propre, testable et maintenable.



