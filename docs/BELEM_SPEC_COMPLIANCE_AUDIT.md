# FAULTLINE — Audit de conformité au challenge Belem Capital (Phase 0)

> **Instruction à donner à Claude Code / à tout agent capable de lire et tester le dépôt.**
> **Mission exclusive : vérifier que le prototype respecte toutes les exigences explicites du PDF officiel avant de lancer d'autres fonctionnalités.**
> **Source de vérité :** `BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf` (EPFL Hackathon 2026, *DeFi Risk Dependency Challenge*, **page 1**, unique page).
> **Projet audité :** dépôt FAULTLINE, depuis sa racine.

---

## 0. Rôle et règles impératives

Tu es un **auditeur technique indépendant**, spécialisé en DeFi, intégration on-chain, modélisation du risque et validation de logiciels. Ta mission n'est **pas** d'améliorer l'esthétique ni de construire les futures fonctionnalités de FAULTLINE. Elle est de **prouver, avec des éléments vérifiables**, que le socle demandé par Belem Capital fonctionne.

1. Lis **l'intégralité du PDF** (texte, schéma Pendle, exemple chiffré, tableau d'évaluation) avant l'audit. S'il n'est pas dans le dépôt, cherche-le dans les fichiers accessibles ou demande le chemin. **N'invente pas son contenu.** La matrice ci-dessous sert de transcription opérationnelle, mais le PDF prime en cas de divergence.
2. Explore **le code réellement présent**, le schéma des données, les contrats/API, le frontend si présent, les tests et le README. Ne te fie jamais à une promesse écrite sans preuve d'exécution.
3. Travaille **en lecture seule sur le produit** : autorisés, inspection, commandes de compilation/test non destructives, appels de lecture vers des données publiques, génération des rapports d'audit. N'effectue pas de déploiement, migration, transaction on-chain, écriture sur un wallet, installation lourde ou modification du code applicatif sans accord. Ne révèle jamais de secret contenu dans `.env`.
4. Pour chaque exigence, fournis : **statut, preuve, commande/test, résultat observé, lacune et correctif minimal**. Cite des chemins de fichiers, symboles et numéros de lignes quand disponibles.
5. **Distingue clairement :** (A) exigences explicites du challenge, (B) critères qualitatifs du jury, (C) exemples de la fiche, (D) liberté de conception, (E) recommandations d'ingénierie proposées par toi. **N'élève pas un exemple ou une recommandation au rang d'obligation.**
6. Ne considère pas un mock, une fixture, une réponse API en dur, un graphe écrit à la main ou des métriques fictives comme preuve suffisante d'un fonctionnement sur des **données réelles**.
7. Les tests sont des moyens de vérification proposés ici, **pas des exigences techniques imposées par le PDF**. Respecte tout choix d'écosystème, de framework et de modèle de risque cohérent avec le challenge.
8. Quand un point est impossible à tester (réseau, clé, RPC, API, dataset, position), marque **NON VÉRIFIABLE**, détaille le blocage et propose une procédure de validation. **Ne déclare jamais « 100 % conforme » sans vérification effective.**
9. **Aucune nouvelle fonctionnalité** (whale tracking, nouveaux scénarios, dashboards accessoires, polish graphique, etc.) avant la fin de cet audit et la correction des blocages identifiés.

---

## 1. Ce que demande réellement Belem Capital

### 1.1. Obligations du coeur du challenge — à prouver

