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

Le panneau **Corpus** montre toute l'arborescence : ouvrez-le depuis son bouton,
à gauche de la liste. Cliquez
sur un dossier pour l'afficher dans la liste, double-cliquez pour le déplier ou
le replier, et double-cliquez sur un fichier pour l'ouvrir. Vous pouvez replier
le panneau et l'élargir en tirant son bord.

> **Un document déposé hors d'une bibliothèque ne sera jamais utilisé par un
> agent.** C'est le premier point à vérifier lorsqu'un document semble ignoré.

Les formats courants passent : PDF, texte, Word, OpenDocument, PowerPoint,
Excel, CSV, Markdown, mails, images, vidéos et enregistrements audio. Un format inhabituel peut être refusé ;
convertissez-le dans un format courant.

## Importer des vidéos et des enregistrements audio

Une vidéo (**.mp4**, **.mov**, **.mkv**, **.webm**, **.avi**) ou un
enregistrement audio (**.mp3**, **.wav**, **.m4a**, **.ogg**, **.flac**,
**.aac**) peut être déposé dans une bibliothèque, jusqu'à 100 Mo par fichier.
Les paroles sont retranscrites, avec le moment où chaque phrase est dite.

Selon la configuration, une vidéo est aussi découpée en scènes : pour chacune,
l'agent dispose d'une courte description de ce qu'on voit à l'écran (lieu,
personnes, actions, texte ou diapositives affichés). Il peut ainsi répondre à
« que montre la vidéo vers la dixième minute ? » comme à « qu'a dit
l'intervenant sur le budget ? ».

Une longue vidéo prend plusieurs minutes à traiter. La retranscription ne
distingue pas encore qui parle.

## Importer des mails

Un mail enregistré depuis Outlook (fichier **.msg**) ou depuis une autre
messagerie (fichier **.eml**) peut être déposé dans une bibliothèque. Pour
l'obtenir, faites glisser le mail hors de votre messagerie, ou utilisez
**Enregistrer sous**.

Ce qui est gardé : l'expéditeur, les destinataires, la date, l'objet, le texte
du mail et **le nom** de ses pièces jointes. Le texte des pièces jointes PDF,
Word et PowerPoint est lu aussi ; un même fichier joint plusieurs fois n'est lu
qu'une fois. Les autres pièces jointes (images, archives…) ne sont pas lues :
déposez-les à part si l'agent doit s'en servir. Les en-têtes de copie cachée
(Cci) ne sont pas ajoutés à la liste des destinataires extraite.
Un mail transféré en pièce jointe est lu aussi : son texte suit celui du mail.

> **Un mail déposé suit les droits d'accès du document.** Les personnes autorisées
> à le lire peuvent aussi consulter les noms et adresses présents dans son contenu.
> Vérifiez qu'il peut être partagé avant de le déposer.

Un mail chiffré ne peut pas être lu et sera refusé. Les signatures séparées
(`multipart/signed`) sont prises en charge ; les signatures S/MIME opaques
(`signed-data`, dont `.p7m`) ne le sont pas. Exportez une copie non chiffrée avec
une signature séparée ou sans signature. Un mail dépassant 25 Mo est refusé :
retirez ses pièces jointes les plus lourdes et enregistrez-le à nouveau.

## Un document du même nom existe déjà

Si un document porte déjà le même nom dans la bibliothèque visée, la plateforme vous le
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

Dès que vous validez, la fenêtre se ferme : vous reprenez la main tout de suite et
l'envoi continue derrière. Un **panneau** s'ouvre à droite de la page et suit
chaque fichier. Vous pouvez le replier en simple bouton, le rouvrir, et
l'élargir en tirant son bord gauche. Il se replie tout seul quand le dernier
fichier qu'il suivait a disparu.

Chaque fichier passe par quatre temps. Le panneau les montre comme quatre
repères qui se cochent l'un après l'autre, et nomme celui en cours :

1. **Envoi du fichier** — votre navigateur transmet. Tant que ce temps dure,
   rien n'est encore arrivé sur la plateforme.
2. **Préparation du document** — la plateforme a reçu le fichier et le range.
3. **Extraction du contenu** — la plateforme lit le document. C'est presque toujours le
   temps le plus long : un PDF volumineux ou scanné peut y rester plusieurs
   minutes.
