---
title: Problèmes de documents
order: 30
description: Ingestion en échec, document jamais cité, format non supporté.
icon: folder
---

# Problèmes de documents

## L'ingestion échoue ou reste bloquée

Après le dépôt, un document passe par les statuts **En attente** →
**Traitement** → **Prêt**. S'il reste bloqué ou affiche **Erreur** :

- **Patientez** : l'ingestion d'un gros document prend du temps.
- **Vérifiez le format** : un fichier corrompu ou d'un type non pris en charge
  échoue (voir [Lenteurs et limites](/help/fr/troubleshooting/limits)).
- **Redéposez** le document si l'erreur persiste.

## Un document n'est jamais cité

- **Statut** : seuls les documents **Prêt** sont exploitables. Vérifiez qu'il
  n'est pas resté en traitement.
- **Emplacement** : un fichier hors bibliothèque, au niveau supérieur, **n'est
  pas indexé**. Placez-le dans une bibliothèque du corpus d'équipe.
- **Exclusion** : vérifiez qu'il n'est pas marqué **Exclu de la recherche**.
- **Rattachement à l'agent** : assurez-vous que la bibliothèque est bien
  rattachée à l'agent que vous interrogez (voir
  [Les agents](/help/fr/features/agents)).

## Le format n'est pas supporté

Les formats courants sont pris en charge (PDF, texte, PPT, Excel/CSV, Markdown).
Un format exotique peut être refusé : convertissez le document dans un format
courant avant de le déposer.
