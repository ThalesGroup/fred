# Exemple minimal de serveur MCP (Python)

Ce dossier contient un exemple très simple d’un serveur MCP prêt à l’emploi, destiné à être utilisé par un agent (par exemple dans Fred). Il expose un transport HTTP « Streamable » au chemin `/mcp` et déclare quelques outils démonstratifs.

Points d’entrée principaux :

- Code du serveur : `postal_service_mcp_server/server_mcp.py`
- Lancement local : `make server`

---

## MCP en 3 minutes

Le Model Context Protocol (MCP) standardise la façon dont des « serveurs de capacités » exposent des outils, ressources, prompts, etc., à des agents IA.

- Protocole : échanges JSON‑RPC 2.0 au-dessus d’un transport (ici HTTP + SSE pour la diffusion d’événements).
- Transport HTTP « Streamable » : un endpoint unique (par défaut `/mcp`) gère à la fois les requêtes POST JSON‑RPC et un flux SSE GET pour les événements/notifications.
- Session : le client initialise une session (handshake), puis invoque des méthodes (ex. exécuter un outil) et reçoit les résultats/events.
- Outils (tools) : fonctions déclarées par le serveur, typées, que le client peut appeler de manière structurée.
- Clients : agents (Fred, LangChain, etc.) qui parlent MCP et savent consommer les endpoints.

Dans cet exemple, on utilise l’API « FastMCP » du SDK officiel `mcp`, qui simplifie l’écriture des outils via un décorateur `@server.tool()` et expose directement une application ASGI à brancher sur Uvicorn.

---

## Exemple fourni

Le serveur d’exemple se trouve dans `postal_service_mcp_server/server_mcp.py` et fait trois choses :

- Crée un serveur MCP avec `FastMCP` et expose l’app via `app = server.streamable_http_app()` (endpoint `/mcp`).
- Déclare quatre outils pédagogiques :
  - `validate_address(country, city, postal_code, street)` : valide/normalise une adresse et renvoie un `address_id`.
  - `quote_shipping(weight_kg, distance_km, speed)` : calcule un prix/ETA.
  - `create_label(receiver_name, address_id, service)` : crée une étiquette + `tracking_id`.
  - `track_package(tracking_id)` : renvoie l’état/historique d’un colis.
- Stocke les données en mémoire (dictionnaires Python) pour rester simple.

Fichier à lire : `postal_service_mcp_server/server_mcp.py`

---

## Prérequis

- Python 3.12+ (un environnement virtuel sera créé par le Makefile)
- `make`
- Port `9797` libre sur `127.0.0.1`

---

## Installation et lancement

La commande ci‑dessous crée un venv, installe les dépendances (`mcp[fastapi]`, `uvicorn`, `fastapi`) et lance le serveur :

```bash
make server
```

Équivalent manuel :

```bash
python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install "mcp[fastapi]" fastapi uvicorn
uvicorn postal_service_mcp_server.server_mcp:app --host 127.0.0.1 --port 9797 --reload
```

Endpoint exposé : `http://127.0.0.1:9797/mcp`

Remarque : c’est un endpoint « machine » (MCP). Ouvrir l’URL dans un navigateur ne produit pas de page lisible ; il est prévu pour des clients MCP.

---

## Utilisation avec Fred

- Le fichier `configuration_academy.yaml` est déjà configuré pour référencer l’endpoint MCP local `http://127.0.0.1:9797/mcp`.
- Étapes typiques :
  1. Démarrer ce serveur avec `make server`.
  2. Dans Fred, créer un agent et lui rattacher ce serveur MCP (la config pointe déjà sur l’endpoint).
  3. Converser avec l’agent : demandez‑lui de valider une adresse, chiffrer un envoi, puis créer une étiquette, etc. L’agent appellera les outils MCP correspondants.

Exemples d’invites utiles côté agent :

- « Valide l’adresse suivante et donne‑moi l’`address_id`… »
- « Fais un devis d’expédition pour 2.5 kg sur 750 km en express. »
- « Crée l’étiquette pour l’adresse X au nom de Y en express, puis donne‑moi le `tracking_id`. »
- « Suis le colis `PKG-…` et résume l’historique. »

---

## Ajouter vos propres outils

Pour créer un nouvel outil :

1. Ouvrez `postal_service_mcp_server/server_mcp.py`.
2. Ajoutez une fonction Python tapée, et décorez‑la avec `@server.tool()`.
3. Redémarrez le serveur.

Exemple rapide :

```python
@server.tool()
async def hello(name: str) -> dict[str, str]:
    return {"message": f"Hello {name}!"}
```

Conseils :

- Tapez clairement les paramètres/retours ; FastMCP s’en sert pour générer la spécification du tool.
- Gardez les effets de bord (I/O, réseau) explicites et gérés dans la fonction outil.

---

## Dépannage

- « ImportError: No module named 'mcp.server.fastapi' »
  - Les versions récentes du SDK `mcp` n’exportent plus ce module. L’exemple actuel utilise `FastMCP` et `server.streamable_http_app()` (voir `postal_service_mcp_server/server_mcp.py`).
  - Si vous avez un ancien venv, faites : `make clean && make server`.

- « Address already in use »
  - Le port `9797` est occupé. Changez‑le dans le `Makefile` ou passez `--port` à Uvicorn.

---

Bon hack ! 