4. **Indexation** — la plateforme range ce qu'elle a lu pour pouvoir le retrouver.

La plateforme analyse quelques fichiers à la fois. Quand vous en importez plusieurs, ceux
qui attendent leur tour affichent **En attente…**, en gris, avec un repère
immobile : le fichier est bien arrivé, son analyse démarrera dès qu'une place se
libère.

**C'est à la fin du dernier temps, et pas à la fin de l'envoi, que le document
devient utilisable par un agent.**

Quand un fichier est arrivé au bout, sa ligne affiche **Ingestion terminée**
puis disparaît d'elle-même au bout de quelques secondes : le document est dans
le tableau, il n'y a plus rien à suivre. Seuls les fichiers en échec ou en
attente de réponse restent.

> Aucun de ces temps n'annonce de pourcentage : la plateforme ne sait pas combien de
> temps il lui reste, et préfère ne pas l'inventer. Un temps qui dure n'est
> pas un temps bloqué.

### Si un fichier échoue

Il reste dans le panneau avec la raison de l'échec, et un bouton **Réessayer**
tant que votre navigateur a encore le fichier sous la main. Si vous avez
rechargé la page entre-temps, le panneau vous demande de le sélectionner à
nouveau : un navigateur ne peut pas rouvrir un fichier tout seul.

### Annuler un envoi

Les fichiers partent quelques-uns à la fois. Ceux qui attendent encore leur tour
peuvent être annulés d'un clic ; ceux qui sont déjà partis appartiennent à la
plateforme et vont au bout.

### Si vous fermez l'onglet en cours d'import

Ce qui est déjà arrivé sur la plateforme continue sans vous. Le reste n'est jamais
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

Un clic droit sur un fichier ou un dossier ouvre ces actions. **Copier le nom**
y place son nom exact dans le presse-papiers.

Chaque équipe dispose d'un **espace de stockage**, dont la page montre la
consommation. En approchant de la limite, un dépôt peut être refusé : faites du
ménage, ou demandez un ajustement à un administrateur de l'équipe.

## Comment un agent lit vos documents

Ce fonctionnement explique la forme des réponses. Le choix ne vous appartient
pas : l'agent décide selon votre demande.

- **Recherche** — trouve les passages les plus pertinents et répond à partir
  d'eux. Rapide, et le bon réflexe pour « que sait-on sur X ? ». Elle ne remonte
  que ce qu'elle juge pertinent, donc **elle peut manquer des éléments**.
- **Lire** - consulte le texte extrait du fichier, par portions. La conversion
  ou l'OCR peut perdre des détails ; ces portions ne sont pas les pages du PDF.
- **Résumer** - produit un aperçu court et sélectionne les points principaux.
  Certains détails sont volontairement omis.
- **Extraire** - recherche les informations demandées dans les portions du
  document, puis réunit les résultats en retirant les doublons. Cela ne garantit
  ni de tout retrouver ni de compter chaque occurrence. Si une portion échoue,
  la demande signale un échec, jamais une absence d'information. Au-delà de la
  limite de taille, seuls le début et la fin sont traités et un avertissement
  accompagne le résultat, même s'il est vide.

Sur un même **contrat de maintenance**, trois demandes illustrent la différence :

| Demande                                                    | Résultat attendu                                                         |
| ---------------------------------------------------------- | ------------------------------------------------------------------------ |
| « Cite la clause de résiliation. »                         | Le libellé du passage dans le texte extrait.                             |
| « Résume ce contrat en deux phrases. »                     | Une synthèse des points principaux, sans tous les détails.               |
| « Relève les échéances, les actions et les responsables. » | Une liste structurée des éléments trouvés, avec les limites éventuelles. |

Exprimez votre besoin : l'agent choisit l'outil. Les packs **Pièces jointes** et
**Documents de l'équipe** les regroupent déjà ; la vue **Avancé** permet de les
régler séparément. La confirmation avant résumé ou extraction est activée par
défaut et peut être réglée sur l'agent.

Un document jamais utilisé ? Voir
[Problèmes courants](/help/fr/troubleshooting/common-problems).
