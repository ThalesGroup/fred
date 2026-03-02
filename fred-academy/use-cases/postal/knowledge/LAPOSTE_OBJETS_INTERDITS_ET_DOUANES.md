# Guide de Demonstration RAG - Objets Interdits, Restrictions et Douanes (Style La Poste)

> Document de demonstration (fictif) pour illustrer un corpus RAG "conformite envoi".
> Objectif: permettre a un agent de repondre a des questions sur les objets interdits, les restrictions et les formalites douanieres (demo).

## 1. Objet du document

Ce guide couvre:

- objets interdits (demo)
- objets soumis a restrictions
- bonnes pratiques de declaration
- formalites douanieres simplifiees (CN22 / CN23, facture)
- cas d'usage frequents (UE / hors UE)

Il est utile pour des questions comme:

- "Puis-je envoyer des batteries ?"
- "Quel document faut-il pour un colis hors UE ?"
- "Que risque-t-on si la declaration est incomplete ?"
- "Comment preparer un colis international ?"

## 2. Avertissement demo

- Ce document est pedagogique et fictif
- Il ne remplace pas les regles legales officielles
- En cas de doute, l'agent doit recommander une verification des conditions officielles en vigueur

## 3. Classification des objets (demo)

### 3.1 Categories

Les objets sont classes dans la demo selon 3 niveaux:

- `interdit`: envoi non autorise
- `restreint`: envoi possible sous conditions
- `autorise`: envoi possible sous reserve d'emballage / declaration adaptes

### 3.2 Regle pour l'agent

Quand un utilisateur mentionne un objet ambigu:

1. identifier la categorie probable (interdit / restreint / autorise)
2. demander les details manquants (quantite, type, destination)
3. repondre avec prudence si hors UE ou objet sensible
4. rappeler l'importance de la declaration exacte

## 4. Objets interdits (demo)

### 4.1 Liste des interdictions typiques

| Categorie | Exemple | Statut | Motif (demo) |
|---|---|---|---|
| Explosifs | feux d'artifice, munitions explosives | interdit | risque securite majeur |
| Gaz sous pression | bonbonnes gaz, aerosols industriels | interdit | risque pression / inflammabilite |
| Produits hautement inflammables | solvants, essence | interdit | risque incendie |
| Produits corrosifs | acides forts | interdit | risque fuite / brulure |
| Stupefiants illicites | substances interdites | interdit | illegal |
| Armes prohibees | certaines armes / pieces interdites | interdit | regulation / securite |
| Matieres infectieuses | echantillons biologiques non autorises | interdit | risque sanitaire |

### 4.2 Reponse type de l'agent (interdit)

Format recommande:

- indiquer que l'objet semble interdit
- expliquer le motif general (securite / legal)
- ne pas proposer de contournement
- orienter vers verification officielle si besoin

## 5. Objets restreints (demo)

### 5.1 Liste indicative

| Objet | Statut | Conditions possibles (demo) |
|---|---|---|
| Batterie lithium integree a un appareil | restreint | appareil eteint, protection, emballage adapte |
| Batterie lithium seule | restreint / souvent refuse selon destination | quantite limitee, emballage renforce, destination eligible |
| Parfum / produit avec alcool | restreint | quantite limitee, emballage et declaration |
| Produits alimentaires non perissables | restreint | destination autorisee, declaration precise |
| Medicaments non refrigeres | restreint | usage personnel, docs selon pays |
| Liquides | restreint | contenants securises, protection fuite |
| Objets de valeur | autorise + precautions | signature + assurance recommandees |

### 5.2 Questions de clarification que l'agent doit poser

Pour un objet restreint, demander:

- destination (France / UE / hors UE)
- quantite
- format (ex: batterie seule ou dans appareil)
- nature exacte du produit
- valeur approximative

## 6. Emballage et declaration (demo)

### 6.1 Regles generales d'emballage

- emballage ferme et solide
- protection interne contre chocs
- absence de jeu excessif dans le colis
- protection anti-fuite pour liquides
- etiquetage clair si fragile

### 6.2 Declaration de contenu

La declaration doit etre:

- precise (pas "objet divers")
- sincere (pas de sous-declaration volontaire)
- coherent avec la valeur et la nature du contenu

Exemples de declaration a eviter:

- `gift`
- `sample`
- `misc items`

Exemples preferables:

- `wireless headphones`
- `printed documents`
- `ceramic mug`
- `cotton t-shirts (x2)`

## 7. Douanes (demo) - notions essentielles

### 7.1 Quand la douane s'applique (simplification demo)

- Envoi national France: pas de formalite douaniere
- Envoi dans l'UE: formalites souvent simplifiees (selon cas)
- Envoi hors UE: declaration douaniere requise dans la plupart des cas

### 7.2 Documents courants (demo)

