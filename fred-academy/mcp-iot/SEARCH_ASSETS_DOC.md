# Documentation de l'outil search_assets

## Vue d'ensemble

L'outil `search_assets` permet de rechercher et filtrer les données de la collection `assets` dans la base de données Kuzzle v2. Il utilise l'API géosecur pour accéder aux données des actifs (véhicules, équipements) avec leurs métadonnées et mesures de position.

## Structure des données

Les données suivent le mapping défini dans `assets.json` avec la structure suivante :

```json
{
  "_id": "Semi-428RNK75",
  "_source": {
    "model": "Semi",
    "reference": "428RNK75",
    "metadata": {
      "designation": "428RNK75",
      "codeInventaire": "L115713946000066",
      "platformId": "IDF NORD PFC",
      "owner": "laposte",
      "actif": false,
      "geofencing": {"disabled": true}
    },
    "measures": {
      "positionSpeed": {
        "values": {
          "position": {"lon": 2.4834, "lat": 49.0065},
          "speed": 0,
          "bearing": 0
        },
        "measuredAt": 1715925913000
      }
    },
    "_kuzzle_info": {
      "createdAt": 1667325047125,
      "updatedAt": 1716882183682
    }
  }
}
```

## Paramètres disponibles

| Paramètre | Type | Description | Exemple |
|-----------|------|-------------|---------|
| `query` | Dict | Requête Elasticsearch DSL personnalisée | `{"bool": {"must": [{"term": {"model": "Semi"}}]}}` |
| `model` | str | Filtrer par modèle d'actif | `"Semi"`, `"Camion"` |
| `designation` | str | Filtrer par désignation | `"428RNK75"` |
| `created_after` | str | Documents créés après cette date | `"2024-01-01T00:00:00Z"` ou timestamp |
| `created_before` | str | Documents créés avant cette date | `"2024-12-31T23:59:59Z"` ou timestamp |
| `measured_after` | str | Mesures de position après cette date | `"2024-01-01T00:00:00Z"` ou timestamp |
| `measured_before` | str | Mesures de position avant cette date | `"2024-12-31T23:59:59Z"` ou timestamp |
| `size` | int | Nombre de résultats (défaut: 100, max: 10000) | `50` |
| `from_` | int | Décalage pour la pagination (défaut: 0) | `100` |

## Exemples d'utilisation

### 1. Recherche basique
```json
{
  "size": 10
}
```

### 2. Filtrer par modèle
```json
{
  "model": "Semi",
  "size": 5
}
```

### 3. Filtrer par désignation
```json
{
  "designation": "428RNK75"
}
```

### 4. Filtrer par date de création
```json
{
  "created_after": "2024-01-01T00:00:00Z",
  "created_before": "2024-12-31T23:59:59Z",
  "size": 20
}
```

### 5. Filtrer par date de mesure de position
```json
{
  "measured_after": "2024-11-01T00:00:00Z",
  "size": 15
}
```

### 6. Requête Elasticsearch personnalisée
```json
{
  "query": {
    "bool": {
      "must": [
        {"term": {"metadata.actif": true}},
        {"exists": {"field": "measures.positionSpeed.values.position"}},
        {"range": {"measures.positionSpeed.measuredAt": {"gte": "2024-01-01T00:00:00Z"}}}
      ]
    }
  },
  "size": 25
}
```

### 7. Recherche d'actifs avec géofencing activé
```json
{
  "query": {
    "bool": {
      "must": [
        {"term": {"metadata.geofencing.disabled": false}}
      ]
    }
  }
}
```

### 8. Pagination
```json
{
  "model": "Semi",
  "size": 50,
  "from_": 100
}
```

## Format de réponse

```json
{
  "success": true,
  "data": {
    "action": "search",
    "collection": "assets",
    "result": {
      "hits": [
        {
          "_id": "Semi-428RNK75",
          "_source": { /* données de l'actif */ },
          "_score": 1.0
        }
      ],
      "total": 1977
    }
  }
}
```

## Gestion des erreurs

L'outil gère plusieurs types d'erreurs :

- **Taille invalide** : `size > 10000` ou `from_ < 0`
- **Erreurs d'authentification** : Token JWT invalide ou expiré
- **Erreurs de connexion** : Problèmes réseau avec l'API
- **Erreurs de format** : Dates mal formatées dans les filtres

Exemple de réponse d'erreur :
```json
{
  "success": false,
  "error": "Size parameter cannot exceed 10000 results"
}
```

## Notes techniques

- **Authentification** : Utilise automatiquement l'authentification JWT via `GeosecurClient`
- **Variables d'environnement** : `GEOSECUR_USERNAME` et `GEOSECUR_PASSWORD` (défaut: geosecur-admin/pass)
- **Cache des tokens** : Les tokens JWT sont mis en cache et renouvelés automatiquement
- **Index Kuzzle** : `tenant-geosecur-laposte`
- **Collection** : `assets`

## Cas d'usage typiques

1. **Suivi de flotte** : Rechercher tous les véhicules actifs avec leur dernière position
2. **Audit** : Lister les actifs créés/modifiés dans une période donnée
3. **Géolocalisation** : Trouver les actifs dans une zone géographique (via requêtes géo Elasticsearch)
4. **Maintenance** : Identifier les actifs sans mesures récentes
5. **Inventaire** : Rechercher par codes d'inventaire ou désignations spécifiques