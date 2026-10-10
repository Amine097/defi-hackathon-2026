# FaultLine — Audit du frontend actuel

_10 octobre 2026 · commit `a2d10c1` · périmètre : `public/` (dashboard + X-Ray) et son contrat avec `/api/analyze`._

> **Status after frontend v2** (same day): constats 1, 3, 5, 6, 7, 8, 10, 11, 13, 15, 16, 17 and the contrast / duplicated-token / gradient points are addressed; 2 is mitigated (the point comparison is labelled); 4 was fixed in the engine by a teammate; 9 is partly addressed (`liquidation` is now shown, `sensitivity` and `stress_table` are not). Evidence: [`UI_QA_REPORT.md`](UI_QA_REPORT.md).

## 1. Verdict

Le frontend est une démo crédible et fonctionnelle : le X-Ray (graphe + simulation de panne + décision) fait déjà le travail du « moment fort » et l'étiquetage live / cache / mock est pris au sérieux. Il est en revanche loin de la cible décrite dans [`frontend.md`](frontend.md) sur trois points :

1. **Cohérence des chiffres.** Les deux pages se contredisent sur la provenance des données, formatent les mêmes montants différemment, et le X-Ray recalcule un verdict STAY/EXIT côté client qui peut contredire celui du moteur.
2. **Breaking Point absent.** La pièce maîtresse de la spec (choc minimal jusqu'à la première liquidation) n'a aucun écran. Le backend expose pourtant déjà `liquidation`, `stress_table`, `sensitivity`, `uncertainty`, `var95_usd`, que l'UI n'affiche pas.
3. **Direction visuelle.** L'existant est une landing page « crypto » (dégradés, halos, fond étoilé) et non le terminal de risque sobre demandé.

Priorité recommandée : corriger les incohérences de chiffres (§3, P0) avant toute refonte visuelle. Ce sont les seules qui peuvent coûter de la crédibilité devant un jury.

## 2. Méthode et limites

- Lecture complète de `index.html`, `xray.html`, `theme.css`, `api.js`, `shell.js`, `xray.js`, `xray/{data,model,chart,util}.js` ; lecture partielle de `xray/graph.js` et `xray.css`.
- Rendu dans Chrome headless à 1440×900 et 390×844, servi par un serveur statique. `/api/analyze` y répond 404, donc **seul le chemin de repli (snapshot `data/sample.json`) et `?data=large` ont été rendus**.
- Interactions réellement exécutées : chargement, scénario 1 (touche `1`), bascule Force/Layers.

Non vérifié : l'API live (et donc les badges `live`/`cache`/`mixed`), le mode emprunteur (`?borrower=`), les sliders, le drawer, le tactile, un lecteur d'écran, Safari/Firefox. Les constats marqués _(code)_ viennent de la lecture du code, pas d'une exécution.

## 3. Constats

### P0 — crédibilité des chiffres

| # | Constat | Où | Correction |
|---|---|---|---|
| 1 | **Même fichier, deux étiquettes opposées.** Hors ligne, le dashboard affiche le badge rouge « MOCK (API offline) » (infobulle : « numbers are not real ») et le X-Ray affiche « REAL DATA SNAPSHOT · 2026-10-10 » pour le même `sample.json`, qui est bien un run réel (`source: "live"`). Observé au rendu. | `api.js:61`, `xray.js:75-80` | Une seule fonction de badge partagée ; reprendre la logique du X-Ray (snapshot réel ≠ mock). |
| 2 | **Verdict recalculé côté client.** Dès qu'on touche le slider « Exit cost », le verdict devient un binaire `stay > exit`, sans le REVIEW ni le carry du moteur. Sur le snapshot : le moteur dit REVIEW, penche STAY (exit avec carry ≈ $4.9k) ; le slider à 0,1 % donne EXIT ($1.7k > $1.0k). _(code)_ | `xray.js:358`, `xray.js:412`, `model.js` `positionLosses` | Soit le slider appelle l'API (`severity`/coût), soit le résultat est étiqueté « what-if client, hors carry » et ne remplace pas le badge du moteur. |
| 3 | **Les KPI contredisent le verdict affiché.** « Expected loss $1.7k / Cost if exit $1.2k / Margin +$412, stay costs more » en rouge, sous un verdict qui penche STAY. Le coût de sortie affiché est l'exécution seule ; la décision utilise exécution + carry ($4.9k). Idem sur le dashboard ($1,657 vs $1,246). Observé. | `xray.js:356-357`, `index.html` KPI `k-exit` | Afficher `exit_band.central_usd` avec le détail exécution + carry, ou deux lignes distinctes ; calculer la marge sur la même base que le verdict. |
| 4 | **Table des pockets en contradiction avec le verdict.** Sur le snapshot, les 10 pockets sont marquées EXIT (dont 9 non touchées, $1,657 vs $1,246), juste sous un verdict REVIEW pour la même position. | payload `book.pockets[].verdict` (backend `portfolio`), rendu `index.html`, `xray.js` `renderBook` | Côté moteur : appliquer aux pockets la même règle de bandes que la décision principale. À défaut, masquer la colonne. |
| 5 | **Deux formateurs de montants.** $1,657 sur le dashboard, $1.7k sur le X-Ray ; $12.5k contre $12k. De plus `fmtUsd` rend `$0` pour une valeur absente, alors que `usd()` rend `—`. | `api.js:28`, `util.js` `usd` | Un seul module de formatage ; jamais `0` pour une donnée manquante. |
| 6 | **« Live » sans preuve de fraîcheur dans le X-Ray.** Le badge dit « Fetched now » avec un point clignotant, alors que la réponse peut sortir du cache CDN (`s-maxage=60`, égal au seuil de péremption du quote). `decision.freshness` et `decision.confidence` ne sont lus que par la ligne grise du dashboard. _(code)_ | `xray.js:59`, `api/analyze.py:62` | Afficher l'âge réel (`data_as_of`, `freshness.label`) à côté du badge sur les deux pages. |

### P1 — fonctionnel et UX

| # | Constat | Où |
|---|---|---|
| 7 | **Paramètres d'URL perdus.** Le dashboard transmet toute la query à l'API ; le X-Ray ne transmet que `ref`. `?borrower=auto`, `value_usd`, `shock`, `severity` sont ignorés sur le X-Ray, et le lien « Open X-Ray » ne les propage pas. _(code)_ | `api.js:24`, `data.js:34`, `index.html:62` |
| 8 | **Liquidation quasi invisible.** Le mode emprunteur (HF, distance à la liquidation) n'apparaît que dans une phrase grise du dashboard ; rien dans le X-Ray. | `api.js` `signalDetails` |
| 9 | **Champs du payload jamais affichés** : `stress_table`, `sensitivity`, `uncertainty`, `assumptions`, `provenance`, `var95_usd`, `mc_mean_usd`, `custom_shock`, `decision.reasons`, `decision.top_drivers`. La méthodologie parle d'une VaR95 Monte Carlo que l'UI ne montre nulle part. | payload vs `public/` |
| 10 | **Le guide masque le graphe à la première visite.** Une modale couvre la vue au chargement : c'est ce que verra un jury sur un navigateur neuf. Elle n'a ni piège de focus ni fermeture par `Esc` (`Esc` désélectionne un nœud). Observé. | `xray.html:59`, `xray.js:82-89`, `xray.js:185` |
| 11 | **Sélecteur de source trompeur.** Il reste sur « Live API » alors que la page affiche le snapshot de repli. Observé. | `xray.js:24` |
| 12 | **Libellés qui se chevauchent dans le graphe.** Déjà à 11 nœuds (« Morpho market… » sur « Pendle market… ») ; à 44 nœuds, illisible en Force comme en Layers. En Layers, les nœuds ne semblaient pas tous dans leur bande à la capture : à confirmer à la main. | `graph.js` (rendu des labels) |
| 13 | **Verdict du dashboard = paragraphe brut.** `decision.explanation` est déversé tel quel (7+ lignes de chiffres) ; le hero occupe ~45 % du premier écran à 1440×900 et le verdict passe en partie sous la ligne de flottaison. Observé. | `index.html` `#explain`, `.hero` |
| 14 | **Texte codé en dur** : « Portfolio view: 10 pockets, one hit » quel que soit le payload. Un nœud `protocol` est légendé « Position » et coloré comme tel dans les drivers du dashboard. | `index.html:108`, `api.js:8` |
| 15 | **Scénario REVIEW affiché en vert** : seule la valeur `EXIT` est testée. _(code)_ | `xray.js:453` |
| 16 | **Requêtes 404 pour les logos.** Le chemin est deviné depuis le premier mot du label : 3 fichiers en 404 sur le snapshot (`reusd.svg`, `rexyz.svg`, `us.svg`). Le repli sur l'icône de couche fonctionne. À l'inverse, 681 logos (≈ 5 Mo) sont déployés pour une vingtaine utilisés. | `graph.js:79`, `public/assets/logos/` |
| 17 | **En-tête mobile du X-Ray qui déborde.** À 390 px le badge est coupé et les liens Dashboard / X-Ray sortent de l'écran ; la barre d'outils passe sur deux lignes par-dessus le graphe. Le dashboard, lui, est correct. Observé. | `xray.css:290-310` |

### P2 — accessibilité, design system, maintenance

- **Graphe inaccessible au clavier.** Le canvas a `tabindex="0"` mais aucun gestionnaire clavier ; la seule alternative est le sélecteur « Fail a node ». Les insights de concentration ont `tabindex` mais ne réagissent qu'au clic (`xray.js:551-559`). Les boutons segmentés n'ont pas d'`aria-pressed`.
- **Contrastes sous 4,5:1 sur du très petit texte** : `#6c768a` sur carte à 10 px (3,5:1), pied de panneau `#596377` (3,0:1), note « Model » à 11 px (3,9:1), axes du graphique à 9,5 px (4,0:1), bouton primaire blanc sur `#3b82f6` (3,7:1). Une grande partie du panneau est en 10–11 px.
- **Tokens dupliqués.** `xray.css:1-12` redéclare tout le `:root` de `theme.css` et ajoute `--layer-protocol`, absent du thème ; une trentaine de couleurs hex sont en dur dans `xray.css`, d'autres dans `graph.js` et `chart.js`. Deux en-têtes distincts (`shell.js` pour le dashboard, HTML propre pour le X-Ray).
- **Écart avec la direction visuelle de la spec** : titre en dégradé, bouton et cartes à halo, grille + halos radiaux en fond (`index.html:15-22`), pastille « X-RAY » en dégradé lumineux (`xray.css:26`), fond étoilé (`graph.js:114`), animation count-up des KPI. La spec demande exactement l'inverse (§4.1, §12).
- **Aucun filet de sécurité front** : pas de test, de lint ni de vérification de types pour ~1 700 lignes de JS ; `model.js` réimplémente la propagation du backend sans test de parité. `xray.js` (760 lignes) cumule état, rendu et contrôleur.

## 4. Ce qui est solide (à conserver)

- **Étiquetage de provenance** conçu comme une contrainte (`payload.source`, badge, `discovery_error`) : rare et précieux, il manque seulement de cohérence entre pages.
- **Le X-Ray comme interaction** : cascade saut par saut, timeline, drawer avec lignage, sources et niveau de confiance, « What you really hold », concentration cachée. C'est le différenciateur réel du produit.
- **Honnêteté de modèle déjà en place** : verdict REVIEW à trois états, « if it happens » pour les pertes conditionnelles, « Client propagation check » distinct du résultat serveur, états vides explicites (look-through absent, peg « not enough data »).
- **Robustesse** : échappement systématique des chaînes du payload, timeout et repli de chargement, état d'erreur avec retry, `prefers-reduced-motion` respecté, zéro dépendance et zéro build (déploiement Vercel trivial).

## 5. Écart avec `frontend.md`

| Attendu par la spec | État actuel |
|---|---|
| Risk Overview : 4 métriques + carte + Breaking Point visibles en 10 s (§5) | Landing page + verdict ; pas de graphe ni de point de rupture sur l'accueil |
| Dependency Explorer avec inspecteur, filtres, recherche (§6) | Graphe + inspecteur présents et bons ; ni filtres ni recherche |
| Stress Lab / Breaking Point (§7) | Absent. Le X-Ray simule des pannes de nœud, pas un choc de prix jusqu'au seuil de liquidation |
| Table Positions triable (§8.1) | Table de pockets statique |
| STAY / EXIT sur mêmes hypothèses (§8.2) | Présent, mais bases de coût incohérentes (constats 2 à 4) |
| Sidebar, en-tête persistant, horodatage du snapshot (§3) | Deux pages, deux en-têtes, pas d'horodatage visible sur le dashboard |
| Stack React + TS + Vite (§10) | Vanilla sans build. La spec dit aussi de ne pas migrer sans raison : ce n'est pas un défaut en soi |
| « Never render a fictitious curve » (§7.4) | Respecté : la courbe break-even est une fonction explicite, étiquetée |
| États `not modeled` ≠ `0` (§7.5) | Respecté dans le X-Ray, violé par `fmtUsd` du dashboard |

## 6. Ordre de travail recommandé

1. **Unifier la vérité des chiffres** (constats 1, 3, 5, 6) : un module partagé pour le badge de source, le formatage et la base du coût de sortie. Petit, sans risque, effet immédiat.
2. **Neutraliser le verdict client** (constat 2) et corriger les verdicts de pockets côté moteur (constat 4).
3. **Faire du X-Ray la page d'accueil** ou y fusionner le verdict du dashboard : le hero marketing consomme le premier écran sans rien apprendre au jury. Supprimer l'ouverture automatique du guide.
4. **Exposer ce que le moteur calcule déjà** : `stress_table`, `uncertainty` / VaR95, `liquidation`. C'est le chemin le plus court vers un écran « Breaking Point » honnête, sans nouveau calcul front.
5. **Propager les paramètres d'URL** entre pages et vers l'API (constat 7).
6. **Passe visuelle** : tokens uniques, retrait des dégradés et halos, taille de texte minimale 12 px, collisions de labels, en-tête mobile.
7. **Tests de parité** `model.js` ↔ backend sur `sample.json`, si le temps le permet.

Les points 1, 2 et 5 sont des corrections ; 3, 4 et 6 sont des choix de produit à arbitrer selon le temps restant avant la démo.
