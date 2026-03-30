# Protocole de Validation - SQL Agent V2

Ce document définit le protocole de test pour valider la montée en compétence de l'agent SQL V2 par rapport à la V1.
Il est basé sur le jeu de données de démonstration (Ports, Radars, Ship Tracks).

## Données de Référence (Ground Truth)

Les réponses attendues sont calculées sur la base des fichiers suivants :
- `Port_preview.csv` (8 ports)
- `Radar_Sites_preview.csv` (5 radars)
- `ship_tracks_demo.csv` (60 points de trace, 12 navires uniques)

## Scénarios de Test

| ID | Niveau | Question Utilisateur | Intention (Routeur) | SQL Attendu (Motif) | Réponse Attendue (Vérité Terrain) |
|:---|:---|:---|:---|:---|:---|
| **1** | **Routing** | "Quelles sont les colonnes de la table des radars ?" | `show_metadata` | *Aucun* | Liste : `radar_id`, `name`, `site_class`, `elevation_m`... (sans halluciner). |
| **2** | **Routing** | "Bonjour, qui es-tu ?" | `show_metadata` | *Aucun* | Présentation polie, pas de SQL. |
| **3** | **Simple** | "Combien y a-t-il de ports dans la base ?" | `query_data` | `SELECT count(*) ...` | **8** ports. |
| **4** | **Simple** | "Donne-moi la liste des ports militaires." | `query_data` | `WHERE port_type = 'military'` | **3** ports : Toulon, Brest, Cherbourg. |
| **5** | **Analytique** | "Quel est le radar qui a la plus grande portée (nominal_range) ?" | `query_data` | `ORDER BY ... DESC LIMIT 1` | **Pointe Saint-Mathieu** (RAD-BRE) avec **500 km**. |
| **6** | **Analytique** | "Quel est le navire le plus rapide enregistré dans les traces ?" | `query_data` | `ORDER BY sog_knots DESC LIMIT 1` | **ES Reina** (23.2 noeuds à 12:50). |
| **7** | **Logique** | "Combien de navires uniques sont suivis ?" | `query_data` | `DISTINCT ship_id` | **12** navires uniques. |
| **8** | **Complexe** | "Trouve-moi les navires qui ont une anomalie de fréquence." | `query_data` | `LIKE '%freq%'` | **2** navires (à 12:30) : **MV Costa Brava** et **MV Atlantique**. |
| **9** | **Robustesse** | "Liste les aéroports disponibles." | `query_data` | *N/A* | L'agent doit dire qu'il ne trouve pas de table correspondante (pas d'hallucination). |

## Guide d'interprétation

1.  **Test 7 (DISTINCT)** : Critique pour valider que l'agent comprend la structure temporelle (plusieurs lignes par navire). Si réponse = 60, échec.
2.  **Test 8 (Filtre Flou)** : Vérifie la capacité à chercher dans des colonnes textuelles (ex: `anomaly_hint`).
3.  **Test 1 (Metadata)** : Valide le fix du `analyze_intent_step` (injection du schéma dans le prompt système du routeur).

## Tests Avancés (Temporel)

*   **Question :** "Quelle était la position du FS Surcouf à 12h30 ?"
*   **SQL Attendu :** `WHERE ship_name LIKE '%Surcouf%' AND timestamp_iso LIKE '%12:30%'`
*   **Réponse :** Latitude 48.614, Longitude -3.986.