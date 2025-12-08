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

> Les extraits nettoyés utilisés dans la démo sont déjà versionnés dans `agentic_backend/academy/08_ecoadviser/data/` (`bike_infra_demo.csv`, `tcl_stops_demo.csv`). Il suffit de les réimporter dans DuckDB pour rejouer le scénario.

## ⚙️ Étape 0 — Baseline stable

1. **Charger les CSV via l’UI Fred / Knowledge Flow**  
   - Ouvrir l’interface d’ingestion tabulaire.  
   - Importer `agentic_backend/academy/08_ecoadviser/data/bike_infra_demo.csv` et `agentic_backend/academy/08_ecoadviser/data/tcl_stops_demo.csv` dans la base DuckDB exposée par le serveur MCP tabulaire (mêmes noms de tables).  
   - (Optionnel) Importer également les autres jeux présents dans `agentic_backend/academy/08_ecoadviser/data/` si vous souhaitez enrichir la démonstration (consommations énergétiques par parcelle, temps de parcours voiture, temps de parcours modes doux, etc.).
   - Vérifier via l’outil “Lister les datasets” que les deux tables sont bien disponibles.
2. **Démarrer Knowledge Flow + Agentic Backend** puis sélectionner l’agent *EcoAdvisor*.
3. **Conduite attendue** : l’agent suit le pattern Tessa (reasoner → tools → reasoner) et produit un bilan CO₂ markdown avec :
   - un tableau comparant voiture / TCL / vélo,
   - des hypothèses explicites (distance, fréquence, facteurs),
   - 2–3 suggestions pour réduire l’empreinte.

Extrait attendu :

| Mode | CO₂ / semaine | Hypothèses |
| --- | --- | --- |
| Voiture | 19.2 kg | 10 km x 2 trajets x 5 j, 0.192 kg/km |
| TCL | 1.0 kg | même distance, 0.01 kg/km |
| Vélo | 0 kg | émission nulle |

**Hypothèses** : distance estimée via utilisateur, facteurs ADEME simplifiés.  
**Pistes bas carbone** : tester TCL les jours de pluie, mix vélo + TCL quand météo clémente.

---

## 🧠 Architecture actuelle

- Pattern Tessa “raisonneur ↔ outils” : un nœud `reasoner` (LLM gpt-4o) alterne avec le nœud `tools` (MCPRuntime) tant que `tools_condition` détecte des appels à effectuer.
- `EcoState` reste volontairement minimal (`messages`, `database_context`). Le contexte tabulaire est injecté dynamiquement dans le prompt pour éviter les hallucinations sur les noms de tables.
- Les outils disponibles sont : serveur tabulaire DuckDB (`bike_infra_demo`, `tcl_stops_demo`, autres jeux importés), service CO₂, service trafic Grand Lyon et service TCL temps réel.
- Le LLM orchestre les requêtes : il commence par découvrir les datasets, lance des requêtes DuckDB, puis compare les modes via `compare_trip_modes`, appelle le trafic/TCL quand c’est pertinent et formate la réponse Markdown.
- Les évolutions plus structurées (nœud `compute_co2`, champs supplémentaires dans l’état, météo, etc.) sont suivies dans `ROADMAP.md`.

👉 Pour une vue technique détaillée (diagramme, appels API), voir `TECH_DOC.md`.

---

## 🔌 Référentiel CO₂ (MCP `mcp-co2-service`)

- Lancer le serveur MCP de référence CO₂ situé dans `agentic_backend/academy/08_ecoadviser/co2_estimation_service/`:  
  ```bash
  uvicorn agentic_backend.academy.08_ecoadviser.co2_estimation_service.server_mcp:app \
      --host 127.0.0.1 --port 9798
  ```
- La configuration `mcp-co2-service` est déjà déclarée dans `config/configuration*.yaml`. Vérifier que le port correspond puis relancer l’Agentic Backend.
- Les tools exposés (`list_emission_modes`, `get_emission_factor`, `compare_trip_modes`, `reload_emission_cache`) retournent systématiquement la source, la date de mise à jour et un lien ADEME/SYTRAL.
- EcoAdvisor n’embarque plus les facteurs dans son prompt : il doit appeler ces tools et **citer la source** (`source`, `last_update`) dans sa réponse.
- En cas de panne du service, l’agent bascule automatiquement sur les facteurs de secours (car 0.192 kg/km, TCL 0.01 kg/km, vélo/marche 0 kg/km) et le mentionne clairement.

### 🌐 Nouveau : interrogation directe de l’API ADEME (Base Carbone)

Le service MCP interroge désormais `https://data.ademe.fr/data-fair/api/v1/datasets/base-carboner/lines` pour récupérer les facteurs d’émission à jour par mode de transport.

- Chaque appel à `reload_emission_cache` combine :
  1. Les facteurs embarqués (`DEFAULT_EMISSION_FACTORS`) pour garantir un fallback.
  2. Les éventuelles surcharges locales (JSON / HTTP).
  3. Les résultats live de l’API ADEME, en priorisant les modes principaux (voiture, bus, tram, métro, train, vélo, marche).
