---
title: Préparer son template PowerPoint
order: 40
description: Ce qui fait un bon template pour la génération de présentations, et comment le faire comprendre à l'agent.
icon: slideshow
---

# Préparer son template PowerPoint

Cette page s'adresse à ceux qui conçoivent le template d'une équipe et à ceux
qui le déposent sur un agent (capacité **Générer une présentation**, voir
[Les capacités](/help/fr/features/capabilities)).

L'agent ne dessine rien : il **copie les diapositives de votre template** et
remplace leur texte. La qualité des présentations dépend donc directement du
template. Les règles ci-dessous suivent ce que la lecture du template fait
réellement.

## Comment le template est lu

Après l'enregistrement de l'agent, le template est lu une fois, en
arrière-plan. Pour chaque diapositive, cette lecture repère les zones à
remplir, mesure la place qu'offre chacune et reconnaît à quoi sert la
diapositive (son **type** : couverture, sommaire, cartes…).

- **Les diapositives d'exemple d'abord.** Les diapositives du fichier sont ce
  que l'agent réutilise, avec toute leur décoration. Les **masques** ne servent
  qu'en dernier recours, quand aucune diapositive ne convient. Une diapositive
  qui reprend simplement son masque le remplace.
- **Le modèle de vision**, s'il est activé, regarde une image de chaque
  diapositive d'exemple : il la nomme, choisit son type et comprend le rôle de
  chaque zone. Il peut aussi juger qu'une diapositive est à usage unique (un
  organigramme précis, une mention légale) : l'agent ne la réutilise pas. Il ne
  décide jamais de la place disponible : elle est mesurée. Sans modèle de
  vision, des règles font ce travail, avec des noms moins précis.

## Une diapositive par mise en page

Mettez chaque mise en page **une seule fois**, remplie d'un texte d'exemple.
Une deuxième copie de la même mise en page n'apporte rien. En revanche,
plusieurs variantes d'un même type (trois cartes, quatre cartes, cartes avec
icônes) donnent à l'agent de quoi varier ses présentations.

## Les types reconnus

Le mot entre parenthèses est celui à écrire dans une note (voir plus bas).

| Type                             | Ce que la diapositive doit contenir                        |
| -------------------------------- | ---------------------------------------------------------- |
| Couverture (`cover`)             | Un titre. Toujours en première position de la présentation |
| Sommaire (`agenda`)              | Des entrées répétées (numéro et intitulé)                  |
| Section (`section`)              | Un titre                                                   |
| Liste à puces (`bullets`)        | Un titre et une zone de texte                              |
| Deux colonnes (`two_columns`)    | Deux zones de texte                                        |
| Comparaison (`comparison`)       | Deux zones de texte ou plus, côte à côte                   |
| Cartes (`cards`)                 | Des éléments répétés, chacun avec un intitulé et un texte  |
| Chiffres clés (`figures`)        | Des éléments répétés avec un chiffre                       |
| Processus (`process`)            | Des étapes répétées                                        |
| Frise chronologique (`timeline`) | Des jalons répétés                                         |
| Équipe (`team`)                  | Des personnes répétées (nom, rôle)                         |
| Citation (`quote`)               | La citation et son auteur                                  |
| Image et texte (`image_text`)    | Une image et un texte en plus du titre                     |
| Tableau (`table`)                | Un tableau à remplir                                       |
| Graphique (`chart`)              | Une zone de graphique, ou un à quatre graphiques           |
| Conclusion (`closing`)           | Remerciements ou contacts. Toujours en dernière position   |
| Autre (`other`)                  | L'agent ne s'en sert pas                                   |

La première diapositive du fichier, si elle a un titre et pas de texte de
corps, est lue comme la couverture.

## Dire à l'agent ce qu'est une diapositive

Trois moyens, du plus fort au plus faible :

1. **Une note.** Dans les notes de la diapositive, chacune sur sa propre ligne :
   `kind: cards` pour le type, `label: Trois cartes avec icône` pour le nom. Ce
   que dit une note n'est jamais remplacé par le modèle de vision.
2. **Un titre ou un nom parlant.** Un titre court, le nom du masque ou le nom
   d'une forme qui dit le type est reconnu : « Sommaire », « Agenda »,
   « Chronologie », « Roadmap », « Processus », « Étapes », « Chiffres clés »,
   « Équipe », « Citation », « Section », « Merci », « Contact »…
