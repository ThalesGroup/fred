# NOTES — Ingestion task tracking: reste à faire

Le détail de ce qui a été livré (root cause, décisions, fichiers touchés, tests) est
documenté dans `docs/swift/backlog/BACKLOG.md` §OPS-04 P4 et
`docs/swift/data/id-legend.yaml` (entrée OPS-04) — ne pas dupliquer ici. Ce fichier
ne garde que ce qu'il reste à vérifier en live. À supprimer une fois tout coché
et la branche mergée.

## Reste à faire

- [ ] **Confirmer que Marc (team_admin, fredlab) voit désormais les tâches
      d'ingestion de Bob dans l'Activité à portée équipe**, après réingestion d'un
      document frais (les tâches créées avant le fix `team_id` restent invisibles
      côté équipe — normal, pas de backfill fait).
- [ ] **Confirmer visuellement que l'anneau de progression tourne bien du début à
      la fin** (ne se fige plus à 30%) — nécessite que le worker Temporal ait bien
      rechargé `workflow.py` (redémarrage déjà fait par le développeur, à confirmer
      à l'usage).
- [ ] Optionnel : arrêter/bloquer Temporal en cours de test pour vérifier que le
      nouveau timeout (`rpc_timeout_seconds`) échoue proprement la tâche au lieu de
      figer la modale — pas fait, pas bloquant.
- [ ] Une fois tout ce qui précède vérifié et la branche mergée : supprimer ce
      fichier.
