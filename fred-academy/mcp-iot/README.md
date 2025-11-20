# Postal Service MCP Server

Serveur MCP (Model Context Protocol) pour les services postaux avec outil de gestion de maintenance.

## Outils disponibles

### 1. Outils postaux existants
- `validate_address()` - Validation et enregistrement d'adresse
- `quote_shipping()` - Devis d'expédition
- `create_label()` - Création d'étiquette d'expédition
- `track_package()` - Suivi de colis

### 2. Outils de gestion de maintenance et actifs
- `get_maintenance_events()` - Récupération des événements de maintenance
- `search_assets()` - Recherche et filtrage d'actifs dans la collection Kuzzle

## Outil de Recherche d'Actifs (Assets)

L'outil `search_assets` permet d'interroger la collection `assets` de Kuzzle v2 pour récupérer et filtrer les données d'actifs (véhicules, équipements) avec leurs métadonnées et mesures de position.

### Fonctionnalités principales

- **Filtrage par modèle** : Rechercher par type d'actif (Semi, Camion, etc.)
- **Filtrage par désignation** : Rechercher par identifiant spécifique  
- **Filtrage temporel** : Par date de création ou de mesure de position
- **Requêtes personnalisées** : Support des requêtes Elasticsearch DSL complètes
- **Pagination** : Gestion des résultats volumineux
- **Authentification automatique** : Via JWT avec cache intelligent

### Paramètres disponibles

| Paramètre | Type | Description | Exemple |
|-----------|------|-------------|---------|
| `query` | Dict | Requête Elasticsearch DSL personnalisée | `{"bool": {"must": [{"term": {"model": "Semi"}}]}}` |
| `model` | str | Filtrer par modèle d'actif | `"Semi"`, `"Camion"` |
| `designation` | str | Filtrer par désignation | `"428RNK75"` |
| `created_after` | str | Documents créés après cette date | `"2024-01-01T00:00:00Z"` |
| `created_before` | str | Documents créés avant cette date | `"2024-12-31T23:59:59Z"` |
| `measured_after` | str | Mesures après cette date | `"2024-01-01T00:00:00Z"` |
| `measured_before` | str | Mesures avant cette date | `"2024-12-31T23:59:59Z"` |
| `size` | int | Nombre de résultats (défaut: 100, max: 10000) | `50` |
| `from_` | int | Décalage pour pagination (défaut: 0) | `100` |

### Exemples d'utilisation

#### 1. Recherche par modèle
```python
result = await search_assets(model="Semi", size=10)
```

#### 2. Filtrage par date de création
```python
result = await search_assets(
    created_after="2024-01-01T00:00:00Z",
    created_before="2024-12-31T23:59:59Z"
)
```

#### 3. Requête personnalisée (actifs actifs avec position)
```python
result = await search_assets(
    query={
        "bool": {
            "must": [
                {"term": {"metadata.actif": True}},
                {"exists": {"field": "measures.positionSpeed.values.position"}}
            ]
        }
    }
)
```

### Structure des données retournées

Les résultats incluent :
- **Métadonnées** : modèle, référence, désignation, propriétaire, statut actif
- **Mesures de position** : latitude, longitude, vitesse, cap, timestamp
- **Informations système** : dates de création/modification Kuzzle
- **Événements** : historique des événements géofencing
- **Appareils liés** : équipements associés à l'actif

Voir `SEARCH_ASSETS_DOC.md` pour la documentation complète avec exemples détaillés.

## Outil de Gestion de Maintenance

L'outil `get_maintenance_events` permet d'interroger l'API de gestion de maintenance décrite dans `openapi/gestionmaintenance.json`.

### Paramètres

| Paramètre       | Type   | Obligatoire | Description                                             |
| --------------- | ------ | ----------- | ------------------------------------------------------- |
| `api_url`       | string | ✅           | URL de base de l'API (ex: "https://api.example.com")    |
| `engine_id`     | string | ✅           | ID du tenant (ex: "tenant-geosecur-laposte")            |
| `start_at`      | string | ✅           | Date de début au format français (dd-mm-yyyy hh:mm:ss)  |
| `end_at`        | string | ❌           | Date de fin (optionnel, par défaut +24h)                |
| `timezone`      | string | ❌           | Fuseau horaire (défaut: "Europe/Paris")                 |
| `size`          | int    | ❌           | Nombre de résultats (défaut: 100)                       |
| `format_type`   | string | ❌           | Format de sortie: "json", "csv", "xml" (défaut: "json") |
| `csv_separator` | string | ❌           | Séparateur CSV: "," ou ";" (défaut: ",")                |

### Exemples d'utilisation

#### 1. Récupération basique en JSON
```python
result = await get_maintenance_events(
    api_url="https://api.monserveur.com",
    engine_id="tenant-geosecur-laposte",
    start_at="23-10-2023 00:00:00",
    end_at="24-10-2023 00:00:00"
)
```

#### 2. Export CSV avec séparateur personnalisé
```python
result = await get_maintenance_events(
    api_url="https://api.monserveur.com",
    engine_id="tenant-geosecur-laposte",
    start_at="23-10-2023 00:00:00",
    format_type="csv",
    csv_separator=";"
)
```

#### 3. Export XML avec plus de résultats
```python
result = await get_maintenance_events(
    api_url="https://api.monserveur.com",
    engine_id="tenant-geosecur-laposte",
    start_at="01-11-2023 00:00:00",
    size=500,
    format_type="xml"
)
```

### Structure de la réponse

#### Succès
```python
{
    "success": True,
    "status_code": 200,
    "data": [...],  # Données selon le format demandé
    "content_type": "application/json"
}
```

#### Erreur
```python
{
    "success": False,
    "status_code": 400,  # Code d'erreur HTTP (optionnel)
    "error": "Message d'erreur détaillé"
}
```

### Architecture

L'implémentation suit le principe de séparation des responsabilités :

1. **`call_maintenance_api()`** - Fonction isolée pour les appels REST
   - Gère les requêtes HTTP
   - Traite les différents formats de réponse
   - Gère les erreurs de réseau

2. **`get_maintenance_events()`** - Outil MCP
   - Valide les paramètres d'entrée
   - Appelle la fonction d'API REST
   - Formate la réponse pour MCP

## Installation et démarrage

```bash
# Installation des dépendances
make install

# Démarrage du serveur
make run

# Test des exemples
.venv/bin/python example_maintenance_usage.py
.venv/bin/python example_search_assets_mcp.py
```

Le serveur sera accessible sur `http://127.0.0.1:9797/mcp`

## Dépendances ajoutées

- `aiohttp` - Pour les appels HTTP asynchrones
- `datetime` - Pour la validation des formats de date

## API de maintenance

L'API suit la spécification OpenAPI définie dans `openapi/gestionmaintenance.json` :

- **Endpoint** : `POST /_/gestionmaintenance/getMaintenanceEvents`
- **Authentification** : Via paramètre `engineId`
- **Formats supportés** : JSON, CSV, XML
- **Timezone** : Support des fuseaux horaires configurables