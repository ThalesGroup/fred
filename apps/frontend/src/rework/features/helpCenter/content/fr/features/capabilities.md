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

### Documents

**Ce qu'elle fait** - l'agent lit et recherche dans les documents que vous lui
confiez. Deux packs choisissent où il regarde ; activez-en un ou les deux :

- **Pièces jointes** - les utilisateurs peuvent joindre des fichiers à la
  conversation (un trombone apparaît dans le chat). L'agent les lit, les résume
  et répond aux questions qui les concernent.
- **Documents de l'équipe** - l'agent recherche dans les documents de l'équipe
  et cite les passages utiles. Vous pouvez le limiter à certains dossiers.

Avec l'un ou l'autre pack, l'agent peut aussi lire un document mot à mot ou en
extraire une information sans rien omettre. Les façons de lire sont détaillées
sur [Les ressources](/help/fr/features/resources).

**Ses limites** - la recherche dans les documents de l'équipe ne voit que les
bibliothèques rattachées à l'agent. Une pièce jointe reste dans sa conversation
et n'est jamais ajoutée aux documents de l'équipe. La recherche remonte les
passages qu'elle juge pertinents : elle est rapide, mais pas exhaustive. La
comparaison de documents ne fonctionne que sur les documents de l'équipe : elle
vient donc avec le pack **Documents de l'équipe**.

Le mode **Documents uniquement** utilise les sources documentaires autorisées par l'agent, pièces jointes comprises. Voir [Les conversations](/help/fr/features/chat#choisir-les-sources-de-la-reponse).

**Exemples** - avec **Pièces jointes** seulement, joindre un contrat et demander
à l'agent d'en relever les échéances. Avec **Documents de l'équipe**, demander
ce que prévoient les procédures de l'équipe pour un incident.

Cette capacité en regroupe plusieurs, que la vue **Avancé** sépare :

| Fonction                          | Ce qu'elle fait                                                                | À savoir                                                                                                           |
| --------------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| Documents                         | Recherche dans les pièces jointes, les documents de l'équipe, ou les deux      | Peut afficher un trombone et un sélecteur de bibliothèque ou de document dans la conversation                      |
| Exploiter les fichiers tabulaires | Interroge les fichiers tabulaires des bibliothèques et les CSV ou Excel joints | Les nouveaux CSV et Excel joints sont interrogeables en SQL ; les anciens Excel peuvent n’avoir qu’un aperçu texte |
| Résumer un document               | Produit le résumé d'un document                                                | Demande votre confirmation avant chaque résumé ; longueur réglable                                                 |
| Comparer des documents            | Retrouve les passages proches d'un passage donné                               | Travaille sur les documents de l'équipe, jamais sur une pièce jointe                                               |
| Verbatim document                 | Restitue le texte exact, page par page                                         | Les pages renvoyées ont une longueur limitée                                                                       |
| Extraction d'information          | Parcourt le document entier sans rien omettre                                  | La plus lente et la plus coûteuse ; confirmation demandée par défaut                                               |

Utilisez les outils tabulaires pour lire les tableaux complets des CSV et Excel
joints ; les outils de lecture documentaire sont destinés aux pièces jointes
textuelles.

En mode **Simple**, désactiver un pack conserve ce que l'autre utilise encore ;
désactiver les deux retire la capacité **Documents**. En mode **Avancé**, la
carte **Documents** commence par les interrupteurs **Pièces jointes** et
**Documents de l'équipe** : si vous désactivez les deux, la carte se
désactive. Les agents existants conservent leurs réglages tant que vous ne les
modifiez pas.

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

**Ce qu'elle fait** — l'agent remplit un template PowerPoint que vous avez
déposé sur l'agent. Chaque emplacement à remplir est un repère placé dans une
diapositive et décrit dans les commentaires de celle-ci ; un repère peut
attendre du texte ou une image tirée d'un dossier de ressources.

**Ses limites** — l'agent remplit un template, il ne conçoit pas de
présentation : sans template déposé, la capacité ne fonctionne pas. Le template est
vérifié au dépôt et les erreurs de repérage vous sont signalées. Un agent
dupliqué ou copié dans une autre équipe emporte son propre exemplaire du template.

**Un exemple** — un template de revue mensuelle en cinq diapositives, que l'agent
remplit chaque mois à partir des documents de la période.

### Générer une présentation

