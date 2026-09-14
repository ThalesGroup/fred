# TEST DE SURCHARGE DU THÈME - ceci ne remplace pas de vraies conditions générales d'utilisation

**Si vous lisez cette page, l'overlay de thème fonctionne.** Ce texte est servi
depuis une archive de thème stockée en objet, pas depuis l'image du frontend.
Rien n'a été reconstruit ni forké pour l'afficher.

Ce qui s'est passé, dans l'ordre :

1. Le conteneur a démarré et récupéré l'archive depuis `FRONTEND_THEME_URL`.
2. Il a extrait `gcu.fr.md` dans le répertoire d'overlay, hors de la racine web.
3. nginx sert désormais ce fichier à la place de celui embarqué dans l'image.

**Remplacez ce fichier avant qu'un vrai utilisateur ne le voie.** Il se trouve
dans `apps/frontend/theme/gcu.fr.md` et n'existe que pour rendre l'archive
complète et la surcharge vérifiable de bout en bout.

Gardez `gcu.md` à côté. L'application demande d'abord `gcu.<langue>.md` : sans
cette variante française, le texte d'origine l'emporterait alors même que le
thème est correctement installé.
