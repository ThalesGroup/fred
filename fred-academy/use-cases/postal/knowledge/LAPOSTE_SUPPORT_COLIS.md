# Guide de Demonstration RAG - Support Colis (Style La Poste)

> Document de demonstration (contenu fictif mais realiste) pour tests RAG / agent conversationnel.
> Usage recommande: ingestion dans une librairie "Demo LaPoste" pour questions support client, operations colis, reroutage et reclamations.

## 1. Objet du document

Ce guide sert de base de connaissances pour un agent conversationnel capable de:

- expliquer des procedures de support colis
- recommander une action (suivi, reroutage, replanification, notification)
- rappeler les regles de compensation (demo)
- guider l'ouverture d'une reclamation
- formuler des messages client clairs

Le document est volontairement structure pour le RAG:

- titres explicites
- tableaux
- mots-cles metier repetes
- cas concrets

## 2. Perimetre de la demo

La demo couvre principalement:

- colis nationaux (France)
- statuts de suivi colis
- reroutage vers point de retrait / pickup point
- replanification de livraison a domicile
- notification client
- estimation de compensation en cas de retard
- ouverture de reclamation (delay, damage, loss)

## 3. Definitions utiles (vocabulaire support)

### 3.1 Statuts colis (demo)

- `CREATED`: etiquette creee, colis pas encore pris en charge
- `IN_TRANSIT`: colis en transit entre plateformes
- `OUT_FOR_DELIVERY`: colis en cours de tournee
- `DELAYED_AT_HUB`: colis bloque en hub (retard)
- `REROUTED_TO_PICKUP_POINT`: livraison redirigee vers point de retrait
- `DELIVERY_RESCHEDULED`: livraison domicile replanifiee
- `DELIVERED`: livre
- `CANCELLED`: annule
- `LOST`: perdu

### 3.2 Actions support disponibles (demo)

- `track_package`
- `get_pickup_points_nearby`
- `reroute_package_to_pickup_point`
- `reschedule_delivery`
- `notify_customer`
- `estimate_compensation`
- `open_claim`

## 4. Politique operationnelle (demo)

### 4.1 Principe general

Le support doit privilegier une resolution rapide et traçable:

1. verifier le statut reel du colis
2. verifier si une action immediate est possible
3. proposer l'option la plus simple pour le client
4. notifier le client si une action a ete executee
5. estimer la compensation si le retard depasse le seuil
6. ouvrir une reclamation si necessaire

### 4.2 Ordre de priorite des actions

Quand un colis est en anomalie (`DELAYED_AT_HUB`, retard significatif, tentative echouee), utiliser cet ordre:

1. `track_package` (diagnostic)
2. `get_pickup_points_nearby` (si reroutage utile)
3. `reroute_package_to_pickup_point` ou `reschedule_delivery`
4. `notify_customer`
5. `estimate_compensation`
6. `open_claim` (si demande client ou incident etabli)

## 5. Matrice de decision support (cas frequents)

| Situation client | Signal typique | Action recommandee | Commentaire |
|---|---|---|---|
| "Ou est mon colis ?" | statut inconnu pour le client | `track_package` | Toujours commencer par le suivi |
| Colis en retard au hub | `DELAYED_AT_HUB` | `get_pickup_points_nearby` puis reroutage si eligibile | Proposer une alternative concrete |
| Client absent / veut changer date | domicile, besoin de flexibilite | `reschedule_delivery` | Conserver livraison a domicile |
| Client prefere un retrait | domicile mais client indisponible | `reroute_package_to_pickup_point` | Puis `notify_customer` |
| Client demande geste commercial | retard prolongé | `estimate_compensation` | Appliquer regles demo |
| Colis abime ou perdu | incident confirme | `open_claim` | Type `damage` ou `loss` |

## 6. Regles de compensation (demo)

Ces regles sont fictives mais coherentes pour la demonstration.

### 6.1 Seuils d'eligibilite

- Service `express`:
  - compensation estimee = `8.0 EUR` si retard >= `24h`
  - code de politique: `DEMO-EXPRESS-24H`
- Service `standard`:
  - compensation estimee = `4.0 EUR` si retard >= `48h`
  - code de politique: `DEMO-STANDARD-48H`
- En dessous des seuils:
  - non eligible
  - code de politique: `DEMO-NO-COMP`

### 6.2 Important

- L'estimation de compensation n'ouvre pas automatiquement une reclamation.
- La reclamation reste une action distincte (`open_claim`).
- Une notification client peut etre envoyee avant ou apres l'estimation selon le contexte.

## 7. Procedure: colis retarde au hub avec reroutage vers pickup point

### 7.1 Objectif

Redonner de la predictibilite au client quand le colis est retarde en plateforme.

### 7.2 Procedure standard

1. Verifier le suivi (`track_package`)
2. Confirmer que le colis n'est pas dans un statut terminal (`DELIVERED`, `CANCELLED`, `LOST`)
3. Verifier l'eligibilite au reroutage
4. Chercher des points de retrait proches (`get_pickup_points_nearby`)
5. Proposer 1 a 3 options au client (avec adresse / horaires)
6. Executer `reroute_package_to_pickup_point`
7. Envoyer `notify_customer` avec confirmation de reroutage

### 7.3 Conditions de refus du reroutage (demo)

Le reroutage doit etre refuse si:

- statut terminal (`DELIVERED`, `CANCELLED`, `LOST`)
- colis non eligible au reroutage (`reroute_eligible = false`)
- point de retrait inconnu
- point de retrait sans capacite disponible

## 8. Procedure: replanification livraison domicile

### 8.1 Quand proposer `reschedule_delivery`

Proposer la replanification quand:

- le client souhaite conserver la livraison domicile
- le colis est encore en mode `home`
- le client a une indisponibilite ponctuelle