3. **Le nom des formes.** Dans le volet Sélection de PowerPoint, nommez une
   forme d'après son rôle : `titre`, `sous-titre`, `corps` ou `texte`,
   `entete`, `legende`, `valeur` ou `numero`, `libelle`, `image` ou `photo`.
   `fixe` ou `decor` laisse une forme telle quelle. Un suffixe est permis après
   `_` ou `-` (`texte_gauche`). Les noms automatiques (« ZoneTexte 12 ») ne
   disent rien.

## Les éléments répétés

Cartes, étapes, chiffres clés, entrées de sommaire : l'agent les reconnaît
quand ils sont construits à l'identique.

- **Groupez chaque élément** (ses textes, son icône) et placez au moins trois
  groupes de même structure : mêmes tailles de police, même nombre d'images.
- **Ou alignez des zones de texte identiques** : trois côte à côte, ou deux
  avec une deuxième rangée alignée dessous (le chiffre au-dessus de son
  libellé). Même taille, même police, même graisse.
- Une zone plus large qu'un tiers de la diapositive est lue comme une colonne,
  pas comme un élément.
- **Prévoyez le nombre maximal d'éléments** : l'agent retire ceux qui sont en
  trop et recentre les autres, il n'en ajoute jamais.
- Les icônes restent celles du template ; une icône part avec son élément.
- Un chiffre clé peut afficher devant lui une petite flèche de hausse, de
  baisse ou de stabilité, dans la police et la couleur du chiffre : rien à
  préparer.

## Laisser de la place au texte

La place de chaque zone est mesurée d'après sa taille, ses marges, sa police
et son interligne. L'agent en est informé (« environ 40 caractères sur
3 lignes ») et écrit à cette mesure.

- **Une zone ajustée à deux mots donne deux mots.** Dimensionnez chaque zone
  pour le texte que vous attendez vraiment.
- **Écrivez un texte d'exemple réaliste**, à la taille finale : il sert à
  affiner la mesure. Variez-le d'une diapositive à l'autre.
- Un texte identique sur plusieurs diapositives (pied de page, mention de
  confidentialité), la date et le numéro de diapositive ne sont jamais remplis.

## Les images

- Une zone d'image est un espace réservé pour image, une image qui couvre au
  moins un quart de la diapositive, ou une image nommée `image` ou `photo`.
  Les images plus petites (logos, icônes) sont de la décoration.
- Si le masque dessine un cadre ou un bandeau derrière une zone d'image, la
  diapositive n'est choisie que lorsque l'agent a des images à y placer :
  sinon, le cadre resterait vide.

## Les tableaux

Un tableau est rempli quand c'est un vrai tableau de données :

- un seul tableau par diapositive, qui en occupe une bonne partie, avec au
  moins deux colonnes ;
- **aucune cellule fusionnée** ;
- des cellules vides ou en texte d'exemple, sans couleur différente d'une
  cellule à l'autre (laissez le style de tableau colorer).

Le nombre de lignes affichées fixe ce que le tableau peut contenir. L'agent
peut retirer des colonnes (il en garde au moins deux) et ajouter ou retirer
des lignes dans la hauteur du tableau.

Une ligne de total et une ligne ou colonne à faire ressortir suivent aussi le
style de tableau : l'apparence que le style prévoit pour une ligne de total
(du gras s'il n'en prévoit pas), et un texte en gras sur une teinte claire de
la couleur du style pour la ligne ou la colonne. Choisissez un style de
tableau qui affiche une ligne de total si vos tableaux se terminent souvent
par un total.

## Les graphiques

L'agent transforme les chiffres d'une demande en un vrai graphique PowerPoint
(barres, histogramme, courbes, secteurs, anneau, histogramme ou barres
empilés, aires, radar, et nuages de points ou bulles qui relient deux ou trois
mesures), qui reste modifiable dans PowerPoint.

- **Prévoyez une diapositive de graphique** : un masque avec un espace réservé
  de graphique, ou une diapositive d'exemple avec un graphique qui en occupe
  une bonne partie. Une zone de texte à côté du graphique reçoit un court
  commentaire ; ajoutez une seconde diapositive de graphique sans cette zone
  pour les graphiques qui se passent de commentaire.
- **Le template décide de l'apparence** : le graphique prend les couleurs
  d'accentuation du thème, dans l'ordre, et sa police de corps. Pour changer
  les couleurs de tous les graphiques, changez les couleurs d'accentuation du
  thème. Si votre graphique d'exemple est déjà du type demandé (par exemple
  des barres pour un graphique en barres), sa mise en forme est conservée ;
  sinon le graphique est reconstruit avec l'apparence du template.
