---
title: Problèmes courants
order: 10
description: Connexion, droits manquants, document ignoré, agent suspendu, réponse interrompue.
icon: build
---

# Problèmes courants

## Je n'arrive pas à me connecter

La connexion utilise votre compte d'organisation. Vérifiez vos identifiants
habituels. En cas de session expirée ou de boucle de connexion, rafraîchissez la
page ou rouvrez l'onglet. Si cela persiste, il s'agit de la configuration
d'accès : adressez-vous à votre administrateur.

## Je ne vois pas mon équipe

Elle est probablement **privée** — elle n'apparaît alors qu'à ses membres — ou
bien on ne la rejoint que sur ajout. Dans les deux cas, demandez à un de ses
membres de vous ajouter. Voir
[Équipes et droits](/help/fr/features/teams-and-permissions).

## Je n'ai pas accès à une action

Il s'agit presque toujours d'une question de **rôle**, et le plus souvent du
même malentendu : **Admin et Éditeur sont deux autorisations distinctes**, et non
deux échelons.

- Créer ou modifier un agent, un prompt, un document → **Éditeur**. Être Admin
  ne suffit pas.
- Gérer les membres et les réglages → **Admin**. Être Éditeur ne suffit pas.
- Lancer une campagne d'évaluation → **Analyste** ou **Admin**.

Détenir les deux jeux de droits suppose de porter les deux rôles ; un Admin de
votre équipe peut vous les accorder. Quant aux pages d'administration de la
plateforme, ne pas les voir correspond au fonctionnement attendu.

## Un document n'est jamais utilisé

Dans l'ordre de fréquence :

1. **Il est hors d'une bibliothèque.** Un document déposé à côté ne sera jamais
   lu. Placez-le dans une bibliothèque.
2. **La bibliothèque n'est pas rattachée à l'agent** que vous interrogez.
3. **Il est encore en préparation** — l'étiquette _Traitement_ est toujours là.
4. **Il a été exclu de la recherche.** Réincluez-le.

Si sa préparation traîne ou signale une erreur : patientez pour un gros
document, vérifiez que le format est courant, et redéposez-le au besoin.

## Un agent est visible mais inutilisable

Il est **suspendu**. Trois causes :

- Une fonction dont il dépend a été **désactivée** pour l'équipe, ou l'accès de
  l'équipe y a été **retiré** : seule la plateforme peut le rétablir
  (voir [Administration](/help/fr/features/administration)).
- La **configuration** d'une de ses fonctions n'est plus valide : désactivez la
  fonction sur l'agent, enregistrez, réactivez-la, enregistrez à nouveau.

Cas voisin : un agent **copié dans une autre équipe** perd ses choix propres à
l'équipe d'origine (bibliothèques, dossiers, documents) et les capacités que
cette équipe n'a pas. Rattachez-lui les ressources de sa nouvelle équipe.

## La réponse s'interrompt ou n'arrive pas

Relancez la question : un aléa réseau ou de traitement suffit à interrompre une
réponse. Si la demande est très large, découpez-la. Une interruption qui se
répète sur **tous** les agents relève d'un incident côté plateforme ; réessayez
plus tard.

## Ma pièce jointe est refusée

Vérifiez le format. Vérifiez aussi que l'agent dispose bien du pack **Pièces
jointes** — sans lui, le trombone n'apparaît pas. Pour un document
destiné à durer, passez par les [ressources](/help/fr/features/resources).

## Une conversation ne se charge pas

Rafraîchissez la page. Si une seule conversation reste inaccessible alors que
les autres fonctionnent, elle a probablement été supprimée — par vous, ou par la
purge de rétention de l'équipe.
