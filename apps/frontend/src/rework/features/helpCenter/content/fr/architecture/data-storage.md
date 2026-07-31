---
title: Où vivent les données
order: 20
description: Les différents magasins de données et ce qu'ils contiennent.
icon: database
---

# Où vivent les données

La plateforme répartit les données entre plusieurs **magasins**, chacun adapté à
un type d'information :

- **Un magasin de fichiers** conserve vos documents d'origine (les fichiers que
  vous déposez et ceux produits par les agents).
- **Un magasin vectoriel** contient l'**index** de recherche : la représentation
  des documents qui permet aux agents de retrouver les passages pertinents et de
  citer leurs sources.
- **Une base de métadonnées** garde la trace des équipes, agents, prompts,
  sessions et documents — le « qui, quoi, où » qui structure la plateforme.
- **Le fournisseur d'identité et le service de permissions** gèrent
  respectivement les comptes et les droits d'accès.

Cette séparation explique certaines opérations d'administration, comme l'**audit
du corpus**, qui vérifie la cohérence entre le magasin de fichiers, l'index
vectoriel et les métadonnées (voir
[Console d'administration](/help/fr/features/admin)).

> Le détail exact (technologies, hébergement) dépend de la configuration de
> votre déploiement.
