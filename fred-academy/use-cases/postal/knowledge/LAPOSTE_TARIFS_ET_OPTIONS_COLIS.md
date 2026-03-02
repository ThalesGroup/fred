# Guide de Demonstration RAG - Tarifs et Options Colis (Style La Poste)

> Document de demonstration (fictif) pour illustrer un corpus RAG "tarification + choix de service".
> Objectif: permettre a un agent de comparer des options d'envoi et recommander un service.

## 1. Objet du document

Ce document decrit:

- des offres colis (demo)
- des regles de choix selon poids / delai / valeur
- des fourchettes tarifaires simplifiees
- des options additionnelles (signature, assurance, pickup)
- des exemples de recommandation

Il est concu pour des questions du type:

- "Quel service choisir pour un colis de 1,8 kg ?"
- "Quelle difference entre standard et express ?"
- "Quand recommander la signature ?"
- "Quel cout approximatif avec assurance ?"

## 2. Hypotheses de la demo

- Les tarifs ci-dessous sont fictifs (non contractuels)
- Le document sert a illustrer le raisonnement d'un agent RAG
- Les montants sont des fourchettes pedagogiques

## 3. Catalogue de services colis (demo)

### 3.1 Services principaux

| Code service | Nom commercial (demo) | Delai indicatif | Suivi | Signature | Reroutage pickup | Usage typique |
|---|---|---|---|---|---|---|
| `standard` | Colis Standard | 3 a 5 jours | Oui | Option | Oui | Envois courants non urgents |
| `express` | Colis Express | 1 a 2 jours | Oui | Option | Oui | Envois urgents ou sensibles |
| `eco_relay` | Colis Eco Relais | 3 a 6 jours | Oui | Non | N/A (deja pickup) | Budget / retrait en point |

### 3.2 Options additionnelles (demo)

| Option | Code | Description | Quand la proposer |
|---|---|---|---|
| Signature a la livraison | `signature` | Remise contre signature | Valeur elevee, besoin de preuve |
| Assurance complementaire | `insurance_plus` | Couverture additionnelle | Objet de valeur / fragile |
| Notification proactive | `notify` | SMS ou email de suivi actionnable | Toujours recommande en support |
| Reroutage pickup | `pickup_reroute` | Livraison redirigee vers point retrait | Client absent / besoin de flexibilite |

## 4. Grille tarifaire simplifiee (France metropolitaine, demo)

### 4.1 Tarifs de base par tranche de poids

#### Service standard

| Tranche de poids | Tarif de base (EUR) | Delai indicatif |
|---|---:|---|
| 0 a 0,5 kg | 4,90 | 3 a 5 jours |
| 0,5 a 1 kg | 6,20 | 3 a 5 jours |
| 1 a 2 kg | 7,90 | 3 a 5 jours |
| 2 a 5 kg | 10,90 | 3 a 5 jours |
| 5 a 10 kg | 15,90 | 3 a 5 jours |
| 10 a 20 kg | 22,50 | 3 a 5 jours |

#### Service express

| Tranche de poids | Tarif de base (EUR) | Delai indicatif |
|---|---:|---|
| 0 a 0,5 kg | 8,90 | 1 a 2 jours |
| 0,5 a 1 kg | 10,50 | 1 a 2 jours |
| 1 a 2 kg | 12,90 | 1 a 2 jours |
| 2 a 5 kg | 17,90 | 1 a 2 jours |
| 5 a 10 kg | 24,90 | 1 a 2 jours |
| 10 a 20 kg | 34,90 | 1 a 2 jours |

#### Service eco_relay

| Tranche de poids | Tarif de base (EUR) | Delai indicatif |
|---|---:|---|
| 0 a 1 kg | 4,20 | 3 a 6 jours |
| 1 a 2 kg | 5,80 | 3 a 6 jours |
| 2 a 5 kg | 8,40 | 3 a 6 jours |
| 5 a 10 kg | 12,90 | 3 a 6 jours |

## 5. Surcharges et options (demo)

### 5.1 Signature

- `+1,50 EUR` (standard)
- `+1,20 EUR` (express)
- non disponible pour `eco_relay` dans cette demo

### 5.2 Assurance complementaire (insurance_plus)

| Valeur declaree (EUR) | Cout optionnel (EUR) |
|---|---:|
| jusqu'a 100 EUR | 1,90 |
| 100 a 300 EUR | 3,90 |
| 300 a 500 EUR | 5,90 |
| 500 a 1000 EUR | 9,90 |

### 5.3 Packaging special (demo, optionnel)

| Type | Supplement (EUR) | Cas typique |
|---|---:|---|
| Fragile renforce | 2,50 | Objet cassable |
| Tube poster | 1,80 | Documents / affiches |
| Petit format suivi | 0,90 | Petits objets non fragiles |

## 6. Regles de recommandation (demo)

### 6.1 Choix du service