- Les champs fournis par ADEME (`Source`, `Date_de_modification`, `Unité_français`, `Commentaire_français`, etc.) sont injectés dans les réponses du tool pour être cités côté agent.
- Les paramètres de cette intégration sont configurables via variables d’environnement :

| Variable | Défaut | Description |
| --- | --- | --- |
| `ADEME_BASECARBONE_ENABLED` | `true` | Active/désactive les appels HTTP. |
| `ADEME_BASECARBONE_URL` | `https://data.ademe.fr/data-fair/api/v1/datasets/base-carboner` | Endpoint de base. |
| `ADEME_BASECARBONE_API_KEY` | _vide_ | Clé optionnelle si vous utilisez un compte authentifié. |
| `ADEME_BASECARBONE_TIMEOUT` | `8.0` | Timeout HTTP en secondes. |
| `ADEME_BASECARBONE_MAX_RESULTS` | `5` | Nombre de lignes ADEME inspectées par mode. |

⚠️ Si l’environnement n’autorise pas les appels réseau, `BaseCarboneClient` se désactive automatiquement et les facteurs statiques continuent d’être servis.


## 🚦 Trafic routier live (MCP `mcp-traffic-service`)

Nous exploitons maintenant l’API **WFS** du portail data.grandlyon.com pour récupérer en temps (quasi) réel les métriques de trafic (`pvo_patrimoine_voirie.pvotrafic`). Le service MCP `mcp-traffic-service` interroge cette API en fonction d’un bounding box construit à partir de l’origine/destination (lat/lon) et retourne les segments correspondants.

### Pré-requis
1. Créer un compte sur https://data.grandlyon.com et générer un **API key** ou un couple *login/mot de passe* permettant d’appeler les services WFS.
2. Renseigner les variables suivantes dans `agentic-backend/config/.env` :
   ```bash
   GRANDLYON_WFS_URL="https://data.grandlyon.com/geoserver/metropole-de-lyon/ows"
   GRANDLYON_WFS_TYPENAME="metropole-de-lyon:pvo_patrimoine_voirie.pvotrafic"
   GRANDLYON_WFS_API_KEY="votre_token"         # ou laisser vide si vous préférez l'authentification Basic
   GRANDLYON_WFS_USERNAME="votre_login"        # optionnel
   GRANDLYON_WFS_PASSWORD="votre_motdepasse"   # optionnel
   GRANDLYON_WFS_TIMEOUT="10"
   ```
   (Il suffit d’avoir soit un `API_KEY`, soit un couple `USERNAME/PASSWORD`. Redémarrer `./start.sh` après modification.)

### Utilisation
- Le tool MCP exposé est `get_live_traffic_segments`. Il prend des coordonnées (approximation lat/lon) pour l’origine et la destination, construit une bbox (avec une marge `buffer_deg`) et interroge le WFS.
- Les réponses contiennent les propriétés fournies par Grand Lyon (vitesse km/h, état du trafic, communes, etc.) ainsi qu’un aperçu des coordonnées.
- EcoAdvisor cite explicitement la provenance (“Grand Lyon WFS”) et s’appuie sur ces données pour recommander ou déconseiller l’usage de la voiture.

> Remarque : les fichiers CSV `data/temps-parcours-*.csv` restent dans le dépôt comme référence historique, mais ne sont plus utilisés par défaut.


## 🚌 Horaires TCL en quasi-temps réel (MCP `mcp-tcl-service`)

Pour afficher la fréquence réelle des bus/tram/métro TCL, un troisième service MCP (`mcp-tcl-service`) appelle l’API **RDATA** de Grand Lyon (`tcl_sytral.tclpassagesarret_2_0_0`). Il fonctionne comme suit :

1. **Créer un compte data.grandlyon.com** (si ce n’est pas déjà fait) et activer l’accès au jeu “Passages aux arrêts TCL”.
2. **Renseigner les credentials basiques** dans `agentic-backend/config/.env` :
   ```bash
   TCL_RDATA_USERNAME="mon.identifiant"
   TCL_RDATA_PASSWORD="monMotDePasseComplexe"
   TCL_RDATA_URL="https://data.grandlyon.com/fr/datapusher/ws/rdata"
   TCL_RDATA_DATASET="tcl_sytral.tclpassagesarret_2_0_0"  # adaptez avec le slug indiqué dans la fiche dataset
   # ou définissez directement TCL_RDATA_ENDPOINT="https://data.grandlyon.com/.../tcl_sytral.tclpassagesarret_2_0_0/all.json"
   # → EcoAdvisor dérive automatiquement les variantes .json / all.json nécessaires
   TCL_RDATA_TIMEOUT="10"
   ```
   (Ces identifiants peuvent être les mêmes que ceux utilisés pour le WFS.)
3. Relancer `./start.sh`. Le service écoute sur `127.0.0.1:9800/mcp`.
4. L’agent appelle `get_tcl_realtime_passages` avec `stop_code` (identifiant d’arrêt) et, éventuellement, la ligne. Les identifiants sont disponibles dans les tables importées (`tcl_stops_demo.csv`…).