| ID | Exigence fondée sur le PDF | Preuve minimale recherchée | Où dans le PDF |
|---|---|---|---|
| **M01** | Un **prototype exécutable**, pas seulement un diagramme ou une présentation. | Le projet démarre; une exécution bout en bout produit une réponse exploitable. | « What we expect » |
| **M02** | **Identifier automatiquement les dépendances d'une position** DeFi. | Sur une position réelle sélectionnée, le logiciel dérive ses dépendances depuis des données/relations vérifiables, sans saisir manuellement tout le graphe. | « The challenge / Build the system » |
| **M03** | Représenter les **dépendances sous-jacentes pertinentes**, y compris leur enchaînement, suffisamment fidèlement pour expliquer la transmission du risque. | Graphe ou structure équivalente montrant les relations, leur origine et leur effet sur la position; validation des liens importants. | « The problem », critère « Dependency discovery » |
| **M04** | Estimer **l'impact économique potentiel sur la position** lorsqu'une de ses dépendances est affectée. | Un choc défini sur une dépendance sélectionnée modifie une estimation numérique de perte/exposition/coût de manière explicable. | « The challenge / Build the system » |
| **M05** | Fournir un **signal de risque utilisable par un gérant**, en pratique une décision **rester ou sortir** et sa justification. | La sortie relie position, choc, pertes et coûts à une recommandation intelligible et argumentée. | Accroche, « Answer the question a risk manager actually asks », « What we expect » |
| **M06** | Faire apparaître **l'arbitrage entre la perte probable si l'on reste et les coûts d'exécution si l'on sort**. | Les deux côtés de la décision sont explicités, dans des unités et un horizon cohérents, avec hypothèses/limites visibles. | « Answer the question a risk manager actually asks » |
| **M07** | Faire tourner le prototype sur des **données réelles on-chain** (directes ou reprises de sources documentées exploitant des données on-chain). | Au moins un cas réel traçable : chaîne, contrat/position ou pool, source, horodatage ou bloc, valeurs effectivement utilisées par le calcul et résultat. | « What we expect », critère « Working demo on real data » |
| **M08** | Produire un **résultat concret utilisable** et montrer la chaîne *dépendance → incident/choc → impact → décision*. | Une démo reproductible reliant les sorties entre elles, plutôt que quatre écrans ou chiffres sans relation. | « The challenge », « What we expect » |

**Interprétation prudente :** M03, M06 et M08 explicitent l'opérationnalisation des objectifs du texte; ils ne prescrivent **aucun modèle mathématique, score, interface ni profondeur fixe**. Le document n'exige pas une API publique, une automatisation de trading ou une couverture exhaustive de tous les protocoles.

### 1.2. Critères de jugement — dimensions qualitatives, pas seuils numériques

| ID | Critère officiel | Poids officiel | Ce qu'il faut évaluer |
|---|---|---:|---|
| **J01** | Dependency discovery: depth and correctness | **30 %** | Profondeur justifiée, exactitude des noeuds et des liens, couverture des dépendances importantes du cas choisi. |
| **J02** | Impact estimation: is the number defensible | **30 %** | Calcul traçable, hypothèses exposées, propagation cohérente, sensibilité et absence de nombres arbitraires. |
| **J03** | Decision usefulness: stay or exit, and why | **25 %** | Recommandation intelligible, comparaison de scénarios et coûts, explication adaptée à un gérant. |
| **J04** | Working demo on real data | **15 %** | Application fonctionnelle et démonstration utilisant réellement les données du cas choisi. |

**Attention :** les pourcentages sont les **poids du jury**, **pas** des seuils de conformité ni une garantie de note. Il n'existe **aucune barre de passage chiffrée** dans le PDF. Ne fabrique pas une note « officielle ».

### 1.3. Exemples et libertés — **NE PAS les rendre obligatoires**

