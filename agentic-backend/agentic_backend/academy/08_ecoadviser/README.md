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

---

## 🧱 Étape 3 — Trafic routier live (Grand Lyon WFS)

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

## 🎛 Architecture LangGraph (version simple)

1. **Node 1 — Input utilisateur**

   - distance
   - adresse
   - mode de transport actuel

2. **Node 2 — Tabular lookup**

   - interroger `data/bike_infra_demo.csv`
   - interroger `data/tcl_stops_demo.csv`
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
