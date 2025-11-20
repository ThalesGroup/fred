# Sécurisation du paramètre `actif` dans le serveur MCP

## Problème identifié

Dans la version précédente du serveur MCP, le paramètre `actif` présentait une vulnérabilité :

1. **Documentation ambiguë** : Le paramètre était documenté avec `"true or false"` en minuscules, encourageant les LLMs à envoyer des chaînes
2. **Transmission directe** : La valeur reçue était transmise directement au client Geosecur sans validation
3. **Risque de type mismatch** : Possibilité de recevoir des chaînes `"true"`/`"false"` au lieu de booléens Python

## Améliorations apportées

### 1. **Normalisation robuste des valeurs**

Ajout d'une fonction `normalize_boolean()` qui :
- Accepte les booléens Python (`True`/`False`)
- Accepte les chaînes `"true"`/`"false"` (toutes casses)
- Gère les espaces autour des chaînes (`"  true  "`)
- Rejette toutes les autres valeurs avec des messages d'erreur clairs

```python
def normalize_boolean(value):
    """Convert string 'true'/'false' to boolean, handle existing booleans."""
    if isinstance(value, bool):
        return value
    elif isinstance(value, str):
        normalized_str = value.strip().lower()
        if normalized_str == "true":
            return True
        elif normalized_str == "false":
            return False
        else:
            raise ValueError(f"Invalid boolean string: {value}. Expected 'true' or 'false'")
    else:
        raise TypeError(f"actif must be boolean or string, got {type(value)}")
```

### 2. **Documentation améliorée**

```python
actif: Filter by asset status - True for active assets, False for inactive assets (default: True)
        Accepts boolean True/False or string "true"/"false"
```

### 3. **Validation d'entrée**

- Validation avant transmission au client Geosecur
- Gestion d'erreur avec messages explicites
- Retour d'erreur structuré au client MCP

```python
try:
    actif_normalized = normalize_boolean(actif)
except (ValueError, TypeError) as e:
    return {"success": False, "error": f"Invalid actif parameter: {str(e)}"}
```

## Tests de sécurité

### ✅ **Valeurs acceptées**
- `True`, `False` (booléens Python)
- `"true"`, `"false"`, `"TRUE"`, `"FALSE"`, `"True"`, `"False"` (chaînes)
- `"  true  "`, `"  FALSE  "` (avec espaces)

### ❌ **Valeurs rejetées en sécurité**
- Tentatives d'injection SQL : `"'; DROP TABLE assets; --"`
- Tentatives d'injection de commande : `"true; DELETE * FROM assets"`
- Tentatives XSS : `"<script>alert('xss')</script>"`
- Caractères spéciaux : null bytes, newlines, Unicode malveillants
- Types incorrects : entiers, listes, dictionnaires, None
- Autres représentations booléennes : `"1"`, `"0"`, `"yes"`, `"no"`, `"on"`, `"off"`

## Avantages de cette approche

### 🛡️ **Sécurité**
- Protection contre l'injection de code malveillant
- Validation stricte des types et valeurs
- Gestion d'erreur contrôlée

### 🔄 **Compatibilité**
- Maintien de la compatibilité avec les booléens Python existants
- Support des chaînes envoyées par les LLMs
- Tolérance aux variations de casse et espaces

### 📝 **Maintenabilité**
- Code plus robuste et prévisible
- Messages d'erreur explicites pour le débogage
- Tests de sécurité automatisés

### 🤖 **Facilité d'usage pour les LLMs**
- Accepte naturellement les formats que les LLMs pourraient envoyer
- Documentation claire sur les formats acceptés
- Gestion gracieuse des erreurs

## Exemple d'usage

```python
# Tous ces appels fonctionnent maintenant :
await search_assets(actif=True)           # Boolean Python
await search_assets(actif="true")         # String lowercase  
await search_assets(actif="TRUE")         # String uppercase
await search_assets(actif="  false  ")    # String avec espaces

# Ces appels sont sécurisés et rejetés :
await search_assets(actif="maybe")        # Erreur claire
await search_assets(actif=123)            # Erreur de type
await search_assets(actif="<script>")     # Tentative d'injection rejetée
```

## Impact

Cette sécurisation **élimine complètement** le risque de transmission de valeurs non-validées au client Geosecur, tout en améliorant l'expérience utilisateur et la robustesse du système.