### 8.2 Creneaux (demo)

Valeurs de creneaux supportees:

- `morning`
- `afternoon`
- `evening`

### 8.3 Regle de communication

Toujours confirmer au client:

- la date demandee
- le creneau retenu
- le fait qu'il s'agit d'une replanification et non d'une annulation

## 9. Procedure: notification client

### 9.1 Quand notifier

Notifier apres une action support executee:

- reroutage effectif
- replanification validee
- information sur retard confirme
- ouverture de reclamation

### 9.2 Canaux (demo)

- `sms`
- `email`

### 9.3 Exemples de messages (recommandes)

#### Retard au hub (information)

Bonjour, votre colis est actuellement retarde en plateforme logistique. Nous suivons son acheminement et reviendrons vers vous avec une mise a jour. Merci de votre patience.

#### Reroutage confirme

Bonjour, votre colis a ete redirige vers un point de retrait a votre demande. Vous recevrez une confirmation des que le colis sera disponible au retrait.

#### Livraison replanifiee

Bonjour, la livraison de votre colis a ete replanifiee a la date demandee sur le creneau confirme. Merci de votre confiance.

## 10. Reclamation client (claim)

### 10.1 Types de reclamations (demo)

- `delay`: retard
- `damage`: colis endommage
- `loss`: colis perdu

### 10.2 Quand ouvrir une reclamation

Ouvrir une reclamation si:

- le client le demande explicitement
- le retard est important et non resolu
- le colis est signale endommage
- le colis est signale perdu

### 10.3 Informations minimales a collecter

- identifiant de suivi (`tracking_id`)
- motif (`delay` / `damage` / `loss`)
- description courte (contexte client)

### 10.4 Bonnes pratiques de redaction de la description

La description doit contenir:

- date ou periode du probleme
- symptome observe (retard, colis abime, non recu)
- attente client (information, resolution, compensation, remplacement)

Exemple:

`Customer reported delayed express parcel; expected yesterday. Tracking shows hub delay. Requests compensation review and updated ETA.`

## 11. Guide de reponse pour agent conversationnel (style support)

### 11.1 Format de reponse recommande

Une bonne reponse doit idealement contenir:

1. un resume de la situation
2. l'action proposee (ou l'action realisee)
3. les limites / conditions
4. la prochaine etape

### 11.2 Exemple de reponse (retard + reroutage)

Resume: le colis est en retard en plateforme logistique.  
Action proposee: je peux rechercher des points de retrait proches puis rediriger le colis vers celui de votre choix si le reroutage est eligibile.  
Prochaine etape: je vous propose 3 points de retrait et j'effectue le reroutage apres validation.

## 12. Donnees de demonstration (Paris / proche banlieue)

Exemples de points de retrait fictifs utiles pour demos:

| ID | Nom | Type | Ville | Code postal | Horaires |
|---|---|---|---|---|---|
| `PP-PAR-001` | Paris Louvre Locker | locker | Paris | 75001 | 24/7 |
| `PP-PAR-002` | Bastille Relay | partner_shop | Paris | 75011 | Mon-Sat 08:30-20:00 |
| `PP-PAR-003` | La Poste Montparnasse | post_office | Paris | 75015 | Mon-Fri 08:00-19:00, Sat 09:00-12:30 |
| `PP-ISS-001` | Issy Val de Seine Locker | locker | Issy-les-Moulineaux | 92130 | 24/7 |
| `PP-BOL-001` | Boulogne Centre Relay | partner_shop | Boulogne-Billancourt | 92100 | Mon-Sat 09:00-19:30 |

## 13. Scenarios de demonstration (questions RAG utiles)

### 13.1 Scenario A - Colis retarde et client presse

Question demo:

`Mon colis express est en retard au hub. Que pouvez-vous faire tout de suite ?`

Points attendus dans la reponse:

- suivi colis d'abord
- proposition de reroutage vers pickup point si eligibile
- notification client apres action
- estimation de compensation si retard >= 24h (express)

### 13.2 Scenario B - Client prefere un point de retrait

Question demo:

`Je ne serai pas chez moi demain. Pouvez-vous rediriger mon colis vers un point relais ?`

Points attendus:

- verifier statut non terminal
- verifier eligibilite reroutage
- lister points proches
- confirmer le point choisi
- notifier

### 13.3 Scenario C - Demande de compensation

Question demo:

`Mon colis standard a plus de 2 jours de retard, est-ce que j'ai droit a une compensation ?`

Points attendus:

- seuil standard >= 48h
- estimation demo = 4 EUR si seuil atteint
- possibilite d'ouvrir une reclamation

### 13.4 Scenario D - Reclamation dommage

Question demo:

`Mon colis est arrive abime, que faut-il faire ?`

Points attendus:

- ouverture de reclamation type `damage`
- description structurée du probleme
- information claire sur la suite

## 14. FAQ (version demo)

### Peut-on rerouter un colis deja livre ?

Non. Les statuts terminaux comme `DELIVERED` ne permettent pas de reroutage.

### Faut-il notifier le client apres chaque action ?

Oui, c'est recommande pour la traçabilite et l'experience client, surtout apres reroutage ou replanification.

### L'estimation de compensation vaut-elle decision finale ?

Non. C'est une estimation operationnelle (demo). La validation finale peut dependre d'une reclamation.

### Quelle est la premiere action a faire quand un client contacte le support ?

`track_package` (diagnostic initial).

## 15. Annexes - Mots-cles utiles pour retrieval

Mots-cles metier a couvrir dans les requetes:

- colis retarde
- hub congestion
- reroutage pickup point
- point relais
- replanification livraison
- notification client
- compensation retard express
- compensation retard standard
- reclamation delay damage loss
- colis livre mais non recu