**Ce qu'elle fait** — l'agent construit une présentation PowerPoint à partir de
votre demande, sur le template de votre entreprise ou, à défaut, sur un template
intégré. Pour chaque diapositive, il choisit la diapositive du template qui
convient le mieux au contenu et la remplit ; les chiffres deviennent des
graphiques modifiables, aux couleurs du template. La présentation s'affiche dans un
aperçu à côté de la conversation et se télécharge en `.pptx`. Le bouton
d'information à côté du téléchargement montre **Ce qui a été construit** :
chaque diapositive, son type, et ce qui a été raccourci, laissé de côté ou
continué sur une autre diapositive.

**Comment la configurer** — déposez un template `.pptx` sur l'agent et
enregistrez. Le template est alors lu en arrière-plan : pendant ce temps,
l'agent affiche **En préparation** et n'est pas encore disponible ; il le
devient tout seul quand la lecture est terminée, et vous pouvez fermer la
fenêtre en attendant. Ensuite, **Vérifier les slides** montre chaque
diapositive trouvée, avec son nom et son type : renommez une diapositive,
changez son type ou mettez-la de côté. Rien n'est obligatoire.
Pour préparer un template que l'agent comprend bien, voir
[Préparer son template PowerPoint](/help/fr/guides/prepare-powerpoint-template).

**Utiliser un modèle de vision** — quand un modèle d'IA capable de lire les
images est disponible, il regarde chaque diapositive du template pour
la nommer et comprendre à quoi elle sert. Vous pouvez choisir le modèle
d'IA qui s'en charge, ou garder celui de l'agent. Sans un tel modèle d'IA,
l'interrupteur est verrouillé et
les diapositives sont nommées par des règles : cela fonctionne, mais les noms
sont moins précis.

**Forcer de la variété** — limite le nombre de fois qu'une même diapositive
revient dans une présentation. **Par nom de slide** (par défaut) : chaque
diapositive du template sert au plus le nombre de fois choisi. **Par type de slide
identifié** : chaque type (des listes à puces, par exemple) revient au plus ce
nombre de fois, même sur des diapositives différentes. Avec **1**, chaque
diapositive est différente ; avec **2** (par défaut), une diapositive peut
revenir une fois. Des sections construites pareil (une par pays, par exemple)
peuvent reprendre la même diapositive au même endroit, comme la deuxième
diapositive de chaque pays. Quand le template contient trop peu de diapositives pour la
présentation demandée, l'agent fait au mieux. Sur la première présentation
d'une conversation, l'agent est invité à revoir celles qui se répètent trop.
Interrupteur coupé : aucune limite. Le changement vaut dès la présentation
suivante, sans relire le template.

**Ses limites** — l'agent n'utilise que les diapositives que le template
contient : il n'en dessine pas de nouvelles. Quand un contenu ne tient dans
aucune diapositive (trop d'éléments, par exemple), il le découpe ou le
raccourcit. Si la lecture du template échoue, l'agent reste indisponible : le
formulaire en donne la raison, avec un bouton **Relancer l'analyse**.

**Un exemple** — « Prépare une présentation de dix diapositives sur nos
résultats trimestriels pour le comité de direction. »

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

**Ce qu'il fait** — un mode où l'agent prend le temps de décomposer le
problème avant de répondre. Ce n'est pas une capacité à activer sur l'agent :
il suit le modèle de langage choisi, et se règle dans la conversation (voir
[Les conversations](/help/fr/features/chat#choisir-le-modele-et-le-raisonnement)).

**Ses limites** — il n'est proposé qu'avec les modèles pour lesquels
l'administrateur l'a activé. Les réponses sont plus lentes et plus coûteuses. Il apporte peu sur une
recherche simple, davantage sur une analyse en plusieurs étapes.

**Un exemple** — comparer deux offres sur une dizaine de critères et justifier
un classement.

## En dehors des packs

La vue **Simple** présente des packs : des ensembles cohérents, activés d'un
clic sur leur carte. La vue **Avancé** peut faire apparaître des capacités qui
n'appartiennent à aucun pack — notamment des capacités d'administration
réservées à des agents d'exploitation. Elles obéissent à la même règle que les
autres : votre équipe ne les voit que si l'administrateur les lui a ouvertes.

Certains agents, comme les agents à parcours guidé, viennent avec leurs
capacités et ne proposent pas de packs. Le formulaire les liste sous **Inclus
avec cet agent** : elles restent actives, et vous y réglez leurs options, par
exemple pour lier l'agent à des bibliothèques précises.
