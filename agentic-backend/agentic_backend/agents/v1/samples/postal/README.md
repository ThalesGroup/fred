# Démo LaPoste (Agent custom) — scénario de test

## Objectif métier (version courte)

Cette démo montre un **copilote métier logistique** capable de :

- diagnostiquer un retard colis en orchestrant **2 serveurs MCP** (métier + IoT),
- afficher une **carte géographique** (hub, véhicule, route, points relais),
- demander une **validation humaine (HITL)** avant une action impactante (reroutage / replanification),
- puis répondre à des **questions de suivi** de façon plus naturelle (sans relancer systématiquement un nouveau scénario).

## Ce que je veux observer

- 1er tour : diagnostic + carte + carte HITL (choix action)
- Choix HITL : reroutage vers **Bastille Relay**
- 2e tour (follow-up) : résumé du tracking + état IoT + position véhicule
- **Sans** redéclencher un nouveau scénario ni une nouvelle carte HITL

## Pré-requis (avant la démo)

- Serveur MCP postal démarré (`9797`)
- Serveur MCP IoT démarré (`9798`)
- Backend agentic redémarré après patch
- Frontend Fred ouvert
- Agent sélectionné : **LaPosteDemo**

## Script de démo (questions à enchaîner)

### 1. Lancement du scénario (diagnostic + carte + HITL)

**Question**
Mon colis est en retard. Peux-tu diagnostiquer la situation, me montrer où il est sur la carte, puis me proposer un reroutage vers un point relais si c’est pertinent ?

**Attendu**

- L’agent seed un scénario de démo (si pas de tracking_id fourni)
- Il appelle les tools métier + IoT
- Il affiche un diagnostic
- Il affiche la carte (hub / véhicule / route / points relais)
- Il ouvre une carte HITL avec les choix (relais / replanification / ne rien faire)

### 2. Action humaine (HITL)

**Choix dans la carte HITL**

- Sélectionner **Bastille Relay** (souvent `PP-PAR-002`)
- ou saisir en texte libre : `Reroute vers PP-PAR-002`

**Attendu**

- Exécution du reroutage
- Notification client (SMS) simulée
- Réponse finale + carte mise à jour (point relais choisi mis en évidence)

### 3. Follow-up conversationnel (test du mode hybride)

**Question**
Parfait. Rappelle-moi le tracking_id et résume l’état IoT (phase, congestion hub, position véhicule).

**Attendu**

- L’agent **réutilise le même contexte colis**
- Il rafraîchit les données (track + snapshot IoT)
- Il répond avec un résumé (tracking_id, phase, congestion, véhicule, position)
- Il peut réafficher la carte
- **Pas de nouvelle carte HITL**
- **Pas de redémarrage complet du scénario**

### 4. Follow-up optionnel (validation de continuité)

**Question**
Peux-tu aussi me rappeler le statut métier actuel et les 2 meilleurs points relais encore disponibles ?

**Attendu**

- Réponse de suivi (lecture seule)
- Pas de HITL
- Pas de reseed

## Variante de démo (si je veux montrer une autre branche)

Au lieu de Bastille Relay à l’étape 2 :

- choisir **Replanifier domicile (demain après-midi)**

Puis poser la même question de follow-up (étape 3) pour montrer que le mode conversationnel marche aussi après une autre action.

## Notes de présentation (oral)

- “Ici, la partie action métier reste déterministe et sécurisée (HITL).”
- “La partie follow-up devient plus naturelle grâce à un usage ciblé du LLM (résumé / routage d’intention).”
- “La carte est un rendu structuré (`GeoPart`) et non une hallucination texte.”