| Document | Quand | Usage |
|---|---|---|
| `CN22` | petits colis / faible valeur (demo) | declaration simplifiee |
| `CN23` | colis plus volumineux / valeur plus elevee (demo) | declaration detaillee |
| Facture commerciale | vente / e-commerce | base douane / taxes |
| Facture pro forma | envoi sans vente (echantillon, retour, cadeau selon cas) | justification de valeur |

### 7.3 Informations minimales a renseigner

- description precise des articles
- quantite
- valeur unitaire et totale
- poids
- pays d'origine (si applicable)
- motif d'envoi (vente, cadeau, retour, echantillon)

## 8. Matrice de decision douaniere (demo)

| Cas | Destination | Vente ? | Document a proposer (demo) | Vigilance |
|---|---|---|---|---|
| Petit colis faible valeur | hors UE | non | `CN22` + valeur declaree | description claire |
| Colis marchand | hors UE | oui | `CN23` + facture commerciale | valeurs detaillees |
| Retour produit | hors UE | non (retour) | `CN23` + facture pro forma / justificatif retour | motif "return" |
| Cadeau | hors UE | non | `CN22` ou `CN23` selon valeur/poids | declaration sincere, pas de sous-valuation |

## 9. Risques en cas de declaration incorrecte (demo)

### 9.1 Consequences possibles

- blocage en douane
- retard de livraison
- demande de documents complementaires
- retour expediteur
- refus de prise en charge

### 9.2 Recommandation agent

L'agent doit dire clairement:

- "Je peux vous guider sur les informations a preparer"
- "La validation finale depend des regles du pays de destination"

## 10. Scenarios de demonstration (questions RAG)

### 10.1 Scenario A - Batterie lithium

Question:

`Puis-je envoyer une batterie lithium ?`

Reponse attendue:

- objet potentiellement restreint
- demander si batterie seule ou integree
- demander destination
- rappeler emballage / restrictions selon destination

### 10.2 Scenario B - Vente hors UE

Question:

`J'envoie un produit vendu a un client hors UE, que faut-il comme document ?`

Reponse attendue:

- declaration douaniere (`CN22`/`CN23` selon cas, demo)
- facture commerciale
- description precise + valeur + quantite

### 10.3 Scenario C - Cadeau international

Question:

`J'envoie un cadeau a un proche hors UE, dois-je faire une declaration ?`

Reponse attendue:

- oui, declaration de contenu en general
- document simplifie ou detaille selon poids/valeur (demo)
- importance de ne pas sous-declarer

### 10.4 Scenario D - Parfum / liquide

Question:

`Je veux envoyer un parfum, est-ce autorise ?`

Reponse attendue:

- objet souvent restreint (liquide / alcool)
- demander destination et quantite
- expliquer conditions d'emballage et possibles restrictions

## 11. Reponses types (style agent)

### 11.1 Objet potentiellement interdit

`D'apres cette base de connaissances, cet objet semble appartenir a une categorie interdite pour l'envoi postal (motif: securite / regulation). Je ne peux pas recommander son expédition. Si besoin, je peux vous aider a verifier les conditions officielles applicables a votre destination.`

### 11.2 Objet restreint (batterie)

`Les batteries lithium sont souvent soumises a restrictions. Pour vous repondre correctement, j'ai besoin de preciser: est-ce une batterie seule ou integree dans un appareil, quelle quantite, et vers quelle destination souhaitez-vous l'envoyer ?`

### 11.3 Douane hors UE

`Pour un envoi hors UE, il faut en general une declaration douaniere (format simplifie ou detaille selon le colis) et une description precise du contenu avec sa valeur. En cas de vente, une facture commerciale est recommandee.`

## 12. Checklist pratique avant depot (demo)

### 12.1 Checklist colis national

- [ ] objet autorise
- [ ] emballage adapte
- [ ] adresse complete
- [ ] service choisi (standard / express / eco_relay)
- [ ] option signature / assurance si necessaire

### 12.2 Checklist colis international (hors UE)

- [ ] objet non interdit / restrictions verifiees
- [ ] description precise des articles
- [ ] valeur declaree
- [ ] quantites et poids
- [ ] document douanier prepare (`CN22` / `CN23` selon cas demo)
- [ ] facture commerciale ou pro forma si besoin

## 13. FAQ (demo)

### Peut-on envoyer des liquides ?

Parfois oui, mais souvent sous conditions (emballage anti-fuite, quantite, destination). Cela entre dans la categorie "restreint" dans cette demo.

### Faut-il declarer un cadeau ?

Oui, il faut en general declarer le contenu et la valeur, surtout hors UE.

### Que faire si je ne connais pas le document douanier exact ?

Fournir une description precise du colis, sa valeur, la destination et le motif d'envoi. L'agent peut guider la preparation des informations avant verification finale.

## 14. Mots-cles retrieval utiles

- objet interdit envoi postal
- batterie lithium colis
- parfum envoi international
- liquide restrictions colis
- douane hors ue cn22 cn23
- facture commerciale colis
- declaration contenu cadeau
- blocage en douane retard colis