Les réponses contiennent la ligne, la destination, l’heure de passage, l’indication temps réel (si disponible) et toutes les métadonnées brutes fournies par le flux RDATA.
Si la version `tclpassagesarret_2_0_0` n’est pas encore publiée sur votre compte Grand Lyon, le service MCP bascule automatiquement sur le dataset historique `tclpassagearret`.

## 📏 Distances géocodées & routées (MCP `mcp-geo-service`)

Lorsque l’utilisateur ne fournit qu’une adresse (“Rue Garibaldi à Villeurbanne → Place Bellecour”), EcoAdvisor s’appuie désormais sur un quatrième service MCP qui combine **Nominatim** (géocodage) et **OSRM** (distance/temps de trajet).

- Lancer le serveur MCP :
  ```bash
  uvicorn agentic_backend.academy.08_ecoadviser.geo_distance_service.server_mcp:app \
      --host 127.0.0.1 --port 9801
  ```
- Tools exposés :
  - `geocode_location` : renvoie plusieurs correspondances (lat/lon, place_id…) pour une requête texte.
  - `compute_trip_distance` : calcule la distance/temps entre deux coordonnées (OSRM ou fallback haversine).
  - `estimate_trip_between_addresses` : chaîne complète `query → géocode → distance`, prête à l’emploi depuis EcoAdvisor.
- Variables d’environnement principales :

| Variable | Défaut | Description |
| --- | --- | --- |
| `ECO_GEO_NOMINATIM_URL` | `https://nominatim.openstreetmap.org/search` | Endpoint Nominatim (remplaçable par une instance privée). |
| `ECO_GEO_OSRM_URL` | `https://router.project-osrm.org` | Endpoint OSRM public (vous pouvez pointer vers un OSRM on-prem). |
| `ECO_GEO_USER_AGENT` | `FredEcoAdvisorGeo/1.0 ...` | User-Agent envoyé aux deux API (important pour Nominatim). |
| `ECO_GEO_DEFAULT_COUNTRIES` | `fr` | Codes pays appliqués par défaut si l’utilisateur ne précise rien. |
| `ECO_GEO_DEFAULT_CITY_SUFFIX` | `Lyon, France` | Suffixe ajouté automatiquement lorsque la requête ne contient pas déjà un mot-clé de ville. |
| `ECO_GEO_GEOCODING_ENABLED` / `ECO_GEO_ROUTING_ENABLED` | `true` | Permettent de désactiver temporairement Nominatim ou OSRM (fallback haversine activé si OSRM indisponible). |

Nominatim impose des limites strictes : utilisez un User-Agent explicite et, si possible, basculez sur une instance dédiée pour une démo publique. OSRM fournit les distances routières pour les profils `driving`, `cycling`, `walking` (alias acceptés : `car`, `vélo`, `marche`…). En cas d’erreur ou de time-out OSRM, le service renvoie au moins une distance géodésique avec une note “fallback”.

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

# 🛠 Préparation des CSV “démo-ready”

Fichier à générer : `prepare_rhone_demo_tables.py`

Sortie :

- `data/bike_infra_demo.csv`
- `data/tcl_stops_demo.csv`
- `data/consommations-energetiques-2020-a-parcelle-territoire-metropole-lyon.csv`
- `data/temps-parcours-automobile-metropole-lyon.csv`
- `data/temps-parcours-modes-doux-metropole-lyon.csv`

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

## 🎛 Architecture LangGraph (implémentation actuelle)

1. **Node 1 — `reasoner` (LLM gpt-4o)**  
   - récupère le prompt système tunable, ajoute le contexte tabulaire (via `get_context`) et l’historique utilisateur ;  
   - décide quand appeler un tool MCP (listage des datasets, requêtes DuckDB, comparaison CO₂, trafic, TCL).

2. **Node 2 — `tools` (MCPRuntime)**  
   - exécute réellement les tools exposés par les serveurs MCP (`mcp-knowledge-flow-mcp-tabular`, `mcp-co2-service`, `mcp-traffic-service`, `mcp-tcl-service`, `mcp-geo-service`) et renvoie les `ToolMessage` au LLM.

3. **Boucle contrôlée par `tools_condition`**  
   - tant que le LLM a besoin d’un outil supplémentaire, on reboucle `reasoner → tools → reasoner`;  
   - lorsque le LLM estime que tout est prêt, il produit la réponse finale en Markdown avec tableau CO₂ et équivalences.

ℹ️ Les prochains jalons (ajout d’un nœud `compute_co2`, météo, scoring enrichi…) sont détaillés dans `ROADMAP.md`.

---

# 🧪 Exemple utilisateur

> “J’habite Villeurbanne Rue Masséna, je vais à Gerland.  
> 10 km en voiture matin et soir.  
> Quel est mon impact CO₂ et quelles alternatives bas carbone existent ?”

---

# 🚧 Aller plus loin

- `ROADMAP.md` décrit les prochaines itérations (nœud `compute_co2`, météo, scoring avancé, UI enrichie).  
- `TECH_DOC.md` résume le fonctionnement global de l’agent (modèle, outils, APIs) pour vos interlocuteurs métiers.

---
