---
title: Les ressources
order: 30
description: Déposer les documents de l'équipe, les organiser, comprendre comment un agent les lit.
icon: folder
---

# Les ressources

Les **ressources** sont les documents de votre équipe. C'est ce qui permet à un
agent de parler de _vos_ contenus et de vous montrer les passages sur lesquels
il s'appuie.

> Déposer, renommer ou supprimer un document demande le rôle **Éditeur**. Tout
> membre peut en revanche les consulter et interroger un agent qui les utilise.

## Le corpus d'équipe

La page **Ressources** présente le **corpus d'équipe** : la base documentaire
partagée entre ses membres.

Les documents se rangent dans des **bibliothèques**, comme des dossiers. Créez
d'abord une bibliothèque, puis déposez vos documents dedans.

> **Un document déposé hors d'une bibliothèque ne sera jamais utilisé par un
> agent.** C'est le premier point à vérifier lorsqu'un document semble ignoré.

Les formats courants passent : PDF, texte, Word, OpenDocument, PowerPoint,
Excel, CSV, Markdown, images et fichiers audio. Un format inhabituel peut être
refusé ; convertissez-le dans un format courant.

## Un document du même nom existe déjà

Si un document porte déjà le même nom dans la bibliothèque visée, Fred vous le
dit **avant** d'envoyer quoi que ce soit, et vous laisse choisir :

- **Remplacer** : le document existant garde sa place et ses liens, seul son
  contenu change. Tout ce qui le citait continue de fonctionner et renvoie
  désormais vers la nouvelle version.
- **Ignorer** : votre fichier est écarté de l'import, le document déjà présent
  ne bouge pas.

Vous pouvez répondre en une fois pour tous les fichiers concernés, ou fichier
par fichier. Le même nom dans une **autre** bibliothèque n'est pas un doublon :
ce sont deux documents indépendants.

> Si quelqu'un dépose ce nom pendant votre import, la question vous est simplement
> reposée dans le panneau de suivi : **Remplacer** ou **Ignorer**. Votre fichier
> n'est pas perdu, il attend votre réponse.

## Suivre vos imports

Dès que vous validez, la fenêtre se ferme : vous récupérez Fred tout de suite et
l'envoi continue derrière. Un **panneau** s'ouvre à droite de la page et suit
chaque fichier. Vous pouvez le replier en simple bouton, le rouvrir, et
l'élargir en tirant son bord gauche.

Chaque fichier passe par quatre temps, que le panneau coche l'un après
l'autre :

1. **Envoi du fichier** — votre navigateur transmet. Tant que ce temps dure,
   rien n'est encore arrivé chez Fred.
2. **Préparation du document** — Fred a reçu le fichier et le range.
3. **Extraction du contenu** — Fred lit le document. C'est presque toujours le
   temps le plus long : un PDF volumineux ou scanné peut y rester plusieurs
   minutes.
4. **Indexation** — Fred range ce qu'il a lu pour pouvoir le retrouver.

**C'est à la fin du dernier temps, et pas à la fin de l'envoi, que le document
devient utilisable par un agent.**

> Aucun de ces temps n'annonce de pourcentage : Fred ne sait pas combien de
> temps il lui reste, et préfère ne pas l'inventer. Un temps qui dure n'est
> pas un temps bloqué.

### Si un fichier échoue

Il reste dans le panneau avec la raison de l'échec, et un bouton **Réessayer**
tant que votre navigateur a encore le fichier sous la main. Si vous avez
rechargé la page entre-temps, le panneau vous demande de le sélectionner à
nouveau : un navigateur ne peut pas rouvrir un fichier tout seul.

### Annuler un envoi

Les fichiers partent quelques-uns à la fois. Ceux qui attendent encore leur tour
peuvent être annulés d'un clic ; ceux qui sont déjà partis appartiennent à Fred
et vont au bout.

### Si vous fermez l'onglet en cours d'import

Ce qui est déjà arrivé chez Fred continue sans vous. Le reste n'est jamais
parti : à votre retour, le panneau **nomme les fichiers qui ne sont pas
arrivés** et vous propose de les sélectionner à nouveau. Seuls ceux-là
repartent, vers la même bibliothèque.

## Après le dépôt

Sur la ligne de chaque document, une étiquette **Traitement** s'affiche le temps
de l'analyse et disparaît d'elle-même : vous n'avez rien à faire. Un repère peut
aussi y apparaître lorsqu'un import attend votre décision — un clic ouvre le
panneau, où la réponse se donne. Chaque document indique par ailleurs son
origine : **Déposé**, **Généré** par un agent, ou **Partagé**.

## Gérer ses documents

Depuis le corpus : **renommer**, **prévisualiser**, **supprimer**, ou **exclure
de la recherche** — l'agent cesse alors d'en tenir compte sans que le document
disparaisse, et vous pouvez l'inclure à nouveau.

Chaque équipe dispose d'un **espace de stockage**, dont la page montre la
consommation. En approchant de la limite, un dépôt peut être refusé : faites du
ménage, ou demandez un ajustement à un administrateur de l'équipe.

## Comment un agent lit vos documents

Ce fonctionnement explique la forme des réponses. Le choix ne vous appartient
pas : l'agent décide selon votre demande.

- **Recherche** — trouve les passages les plus pertinents et répond à partir
  d'eux. Rapide, et le bon réflexe pour « que sait-on sur X ? ». Elle ne remonte
  que ce qu'elle juge pertinent, donc **elle peut manquer des éléments**.
- **Lecture mot à mot** — lit le texte exact, dans l'ordre, quand vous voulez le
  libellé précis d'un passage.
- **Extraction** — parcourt le document entier et liste tout ce qui correspond,
  sans rien omettre. La plus lente, la plus exhaustive.
- **Résumé** — un aperçu court, volontairement non exhaustif.

> **Si rien ne doit être oublié, dites-le** : « liste _toutes_ les échéances ».
> L'agent passe alors par l'extraction plutôt que par la recherche.

Un document jamais utilisé ? Voir
[Problèmes courants](/help/fr/troubleshooting/common-problems).
