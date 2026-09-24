---
title: Les capacités
order: 15
description: Ce que chaque capacité permet, ce qu'elle ne fait pas, et quand elle est utile.
icon: extension
---

# Les capacités

Une **capacité** est une chose qu'un agent sait faire en plus de répondre :
chercher dans les documents de l'équipe, remplir une présentation, produire une
page web. Elles s'activent dans l'onglet **Capacités** d'un agent (voir
[Les agents](/help/fr/features/agents)).

Cette page décrit chacune d'elles : ce qu'elle fait, ses limites, et un cas où
elle est utile.

> **La liste affichée par l'interface fait foi.** Elle dépend du déploiement et
> de ce que l'administrateur a ouvert à votre équipe : une capacité décrite ici
> peut ne pas y figurer, et un déploiement peut en proposer d'autres.

## Données et connaissances

### Accès aux ressources de l'équipe

**Ce qu'elle fait** — l'agent consulte le corpus de l'équipe : il y cherche les
passages utiles et les cite, lit un document mot à mot, ou en extrait une
information de façon exhaustive. Les trois façons de lire sont détaillées sur
[Les ressources](/help/fr/features/resources).

**Ses limites** — l'agent ne voit que les bibliothèques rattachées à son
paramétrage, et un document déposé hors bibliothèque reste invisible. La
recherche remonte les passages qu'elle juge pertinents : elle est rapide, mais
pas exhaustive. C'est l'agent qui choisit sa façon de lire, selon la demande.

**Un exemple** — « Que disent nos procédures sur le délai de réponse à un
incident ? » L'agent cherche dans le corpus et répond en citant les passages
sur lesquels il s'appuie.

Cette capacité en regroupe plusieurs, que la vue **Avancé** sépare :

| Fonction                          | Ce qu'elle fait                                       | À savoir                                                                               |
| --------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Rechercher dans les ressources    | Trouve les passages pertinents et les cite            | Peut afficher dans la conversation un sélecteur de bibliothèque ou de document         |
| Exploiter les fichiers tabulaires | Exploite les données d'un CSV ou d'un Excel du corpus | Le fichier doit être déposé dans une bibliothèque ; ce n'est pas un outil de reporting |
| Résumer un document               | Produit le résumé d'un document                       | Demande votre confirmation avant chaque résumé ; longueur réglable                     |
| Comparer des documents            | Retrouve les passages proches d'un passage donné      | Travaille sur le corpus, jamais sur une pièce jointe                                   |
| Verbatim document                 | Restitue le texte exact, page par page                | Les pages renvoyées ont une longueur limitée                                           |
| Extraction d'information          | Parcourt le document entier sans rien omettre         | La plus lente et la plus coûteuse ; confirmation demandée par défaut                   |

### Accès au Wiki de l'équipe

> **Beta.** Le wiki porte l'étiquette **Beta** dans la navigation de l'équipe :
> c'est une proposition, pas encore une fonctionnalité figée. Sa conception
> peut évoluer d'après les retours d'usage — les vôtres sont attendus.

**Ce qu'elle fait** — l'agent lit les pages du wiki de l'équipe et suit les
règles qui y sont écrites. Selon le mode choisi, il peut aussi **proposer** des
pages et des modifications. Activer cette capacité pour une équipe est aussi ce
qui donne un wiki à ses membres.

**Ses limites** — aucun mode ne permet à l'agent de supprimer, renommer ou
déplacer une page. Une proposition vous est toujours soumise avant d'être
écrite. Le wiki est un espace de règles et de notes rédigées par l'équipe, pas
un substitut au corpus documentaire.

**Un exemple** — une équipe consigne dans son wiki ses conventions de nommage ;
l'agent chargé de rédiger des comptes rendus les applique sans qu'on les lui
rappelle à chaque fois.

### Pièces jointes à une conversation

**Ce qu'elle fait** — ajoute à l'interface de conversation un bouton permettant
de joindre un fichier (PDF, image, texte) à un message. L'agent peut alors le
résumer, le lire mot à mot ou en extraire une information.

**Ses limites** — une pièce jointe appartient à la conversation : elle n'entre
pas dans le corpus de l'équipe et n'est pas réutilisable ailleurs. Si cette
capacité est la seule activée, l'agent travaille **uniquement** sur les pièces
jointes et n'interroge jamais le corpus.

**Un exemple** — vous recevez un contrat par courriel, vous le joignez à une
conversation et demandez à l'agent d'en relever les échéances.

## Production de documents

### Générer un document Word

**Ce qu'elle fait** — l'agent rédige un document dans un panneau latéral ouvert
à côté de la conversation. Le document se retravaille au fil des échanges, vous
pouvez l'éditer vous-même, puis le télécharger au format Word ou Markdown.

**Ses limites** — c'est un document texte : titres, paragraphes, listes. Il n'y
a ni gabarit d'entreprise, ni mise en page complexe, ni maîtrise fine de la
typographie.

**Un exemple** — « Rédige une note de synthèse à partir des trois rapports que
nous venons de parcourir. »

### Remplir un document PowerPoint

**Ce qu'elle fait** — l'agent remplit un modèle PowerPoint que vous avez
déposé sur l'agent. Chaque emplacement à remplir est un repère placé dans une
diapositive et décrit dans les commentaires de celle-ci ; un repère peut
attendre du texte ou une image tirée d'un dossier de ressources.

**Ses limites** — l'agent remplit un modèle, il ne conçoit pas de
présentation : sans modèle déposé, la capacité ne fonctionne pas. Le modèle est
vérifié au dépôt et les erreurs de repérage vous sont signalées. Un agent
dupliqué conserve la configuration mais **pas le fichier du modèle**, qui est à
redéposer.

**Un exemple** — un modèle de revue mensuelle en cinq diapositives, que l'agent
remplit chaque mois à partir des documents de la période.

### Générer une page web (HTML/CSS)

**Ce qu'elle fait** — l'agent produit une page ou un composant web, affiché
dans un aperçu à côté de la conversation. L'aperçu se télécharge en HTML, PDF
ou image.

**Ses limites** — HTML et CSS uniquement : pas de JavaScript, donc rien
d'interactif. L'aperçu est en lecture seule et la page produite reste de taille
modeste ; au-delà, l'agent doit l'alléger. Ce n'est pas un outil de publication :
rien n'est mis en ligne.

**Un exemple** — « Présente ces indicateurs sous forme d'un tableau de bord
d'une page, que je puisse exporter en PDF. »

## Intelligence et orchestration

### Raisonnement

**Ce qu'elle fait** — ouvre dans les options de la conversation un mode où
l'agent prend le temps de décomposer le problème avant de répondre.

**Ses limites** — ce mode dépend du modèle utilisé et n'est pas proposé avec
tous. Les réponses sont plus lentes et plus coûteuses. Il apporte peu sur une
recherche simple, davantage sur une analyse en plusieurs étapes.

**Un exemple** — comparer deux offres sur une dizaine de critères et justifier
un classement.

## Actions et intégration

Cette section de l'onglet **Capacités** est prévue pour les capacités qui
agissent sur des systèmes extérieurs à la plateforme. Elle est vide aujourd'hui.

## En dehors des packs

La vue **Simple** présente des packs : des ensembles cohérents, activés d'une
seule bascule. La vue **Avancé** peut faire apparaître des capacités qui
n'appartiennent à aucun pack — notamment des capacités d'administration
réservées à des agents d'exploitation. Elles obéissent à la même règle que les
autres : votre équipe ne les voit que si l'administrateur les lui a ouvertes.