- **Écosystèmes :** Solana, EVM, Canton et Tempo sont des possibilités. **Un seul écosystème peut suffire** pour un prototype crédible; le PDF ne demande pas la prise en charge de tous.
- **Pendle PT :** le schéma illustratif présente **cinq couches** : (1) settlement chain; (2) underlying yield source and issuer; (3) oracle pricing the asset; (4) PT market and AMM curve; (5) lending market holding it as collateral. **Ne pas imposer Pendle ni exactement cinq couches** à d'autres positions. Si FAULTLINE choisit *cette* position Pendle comme cas phare, auditer les couches applicables à la position exacte, en signalant celles qui n'existent pas dans ce cas.
- **Autres cas illustratifs :** vault allouant des fonds à une plateforme de perps; concentration de TVL; dépendance à un oracle/feed. Ce sont des pistes, **pas des modules tous exigés**.
- **Méthodes de risque :** graph analysis, simulation, statistiques et agents sont autorisés; **aucun n'est imposé**.
- **Exemple d'arbitrage :** portefeuille en dix poches de 10 %, une poche affectée, **11 % de slippage** pour la sortir. C'est un cas pédagogique, **pas une valeur de slippage à coder en dur**. Si ces hypothèses s'appliquent à une poche représentant 10 % du portefeuille, le coût équivaut à **1,1 % de la valeur totale du portefeuille**; afficher correctement la base de calcul.
- **Informations Belem :** AUM, historique, nombre de protocoles/chaînes suivis et pratiques internes décrivent l'organisateur. **Ce ne sont pas des exigences d'implémentation pour FAULTLINE.**

---

## 2. Protocole d'audit (ordre à respecter)

### Étape A — Inventaire et traçabilité

1. Identifier langage, frameworks, points d'entrée, packages, scripts d'exécution, services externes, RPC/indexeurs, fichiers de configuration, front/back, modèles et tests.
2. Identifier **la véritable entité analysée** : adresse wallet, token, vault, marché, LP, PT, position de prêt ou autre. Noter chaîne, adresse(s) de contrat, identifiants et unités.
3. Pour M01 à M08, associer les fonctions/modules, endpoints, composants UI et tests concernés; si aucune implémentation n'est repérée, noter **ABSENT**.
4. Classifier l'origine de **chaque variable importante** : chaîne/RPC, indexeur, API externe de données on-chain, config, estimation, scénario hypothétique, mock/fixture, ou hardcode.
5. Décrire en une phrase le **chemin bout en bout** actuel : `entrée position → découverte → graphe → choc → calcul → coût de sortie → décision → affichage`.
6. Repérer les fonctionnalités additionnelles déjà présentes, mais **ne pas les auditer à la place du coeur Belem**.

### Étape B — Vérification statique de logique

Contrôler, en documentant précisément les résultats :

- **Découverte M02/M03 :** origine des dépendances; preuve de découverte automatique; direction des arêtes; risques indirects; identifiants de noeuds; absence de cycles ou traitement prévu; duplication de risques; couverture explicitement partielle lorsque nécessaire; cohérence de la position avec le réseau.
- **Propagation M04 :** quel choc touche quel noeud; relation causale jusqu'à la position; équations, paramètres, limites, conversion en valeur monétaire; distinction risque direct/indirect; pas de risque compté deux fois sans justification.
- **Décision M05/M06 :** définition de « rester », « sortir », des coûts de sortie et du risque de rester; horizon et probabilités **si utilisés**; coûts correctement exprimés en %/bps/monnaie; distinction perte conditionnelle, perte espérée et score heuristique; recommandation et explication cohérentes avec les chiffres.
- **Authenticité M07 :** parsing des données, précision des décimales des tokens, prix, timestamps, chain IDs, appels API et exceptions; le **calcul final** doit utiliser la donnée réelle, pas seulement l'afficher en décoration.
- **Démo M01/M08 :** état du backend et frontend, exécution locale, erreurs, chargement, états vides, provenance visible et reproductibilité. **Pas d'exigence de sophistication UI** non prévue par le PDF.

### Étape C — Exécution et tests de bout en bout

**Exécute les tests existants**, puis adapte les contrôles ci-dessous à l'architecture en place. N'annonce « PASS » que pour des sorties **observées**. Quand le test nécessite des accès absents, **NON VÉRIFIABLE**, sans inventer de résultat.

