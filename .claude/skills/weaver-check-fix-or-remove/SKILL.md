---
name: weaver-check-fix-or-remove
description: Examiner la pertinence des tests Fred pendant la migration Weaver et ReBAC, puis corriger le code, adapter ou supprimer les tests selon les contrats encore valides. Utiliser pour des échecs de tests ou une demande ciblée de tri des tests de migration, sans déclencher un audit général.
---

# Weaver : vérifier la pertinence avant de réparer

Le résultat attendu est une couverture utile du comportement convenu pour Fred.
Un test vert ne suffit pas : ne pas préserver un mécanisme Swift abandonné,
ni supprimer une garantie encore nécessaire parce que son test échoue.

Lire `AGENTS.md` et `fred-reconstruction-method` du checkout actif. Appliquer
la réduction du code de production, la réutilisation et la suppression des chemins
remplacés, sans affaiblir les garanties ni supprimer des tests utiles.

## Établir le contrat

- Localiser le checkout demandé, lire ses instructions applicables et les skills
  qu'elles imposent. Utiliser les chemins du checkout actif, sans chemin Fred
  personnel figé. Vérifier la branche et les modifications déjà présentes.
- Partir des échecs fournis et annoncer un lot limité. Lire les assertions,
  fixtures, mocks, contrats producteurs et consommateurs, et le chemin réellement
  exécuté. Remonter au premier échec causal derrière une erreur HTTP générique.
- Formuler ce que chaque test protège, indépendamment de son implémentation.
  Distinguer le comportement actuel observé, la cible Weaver acceptée et le
  comportement Swift historique. Consulter les décisions pertinentes du dépôt ;
  ni le code actuel ni une ancienne spécification ne suffisent seuls à établir
  le comportement attendu. Une cible écrite n'est pas un parcours déjà intégré.
- Une lacune de migration n'est pas une obsolescence. Si l'attendu reste ambigu,
  préciser la décision manquante et avancer sur les cas indépendants.

## Choisir et appliquer

| Diagnostic étayé | Action |
| --- | --- |
| Garantie toujours requise, code en régression | Corriger le code et conserver une assertion qui détecte la régression. |
| Garantie utile, fixture ou assertion liée à un ancien contrat | Adapter le test au contrat Weaver réel en préservant sa portée. |
| Comportement explicitement abandonné, sans garantie résiduelle | Supprimer le test et les seules fixtures devenues inutilisées. |
| Couverture réellement redondante | Fusionner ou supprimer en identifiant le test conservé et les cas qu'il couvre. |
| Environnement ou dépendance défaillante | Corriger la configuration de test dans le lot, ou signaler le blocage sans changer l'attendu métier. |
| Fonction requise mais migration incomplète | Rendre l'écart explicite ; ne pas déclarer le test obsolète ni implémenter toute la migration hors du lot. |

Une demande « check and fix or remove » demande l'application des corrections
justifiées dans le lot, pas seulement un rapport. Une demande de diagnostic seul
reste en lecture seule. Respecter les changements en cours des autres auteurs.

Avant une suppression, rechercher les usages statiques et dynamiques pertinents
(enregistrement, configuration, routes, identifiants). Identifier la décision qui
abandonne le comportement ou la couverture qui le remplace. Préserver les cas
négatifs utiles et toute garantie de sécurité portée par un ancien test.
L'absence d'implémentation Weaver ne prouve pas que la garantie a disparu.

Pour ReBAC, préserver les garanties aux frontières convenues : identité fiable,
délégation, isolation, admission, accès aux ressources et cycle de vie. Relire
les arbitrages actuels du dépôt sur leur temporalité ; ne pas recopier une
ancienne stratégie de vérification dans le nouveau modèle.

## Éviter les faux correctifs

- Ne pas affaiblir une validation de production ou ajouter un défaut permissif
  pour accepter une réponse simulée incomplète. Vérifier aussi le producteur réel.
- Simuler les dépendances externes au bon niveau. Ne pas court-circuiter le
  mécanisme que le test prétend vérifier, notamment l'admission ou le streaming.
- Ne pas recréer de fallback Swift, d'alias ou de chemin d'autorisation parallèle
  pour sauver un test hérité.
- Ne pas remplacer un échec par `skip`, `xfail` ou une assertion plus faible pour
  obtenir du vert. Distinguer les échecs des `xfail` attendus ; n'étendre l'examen
  à ces derniers que s'ils expliquent le problème ou font partie de la demande.
  Un problème amont doit avoir une preuve et une condition de réexamen précises.
- Réutiliser une fixture partagée lorsqu'elle est accessible et adaptée ; ne pas
  ajouter une abstraction ou un import entre suites seulement pour une ligne.

## Vérifier et restituer

Appliquer le formatage et les contrôles qualité exigés par le dépôt. Respecter
son périmètre d'exécution des tests et la demande de l'utilisateur : une relance
autorisée commence par les tests concernés et les voisins affectés, sans campagne
générale automatique. Si les tests ne sont pas exécutés, le dire explicitement.

Rendre un bilan court : test ou groupe, garantie protégée, décision et preuve,
fichiers changés, commandes réellement exécutées et résultats. Pour une
suppression, indiquer la couverture conservée ou pourquoi elle n'a plus lieu
d'être. Séparer diagnostic statique, réussite des tests et validation produit.
Ne pas recréer de workflow RFC ou de journal parallèle. Un commit ou une PR
requiert l'autorisation de l'utilisateur.
