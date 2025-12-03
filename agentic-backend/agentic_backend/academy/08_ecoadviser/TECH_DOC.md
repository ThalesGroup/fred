# EcoAdvisor — fonctionnement global

## 1. Pourquoi cet agent ?
- Aider un collaborateur à mesurer l’empreinte carbone de ses trajets quotidiens et à identifier des alternatives bas carbone réalistes.
- Valoriser les données publiques (Grand Lyon, ADEME) et les présenter dans un langage simple, orienté décision.
- Servir d’exemple réplicable pour d’autres territoires ou cas d’usage mobilité/CO₂.

## 2. Architecture conversationnelle
```
Utilisateur ↔ LLM GPT-4o (raisonneur principal)
                   │
                   ├─ MCP Tabular      → jeux de données locaux (DuckDB)
                   ├─ MCP CO₂ Service  → facteurs ADEME + calcul compare_trip_modes
                   ├─ MCP Traffic      → API WFS Grand Lyon (trafic routier)
                   └─ MCP TCL          → API RDATA Grand Lyon (passages TCL)
```
- Le modèle de langage pilote la conversation et décide quand appeler un outil grâce au tool-calling OpenAI.
- Chaque outil renvoie une trace structurée (JSON) que l’agent réutilise pour sourcer ses réponses.

## 3. Modèle de langage utilisé
- Par défaut : **OpenAI gpt-4o**, température 0, timeout 30 s (config `agentic-backend/config/configuration_academy.yaml`).
- Le modèle est interchangeable via la configuration (Azure OpenAI, Claude, etc.) sans modifier le code de l’agent.
- Les réponses sont générées dans la langue détectée (français par défaut) et structurées en Markdown avec un tableau CO₂ final.

## 4. Services et API appelés
| Service | API / Stack | Quels appels ? | Ce que voit l’utilisateur |
| --- | --- | --- | --- |
| MCP Tabular (`mcp-knowledge-flow-mcp-tabular`) | Serveur DuckDB piloté par Knowledge Flow (pas d’URL publique) exposant notamment `bike_infra_demo` et `tcl_stops_demo`. | `get_context`, `list_tables`, `query` avec des filtres géographiques simples. | Carte mentale des aménagements cyclables, arrêts TCL pertinents, citations de colonnes réelles. |
| MCP CO₂ Service (`mcp-co2-service`, `http://127.0.0.1:9798/mcp`) | FastAPI locale qui interroge l’API ADEME Base Carbone `https://data.ademe.fr/data-fair/api/v1/datasets/base-carboner/lines`. | `list_emission_modes`, `get_emission_factor`, `compare_trip_modes`, `reload_emission_cache`. | Tableau CO₂ hebdo par mode + mention explicite de la source ADEME (nom, date, URL). |
| MCP Traffic Service (`mcp-traffic-service`) | Client WFS Grand Lyon sur `https://data.grandlyon.com/geoserver/metropole-de-lyon/ows` (typename `metropole-de-lyon:pvo_patrimoine_voirie.pvotrafic`). | `get_live_traffic_segments(origin_lat, origin_lng, dest_lat, dest_lng)` avec une bbox automatique. | Contexte “Grand Lyon WFS signale trafic dense/fluide” ajouté à la synthèse voiture. |
| MCP TCL Service (`mcp-tcl-service`) | Client RDATA Grand Lyon (`https://data.grandlyon.com/fr/datapusher/ws/rdata`, dataset `tcl_sytral.tclpassagesarret_2_0_0`). | `get_tcl_realtime_passages(stop_code, line)` après identification de l’arrêt via la table tabulaire. | Liste/tables des prochains passages avec heure locale, ligne et direction. |

## 5. Parcours type d’une question
1. **Clarifier la situation** : EcoAdvisor demande origine, destination, mode actuel, distance et fréquence.
2. **Lister les données disponibles** : appel `get_context` pour s’assurer que `bike_infra_demo` / `tcl_stops_demo` sont chargées.
3. **Explorer les datasets** : requêtes DuckDB (via MCP tabular) pour trouver des pistes cyclables ou arrêts TCL proches des lieux cités par l’utilisateur.
4. **Calculer les émissions** : appel `list_emission_modes` puis `compare_trip_modes` (ou `get_emission_factor`) pour obtenir les kg CO₂/semaine de chaque option.
5. **Valider les conditions réelles** :
   - Si la voiture est évoquée : `get_live_traffic_segments` fournit l’état de trafic de la zone Grand Lyon correspondante.
   - Si les TCL sont envisagés : `get_tcl_realtime_passages` donne les prochains départs à partir du `stop_id` extrait du dataset.
6. **Synthèse** : réponse structurée avec sous-titres (`### Synthèse rapide`, etc.), tableau CO₂, hypothèses, équivalences (heures d’aspirateur / jours de chauffage) et recommandations avec emojis.

## 6. Données embarquées / prérequis
- `data/bike_infra_demo.csv` : tronçons cyclables de la métropole de Lyon.
- `data/tcl_stops_demo.csv` : arrêts TCL (coordonnées, lignes).
- Autres CSV (temps de parcours, consommations énergétiques…) disponibles dans le dossier `data/` et importables à volonté via l’UI tabulaire.
- Les fichiers peuvent être remplacés par des jeux clients (autres territoires, données internes) – le serveur DuckDB et les tools restent identiques.

## 7. Comportements de repli
- **Service CO₂ indisponible** : bascule automatique sur des facteurs par défaut (voiture 0,192 kg/km, TCL 0,01 kg/km, vélo/marche 0) avec transparence dans la réponse.
- **APIs Grand Lyon inaccessibles** : l’agent mentionne l’indisponibilité et continue avec les données tabulaires ou des recommandations génériques.
- **Informations utilisateur incomplètes** : l’agent pose des questions ciblées plutôt que d’extrapoler (distance, fréquence, contraintes météo).

## 8. Personnalisation côté client
- **Prompt & persona** : éditables depuis l’interface Academy (champ `prompts.system` + bloc `persona_salarie_cnr`) pour refléter vos politiques de mobilité ou un autre profil d’utilisateur.
- **Sources de données** : branchez vos propres CSV/SQL dans le serveur tabulaire (émissions internes, parkings entreprise, navettes) pour enrichir les recommandations.
- **Modèle** : changez `default_chat_model` ou forcez un modèle spécifique pour EcoAdvisor si vous devez rester On-Prem / Européen.

EcoAdvisor associe donc un LLM GPT-4o, les données locales DuckDB et trois APIs publiques (ADEME, trafic Grand Lyon, RDATA TCL) afin de produire un bilan CO₂ contextualisé, sourcé et directement exploitable par les équipes métier.