| Test | Scénario de vérification | Observation attendue |
|---|---|---|
| **T01** | Installer/initialiser selon la doc **si autorisé**, puis lancer le projet. | Le prototype démarre sans erreur bloquante et expose son résultat. |
| **T02** | Analyser **une position réellement existante** dans l'écosystème pris en charge. | Dépendances générées par la logique du produit; la position n'est pas une simple fixture. |
| **T03** | Inspecter les dépendances de T02 et vérifier **au moins quelques relations critiques** via contrat, docs du protocole, RPC ou indexeur. | Relations plausibles, validées et sourcées; lacunes reconnues. |
| **T04** | Sélectionner une dépendance directe et lui appliquer un choc défini. | Un impact économique quantifié sur la position est calculé et expliqué. |
| **T05** | Sélectionner une dépendance **indirecte**, lorsqu'il en existe une dans le cas choisi. | Le choc se propage via la relation pertinente; sinon **NON APPLICABLE** avec justification. |
| **T06** | Comparer choc nul / faible / important, pour un paramètre dont l'effet attendu est monotone. | Résultats cohérents et vérifiables; aucune garantie de monotonie pour les mécanismes non monotones. |
| **T07** | Tester la cohérence des unités avec une valeur de position contrôlable. | $ / token / % / bps, décimales et valeur de référence correctement convertis. |
| **T08** | Examiner le coût de sortie du **cas réel** : source et hypothèses de slippage, frais, liquidité et autres composantes réellement modélisées. | Coût explicite et justifié; limites signalées; aucune valeur arbitraire présentée comme réelle. |
| **T09** | Proposer un cas où le risque de rester est clairement inférieur au coût de sortie et l'inverse, **si la logique décisionnelle le permet**. | Signal et justification compatibles avec la règle de décision définie; sinon défaut ou limite explicitée. |
| **T10** | Répéter un même cas avec mêmes données figées et paramètres. | Résultat reproductible, ou variabilité expliquée si modèle probabiliste. |
| **T11** | Retracer un nombre affiché depuis la donnée source jusqu'à la formule et à l'interface. | Preuve d'un usage réel des données et provenance suffisante pour vérification. |
| **T12** | Désactiver / simuler l'indisponibilité d'une source **sans action destructive**, si faisable. | Erreur ou mode dégradé clair; pas de chiffre inventé ni fallback silencieux présenté comme live. |
| **T13** | Vérifier une donnée périmée, mal formée ou non disponible, avec mock de test clairement identifié si nécessaire. | Comportement explicite; fraîcheur/limites non masquées. |
| **T14** | Parcourir le cas depuis l'entrée de la position jusqu'à l'écran ou à l'API du signal final. | Parcours complet compréhensible : **dépendance → choc → impact → décision**. |
| **T15** | Relire les sorties et comparer les affirmations (« temps réel », « perte attendue », « exact », « live », etc.) à leur implémentation. | Aucune revendication non démontrée; estimation et observation clairement distinctes. |

**Note :** T06–T13 sont des **tests de robustesse et de crédibilité proposés**, pas autant de fonctionnalités distinctes exigées par Belem. Une absence sur ces points peut nuire au caractère défendable du résultat, mais ne crée pas artificiellement une obligation du PDF.

### Étape D — Test de la décision financière

Exiger pour le **cas principal de démonstration** un récapitulatif de ce type, avec valeurs réellement calculées :

```text
Position analysée      : [protocole / position / chaîne / identifiant vérifiable]
Exposition              : [montant + devise + date / bloc]
Dépendance affectée     : [noeud identifié, source du lien]
Scénario                : [choc, amplitude, horizon si pertinent, hypothèses]
Impact estimé en restant: [montant / % + nature de la mesure]
Coût estimé de sortie   : [montant / % + méthode / hypothèses]
Décision                : [STAY / EXIT / INDETERMINATE]
Raison                  : [comparaison explicite et réserves]
Origine des données     : [chaîne, contrats, sources, horodatage / bloc]
```

Vérifie spécifiquement que :