- **Plusieurs graphiques côte à côte** : une diapositive d'exemple peut
  contenir deux, trois ou quatre graphiques, chacun couvrant au moins un
  vingtième de la diapositive. L'agent les remplit tous, de gauche à droite
  puis de haut en bas, et n'utilise cette diapositive que s'il a exactement
  autant de graphiques à montrer ; chaque graphique a son propre titre. Une
  zone de texte placée juste au-dessus d'un graphique affiche le titre de ce
  graphique. Prévoyez une diapositive d'exemple pour chaque nombre de
  graphiques souhaité ; pour un autre nombre, l'agent répartit ses graphiques
  sur plusieurs diapositives ou les regroupe.
- Sans diapositive de graphique, une grande zone de contenu (celle du masque
  « Titre et contenu » de PowerPoint) reçoit le graphique quand la diapositive
  n'a pas d'autre texte.
- L'agent ne dessine jamais un graphique ailleurs, et demande moins de
  catégories ou des libellés plus courts plutôt que de les tasser.

## Les messages clés sur les diapositives

Le message clé de chaque diapositive, ce que le public doit en retenir, va
dans les notes de l'orateur. Pour que l'agent l'affiche aussi sur la
diapositive quand on le lui demande (« affiche les messages clés sur les
slides »), nommez la zone de texte prévue pour lui `message clé`, `à retenir`
ou `takeaway` dans le volet Sélection de PowerPoint, ou sur son masque. Sans
cette demande, la zone est remplie comme toute autre zone de texte. Avec elle,
l'agent préfère une diapositive qui a une telle zone. Un message clé qui ne
peut pas être affiché, trop long pour la zone ou sur une diapositive sans zone,
reste dans les notes de l'orateur, et **Ce qui a été construit** le signale.

## Ce qui est mis de côté

Ces diapositives restent visibles dans **Vérifier les slides**, avec la raison :

| Raison affichée      | Ce qui la provoque                                                                         |
| -------------------- | ------------------------------------------------------------------------------------------ |
| Graphique            | Plus de quatre graphiques sur la diapositive, ou un graphique dans un groupe               |
| Tableau              | Un tableau qui n'est pas un tableau de données (cellules fusionnées, couleurs par cellule) |
| Banque d'icônes      | Une vingtaine d'images ou plus, sans texte                                                 |
| Non copiable         | Un SmartArt, un très petit graphique ou un objet incorporé (Excel…)                        |
| Aucun espace réservé | Un masque sans rien à remplir                                                              |
| Exclu par vous       | Vous l'avez mise de côté                                                                   |

Un SmartArt peut être converti en formes dans PowerPoint : la diapositive
devient alors utilisable.

## Vérifier le résultat

**Vérifier les slides** présente les diapositives retenues, les masques et les
diapositives mises de côté. Vous pouvez renommer une diapositive (son nom aide
l'agent à choisir), changer son type, la mettre de côté ou la reprendre. Donner
un autre type à une diapositive Autre permet à l'agent de s'en servir, comme
une note `kind:`. La mention **Nommée par des règles** signale une diapositive que le modèle de
vision n'a pas lue.

## Après une modification du template

Déposez le fichier modifié et enregistrez l'agent : le template est relu en
entier, et l'agent reste indisponible pendant la lecture. Redéposer le même
fichier garde la lecture précédente. Activer ou couper le modèle de vision, ou
en changer, relance aussi la lecture. Les corrections faites dans **Vérifier
les slides** ne sont gardées que pour les diapositives toujours présentes ;
les notes et les noms de formes, eux, voyagent avec le fichier.

## En résumé

| À faire                                                       | À éviter                                        |
| ------------------------------------------------------------- | ----------------------------------------------- |
| Une diapositive d'exemple par mise en page                    | Plusieurs copies de la même mise en page        |
| Une note `kind:` quand le type n'est pas évident              | Laisser des diapositives en type Autre          |
| Des éléments répétés groupés ou alignés à l'identique         | Des cartes de tailles ou de polices différentes |
| Le nombre maximal d'éléments que vous voulez voir             | Compter sur l'agent pour ajouter une carte      |
| Des zones de texte à la taille du texte attendu               | Des zones ajustées à deux mots                  |
| Un texte d'exemple réaliste, différent sur chaque diapositive | Le même texte d'exemple partout                 |
| Des tableaux simples, sans fusion ni couleur par cellule      | Un planning dessiné en cellules colorées        |
| Les SmartArt convertis en formes                              | Des objets incorporés à remplir                 |
| Jusqu'à quatre graphiques par diapositive, assez grands       | Cinq graphiques ou plus sur une diapositive     |