Regles simples pour l'agent:

1. Si le client mentionne une urgence (livraison rapide, demain, tres vite), proposer `express`
2. Si le budget est prioritaire et delai flexible, proposer `standard` ou `eco_relay`
3. Si le client prefere le retrait en point, proposer `eco_relay` (si disponible) ou reroutage pickup
4. Si le poids > 10 kg, verifier les limites du service choisi avant de confirmer

### 6.2 Signature et assurance

Proposer `signature` si:

- valeur de l'objet > 100 EUR
- besoin de preuve de remise
- client exprime une crainte de perte ou vol

Proposer `insurance_plus` si:

- valeur declaree > 100 EUR
- objet fragile ou difficile a remplacer

### 6.3 Formulation recommandee pour l'agent

L'agent doit presenter:

- une option "equilibre" (souvent `standard`)
- une option "rapide" (`express`)
- une option "economique" (`eco_relay`) si pertinente

## 7. Limites de dimensions et poids (demo)

### 7.1 Limites generales (demo)

| Service | Poids max | Longueur max | Somme L + l + h max |
|---|---:|---:|---:|
| `standard` | 20 kg | 100 cm | 200 cm |
| `express` | 20 kg | 100 cm | 200 cm |
| `eco_relay` | 10 kg | 70 cm | 150 cm |

### 7.2 Rappels pour l'agent

- Toujours demander dimensions si l'utilisateur parle d'un objet volumineux
- Ne pas confirmer un tarif final sans verifier poids + dimensions
- Si information manquante, donner une fourchette et expliciter l'hypothese

## 8. Exemples de calculs (demo)

### 8.1 Exemple A - Colis 1,8 kg, non urgent

Hypothese:

- poids: 1,8 kg
- France metropolitaine
- pas de signature
- pas d'assurance

Resultat indicatif:

- `standard`: 7,90 EUR
- `express`: 12,90 EUR
- `eco_relay`: 5,80 EUR

Recommandation type:

- Economique: `eco_relay`
- Equilibre: `standard`
- Rapide: `express`

### 8.2 Exemple B - Colis 1,8 kg, objet valeur 350 EUR

Hypothese:

- poids: 1,8 kg
- valeur declaree: 350 EUR
- signature + assurance conseillees

Calcul indicatif (standard):

- base standard: 7,90 EUR
- signature: +1,50 EUR
- assurance (300-500): +5,90 EUR
- total indicatif: 15,30 EUR

Calcul indicatif (express):

- base express: 12,90 EUR
- signature: +1,20 EUR
- assurance (300-500): +5,90 EUR
- total indicatif: 20,00 EUR

## 9. Reponses types pour l'agent (RAG demo)

### 9.1 Question: "Je veux le moins cher"

Reponse attendue:

- proposer `eco_relay` si compatible poids/dimensions
- sinon `standard`
- mentionner delai indicatif
- rappeler que le prix final depend du poids et dimensions exacts

### 9.2 Question: "Je veux que ce soit livre vite et en securite"

Reponse attendue:

- proposer `express`
- recommander `signature`
- recommander `insurance_plus` si valeur declaree
- expliquer le compromis prix / delai / preuve de remise

### 9.3 Question: "Mon client sera absent"

Reponse attendue:

- proposer `eco_relay` des le depart
- ou livraison domicile avec reroutage pickup possible
- mentionner la notification client

## 10. FAQ (demo)

### Le tarif depend-il uniquement du poids ?

Non. Le poids est un critere principal, mais les dimensions, les options (signature, assurance) et parfois le mode de remise influencent le cout final.

### Le service express inclut-il automatiquement la signature ?

Non, dans cette demo la signature est une option additionnelle.

### Peut-on recommander eco_relay pour tous les colis ?

Non. Le service `eco_relay` a des limites plus strictes (poids / dimensions) et suppose une remise en point de retrait.

## 11. Scenarios de demo pour illustrer le corpus

### Scenario 1 - Comparaison de services

Question:

`J'envoie un colis de 1,8 kg en France, quelles options ai-je et a quel prix approximatif ?`

Attendus:

- comparaison `standard` / `express` / `eco_relay`
- tarifs indicatifs
- mention des delais

### Scenario 2 - Objet de valeur

Question:

`J'expedie un objet de 350 EUR, que conseillez-vous en plus du transport ?`

Attendus:

- signature
- assurance complementaire
- justification (preuve de remise / couverture)

### Scenario 3 - Budget vs urgence

Question:

`Je veux un compromis entre prix et rapidite pour un envoi non urgent.`

Attendus:

- recommandation `standard`
- explication de la logique de choix

## 12. Mots-cles retrieval utiles

- tarif colis standard express
- comparaison services colis
- signature livraison
- assurance colis valeur declaree
- eco relay point retrait
- poids dimensions colis
- prix approximatif envoi 2 kg