- Un **score de risque sans traduction économique** ne remplace pas à lui seul l'estimation d'impact demandée.
- Une **perte conditionnelle à un choc** n'est pas appelée « perte espérée » sans estimation de probabilité. Si le modèle utilise plutôt un seuil, un stress test, une fourchette ou une règle heuristique, il l'annonce honnêtement et explique comment la décision est produite.
- Une recommandation « sortir » **n'est pas automatique** dès qu'un risque est élevé : elle doit tenir compte du coût de sortie dans le cadre retenu.
- Les coûts de sortie calculés sur une sous-position ne sont **pas confondus** avec les pertes rapportées au portefeuille entier.
- Les hypothèses arbitraires ou incertaines sont **visibles et testables**, non maquillées en données de marché observées.
- Si l'information ne permet pas une décision défendable, **INDETERMINATE / données insuffisantes** est préférable à une fausse certitude; expliquer ce que cela empêche de satisfaire dans le cas testé.

---

## 3. Comment noter les constats

### Statuts de preuve (pour chaque M et chaque test)

- **VÉRIFIÉ** : code localisé **et** démonstration/test observé concluant.
- **PARTIEL** : partie fonctionnelle mais absence d'un élément essentiel ou d'une justification.
- **ÉCHEC** : absent, erroné, ou contraire à l'exigence.
- **NON VÉRIFIABLE** : pas de donnée, d'environnement ou de possibilité d'exécution pour établir le résultat.
- **NON APPLICABLE** : uniquement pour un test conditionnel ou un exemple libre, **jamais** pour les exigences fondamentales M01–M08.

### Sévérités et priorité de travail

| Niveau | Définition | Exemple |
|---|---|---|
| **P0 — Bloquant conformité** | Empêche de satisfaire une obligation explicite ou invalide le résultat. | Aucune vraie donnée on-chain; graphe entièrement hardcodé; aucune estimation économique; signal stay/exit sans comparaison des coûts. |
| **P1 — Risque jury majeur** | Base existante mais crédibilité, exactitude ou défendabilité insuffisantes. | Décimales incorrectes, dépendance critique omise, hypothèse majeure cachée, résultats non reproductibles. |
| **P2 — Renforcement** | Amélioration utile pour la démo ou la qualité, non indispensable à la conformité de base. | Meilleure couverture de noeuds, tests complémentaires, provenance mieux exposée. |
| **P3 — Hors phase** | Feature additionnelle ou cosmétique. | Whale analyzer avancé, réorganisation complète du design, multi-chaîne sans besoin pour la démo. |

**Règle d'arbitrage :** corrigez les **P0**, puis les **P1** affectant J01–J04. Les P2/P3 ne doivent pas masquer un P0. Ne confonds pas priorité d'ingénierie avec règle officielle du jury.

---

## 4. Rapports à écrire dans le dépôt

Crée les fichiers **dans `audit/`**, sans modifier le code produit :

### A. `audit/BELEM_REQUIREMENTS_AUDIT.md`

Structure obligatoire :

1. **Verdict global** : `CONFORMITÉ DÉMONTRÉE` ou `CONFORMITÉ NON DÉMONTRÉE` (si un M est partiel, en échec ou non vérifiable).
2. **Périmètre et environnement** : commit/branche, date, commandes utilisées, services nécessaires, limites d'accès.
3. **Matrice M01 à M08** : statut, implémentation (chemin + lignes), test exécuté, résultat observé, lien vers preuve, priorité si écart.
4. **Tests T01 à T15** : statut, commandes/paramètres, résultats observés, limites.
5. **Parcours du cas réel** : entrée, sources, dépendances vérifiées, choc, formule d'impact, coût de sortie, décision.
6. **Analyse par critère du jury** J01–J04 : points forts, risques, preuves, **poids officiels**; pas de note officielle inventée.
7. **Bugs, incertitudes et écarts ordonnés** P0 → P3; pour chaque écart : pourquoi c'est important, étapes de reproduction, correctif minimal, test de non-régression.
8. **Plan d'action strictement minimal** pour arriver à une conformité démontrable; distinguer nécessaire / recommandé / facultatif.
9. **Checklist finale de validation** avec cases cochées seulement si effectivement vérifiées.

### B. `audit/BELEM_EVIDENCE.json`

Crée un JSON valide, lisible par machine, par exemple :

```json
{
  "source": "BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf",
  "source_page": 1,
  "project": "FAULTLINE",
  "commit": "<git-sha-or-unknown>",
  "verdict": "CONFORMITÉ NON DÉMONTRÉE",
  "requirements": [
    {
      "id": "M01",
      "status": "NON VÉRIFIABLE",
      "evidence": [],
      "tests": [],
      "blockers": ["<raison précise>"],
      "priority": "P0"
    }
  ],
  "tests": [],
  "real_data_case": null,
  "blocking_findings": [],
  "audited_at": "<ISO-8601>"
}
```

Inclure **les huit entrées M01–M08**, même si non vérifiables. Conserver les résultats bruts pertinents (sans secrets, sans données personnelles inutiles) et mentionner les preuves manquantes.

### C. Récapitulatif terminal final

À l'issue de l'audit, termine par :

```text
AUDIT BELEM — FAULTLINE
M01  [statut]  Prototype exécutable
M02  [statut]  Découverte automatique
M03  [statut]  Dépendances correctement reliées
M04  [statut]  Impact économique quantifié
M05  [statut]  Signal stay / exit explicable
M06  [statut]  Arbitrage risque / coût de sortie
M07  [statut]  Données réelles on-chain
M08  [statut]  Démo bout en bout exploitable

Critiques P0 : [nombre]
Majeurs P1   : [nombre]
VERDICT      : [CONFORMITÉ DÉMONTRÉE / CONFORMITÉ NON DÉMONTRÉE]
PROCHAINE ACTION : [la plus petite correction nécessaire / autorisation de passer aux features]
```

---

## 5. Verrou de phase : quand peut-on passer aux autres fonctionnalités ?

Le passage de la **Phase 0 (conformité au cahier des charges)** à la **Phase 1 (features FAULTLINE supplémentaires)** est autorisé **uniquement si** :

- [ ] Le PDF a été lu et les exigences ont été correctement séparées des exemples.
- [ ] **M01, M02, M03, M04, M05, M06, M07 et M08 = VÉRIFIÉ.**
- [ ] Un cas **réel** a été exécuté de bout en bout avec preuves inspectables.
- [ ] Les chiffres clés (impact, coût de sortie et décision) sont reliés aux données et hypothèses qui les produisent.
- [ ] Aucun **P0** non résolu; aucune incohérence **P1** rendant la démonstration trompeuse.
- [ ] Les limites connues sont documentées; les données fictives ne sont pas présentées comme réelles.
- [ ] Les rapports d'audit existent et reflètent les observations réellement effectuées.

**Sinon :** réponds **« CONFORMITÉ NON DÉMONTRÉE — NE PAS PASSER AUX NOUVELLES FEATURES »**, avec les corrections minimales classées par ordre de priorité. **Ne corrige pas silencieusement le produit : livre le diagnostic et attends l'accord de l'équipe pour modifier le code.**

**Si tout passe :** réponds **« CONFORMITÉ DÉMONTRÉE SUR LE PÉRIMÈTRE TESTÉ — PHASE 1 AUTORISÉE »**. Cette formulation garantit la traçabilité des exigences explicites du PDF, **pas** une note parfaite au jury ni l'absence absolue de bugs.

---

## 6. Instruction de démarrage pour l'agent

**Commence maintenant.** Lis le PDF de référence et le dépôt FAULTLINE. Ne pose une question que si l'absence d'accès empêche réellement le contrôle. Sinon, audite l'existant, exécute les validations non destructives possibles, écris les deux rapports, puis donne le verdict. **Priorité absolue : prouver le coeur du challenge Belem avant toute autre feature.**
