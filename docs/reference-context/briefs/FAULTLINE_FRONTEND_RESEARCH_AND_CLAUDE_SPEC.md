# FAULTLINE — Frontend Research, UI/UX Blueprint & Claude Code Playbook

> **Document de référence à donner à Claude Code** · Version 1.1 · 10 octobre 2026  
> **Contexte :** hackathon EPFL / Belem Capital — analyse des dépendances et du risque DeFi.  
> **Périmètre :** frontend et intégration frontend ↔ backend **existant** ; pas de réécriture des moteurs de calcul.  
> **Nom de travail :** FAULTLINE (modifiable si l'équipe change de marque).

---

## 0. Décision de design en une minute

**Il faut construire un _risk command center_, pas un clone de DEX ni un dashboard crypto générique.** Le jury doit comprendre en quelques secondes :

1. **Où est exposé le portefeuille ?** → cartographie des dépendances + exposition.
2. **Quel choc le ferait basculer ?** → **Breaking Point**, la pièce maîtresse de la démo.
3. **Combien pourrait-il perdre ?** → simulation d'impact, avec scénarios et hypothèses.
4. **Que peut-on faire ?** → STAY / EXIT et faisabilité d'une sortie, quand ces données existent.

**Direction visuelle recommandée :** terminal financier institutionnel, moderne, sobre et très lisible. Fond ardoise presque noir, surfaces de données bien délimitées, typographie soignée, orange de risque utilisé avec parcimonie, graphiques nets et _progressive disclosure_. Pas de neon cyberpunk, pas d'animation décorative permanente, pas de cards uniformes pour remplir l'écran.

**Différenciation défendable :** une **seule sélection** d'asset, de protocole ou de dépendance synchronise **le graphe, l'exposition, le Breaking Point, l'impact financier et la décision**. Le produit raconte une chaîne causale, et pas cinq graphiques indépendants.

**Priorité d'exécution :** d'abord la page **Risk Overview** et l'interaction **Breaking Point** ; ensuite **Dependency Explorer** ; enfin la couche intelligence/alerting si elle existe réellement.

---

## 1. Recherche des produits comparables

### 1.1 Références directes

| Produit | Référence consultable | Ce qu'on en retient pour FAULTLINE | Ce qu'on évite de copier |
|---|---|---|---|
| **DeFi Saver** | [Dashboard metrics](https://help.defisaver.com/features/defi-saver-dashboard) · [Ratios de risque](https://help.defisaver.com/features/defi-saver-dashboard/health-safety-and-collateral-ratio) | Ratio de santé, seuil de liquidation, métriques par position et détails à la demande. Le **prix de liquidation peut être N/A** avec plusieurs collatéraux : bon exemple de prudence UX. | La complexité des interfaces de gestion de position/trading, peu utile dans une app d'analyse. |
| **Gauntlet Risk Dashboard** | [Exemple Moonwell](https://dashboards.gauntlet.xyz/protocols/moonwell/markets/base/assets/cbeth?fullscreen=asset_latest_liquidation_curve) · [Présentation des dashboards](https://governance.aave.com/t/gauntlet-risk-dashboard-v2-launch/12663) | **Liquidations at Risk**, VaR, statistiques de marché, **liquidation curves**, fraîcheur des données. Faire une page qui ressemble à un outil de travail de risk analyst. | Des dizaines de séries dès l'écran d'accueil. |
| **Morpho Vaults** | [Exemple de vault avec Allocation / Risk](https://app.morpho.org/arc/vault/0x389abDf4355e0cF4f19298179991705a98f21c18/galaxy-eurc) · [Curators](https://morpho.org/curators) | Différenciation **allocation / exposition / risque** ; filtres par marché, collatéral et adapter ; terminologie structurée. | Un parcours orienté dépôt dans un vault plutôt qu'analyse multi-dépendances. |
| **Dune** | [RockawayX Dashboard — lien transmis par Belem](https://dune.com/rockawayxvault/rockawayx-dashboard) · [Data Hub](https://dune.com/data-hub) | Structure dashboard + graphiques + données onchain + profondeur analytique ; bon point de comparaison avec les données effectivement disponibles. | Un mur de graphiques SQL sans hiérarchie décisionnelle. |
| **Arkham Visualizer / Tracer** | [Visualizer](https://codex.arkm.com/the-intelligence-platform/visualizer) · [Tracer](https://codex.arkm.com/the-intelligence-platform/tracer) | Graphe navigable, filtres, clic sur liens, détail d'entité et exploration de relations. | Confondre **flux de transactions** et **relations de dépendance** : ce sont deux graphes distincts. |

**Limite de recherche :** le lien public RockawayX sur Dune est accessible, mais son contenu graphique dynamique n'était pas récupérable de manière fiable dans cette consultation. Il faut l'ouvrir **dans un navigateur** pour identifier ses datasets, métriques et graphiques exacts ; **ne rien attribuer au dashboard par supposition**. Ce document s'appuie sur son rôle de référence et sur des interfaces dont les capacités sont documentées.

### 1.2 Leçons concrètes tirées de cette comparaison

- **DeFi Saver →** montrer la distance à un seuil, pas simplement un score abstrait. Faire apparaître l'unité, la méthode de calcul et les cas où le seuil n'est pas calculable.
- **Gauntlet →** mettre côte à côte métriques actuelles, exposition au choc et courbe de liquidation. Afficher `updated_at`, le réseau et les conditions du scénario.
- **Morpho →** distinguer portefeuille, position, marché, collatéral, oracle, protocole et chaîne ; ne pas mélanger ces dimensions dans un diagramme circulaire unique.
- **Dune →** proposer des données inspectables et une traçabilité vers la source ; l'UI FAULTLINE doit transformer ces données en **diagnostic**, pas juste les regrapher.
- **Arkham →** rendre le graphe **actionnable** : recherche, survol, sélection, panneau contextuel, chemin causal. Les nœuds ne sont pas de la décoration.

### 1.3 Sources UX / outils techniques utilisés

- [Anthropic — skill officiel frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md)
- [Claude Code — Skills](https://code.claude.com/docs/en/skills) et [CLAUDE.md](https://code.claude.com/docs/en/memory)
- [Microsoft — Playwright MCP](https://github.com/microsoft/playwright-mcp)
- [Chrome DevTools MCP — intégration Claude Code](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/client-configurations.md)
- [shadcn/ui — installation Vite](https://ui.shadcn.com/docs/installation/vite)
- [React Flow — nodes personnalisés](https://reactflow.dev/learn/customization/custom-nodes)
- [TanStack Table — documentation React](https://tanstack.com/table/latest/docs/framework/react)

> **Règle de lecture :** les références externes inspirent des patterns et servent à vérifier des capacités ; les choix de design ci-dessous sont **des recommandations pour FAULTLINE**, pas des fonctionnalités supposées présentes chez les concurrents.

---

## 2. Positionnement et utilisateur principal

### 2.1 Public cible

- **Primaire :** risk analyst / gestionnaire de portefeuille DeFi / analyste de vault.
- **Secondaire :** juré de hackathon comprenant les fondamentaux financiers mais pas toute la plomberie DeFi.
- **Question fondamentale :** _« Si cette dépendance casse ou si le prix bouge, quelle partie de mon portefeuille souffre, à quel seuil, et quelle action reste possible ? »_

### 2.2 Promesse produit (copy UI)

**FAULTLINE**  
**Know what breaks first.**  
_Subtitle :_ “Map dependencies. Stress-test positions. See the path to liquidation.”

Éviter des phrases vagues du type _AI-powered next-generation security platform_. Ne pas promettre de « risque en temps réel » sans prouver la fraîcheur des données et le mode de rafraîchissement.

### 2.3 Les trois couches de risque doivent rester distinctes

1. **Concentration / dépendance :** quelle part du portefeuille dépend d'une entité ou d'un composant.
2. **Liquidation d'une position à effet de levier :** seuil financier calculé selon les règles du protocole ; concerne **les positions emprunteuses éligibles**, pas tous les dépôts.
3. **Perte sous scénario :** pertes modélisées lors d'un prix en baisse, d'un depeg, d'une panne d'oracle, d'une défaillance protocolaire, etc. **Un incident smart-contract n'est pas équivalent à une baisse de prix**.

L'UI ne doit jamais confondre « $ exposés », « $ potentiellement liquidés » et « $ réellement perdus ».

---

## 3. Architecture d'information : écrans et navigation

### 3.1 Sidebar

```text
FAULTLINE

WORKSPACE
  ◉ Risk Overview             P0 — page d'accueil
  ◈ Dependency Explorer       P0 — graphe et exposure
  ◌ Stress Lab                P0 — Breaking Point + impact
  ≋ Positions                 P0 — drill-down en table

INTELLIGENCE                   afficher seulement si données disponibles
  ◇ Leverage Hunter           P1
  ◇ Whale Impact              P1
  ◇ Chain of Blame            P1

ACTION                         afficher seulement si fonction implémentée
  → Exit Analysis             P0/P2 selon backend
  ◉ Alerts                    P2

Footer: Data Sources · Methodology · Settings
```

**Recommandation hackathon :** limiter la navigation initiale à **Overview / Dependency Graph / Stress Lab** + sections secondaires discrètes. Une sidebar surchargée de features non terminées nuit à la démo.

### 3.2 Header persistant

À droite de la sidebar, une barre compacte, commune aux pages :

- **Workspace / portfolio selector** : portefeuille de démonstration, adresse ou portefeuille chargé.
- **Network selector** : All chains / Ethereum / Base / Arbitrum… seulement si supportés.
- **Snapshot timestamp** : `As of 13:42 UTC` + info d'âge + indicateur `Live`, `Delayed`, `Snapshot`, `Demo`.
- **Search / command palette** : rechercher un protocole, un asset ou une dépendance, si faisable.
- **Help** : legend / méthode ; pas de “Connect Wallet” si l'app ne requiert pas réellement de signature.

### 3.3 Routes proposées (adapter au routing déjà en place)

```text
/                       -> redirect /overview
/overview               -> résumé de risques
/dependencies           -> graphe + inspector
/stress                 -> simulateur Breaking Point
/positions              -> tableau des positions
/positions/:id          -> détails d'une position
/intelligence/*         -> si P1 disponible
/exit                   -> comparaison, si implémentée
```

**Ne pas remplacer un routeur déjà en place** simplement pour coller à cette proposition.

---

## 4. Design system — direction graphique choisie

### 4.1 Moodboard textuel

**“Institutional risk terminal with editorial precision.”** Références de caractère : densité et sérieux de Gauntlet, lisibilité de Morpho, exploration d'Arkham, fini visuel d'un outil SaaS financier premium.

- **Dark mode par défaut** ; light mode éventuel après la démo.
- **Surfaces sobres :** pas de glassmorphism envahissant, ombres légères, séparateurs nets.
- **Signal visuel principal :** une fracture/ligne de seuil qui traverse la courbe de stress et se propage au graphe ; pas besoin d'illustrations 3D.
- **Densité maîtrisée :** dashboard utile en 1440 × 900 sans scroller sur 3 écrans.
- **Accent unique :** cyan/bleu pour la sélection et l'interaction ; orange/rouge réservés au risque.

### 4.2 Palette proposée (tokens, pas couleurs codées partout)

```css
:root {
  --bg: #0A1018;           /* canvas */
  --surface: #111A25;      /* panels */
  --surface-raised: #182432;
  --border: #293747;
  --text: #F1F5F9;
  --text-muted: #9BADBF;
  --accent: #66D5E8;       /* selection / interaction */
  --positive: #45C6A3;     /* action favorable */
  --warning: #F7B955;      /* seuil proche */
  --critical: #FF6F6A;     /* risque avéré / liquidation */
  --neutral: #7F91A6;
}
```

Ces hex sont un point de départ. Vérifier les **contrastes réels** (texte, badges, chart labels, focus states) et les ajuster avant validation. Ne pas encoder les états par couleur seule : texte, forme/icône et valeur doivent suffire.

### 4.3 Typographie

- **Titres / UI :** `Manrope` ou `IBM Plex Sans` ; choisir **une** direction, puis la garder partout. Par défaut : IBM Plex Sans pour la crédibilité technique.
- **Nombres / données tabulaires :** `IBM Plex Mono`, avec `font-variant-numeric: tabular-nums`.
- Titres de pages 24–30 px, titres de panneaux 14–16 px, métriques 28–40 px, labels 12–13 px, body 14–15 px.
- Monospace uniquement pour nombres, unités, timestamps, adresses et labels techniques ; pas pour de longs paragraphes.

### 4.4 Layout et composants

- Sidebar fixe **220–240 px** ; header compact **60–68 px** ; contenu avec `max-width` adapté aux graphiques, pas un tunnel central.
- Gouttières **16–24 px**, rayon de card **10–12 px** ; alignement strict des titres, métriques et graphiques.
- Composants réutilisables : `MetricCard`, `RiskBadge`, `SourceTag`, `FreshnessIndicator`, `TokenIcon`, `ProtocolIcon`, `SectionHeader`, `EntityInspector`, `ScenarioPreset`, `AssumptionTooltip`, `EmptyState`, `DataWarning`.
- Icônes : `lucide-react`, symboles cohérents. Aucun emoji dans l'interface finale.
- Effets : transitions fonctionnelles 120–200 ms ; respecter `prefers-reduced-motion`; ne pas animer constamment les arêtes du graphe.

### 4.5 Microcopy finance — vocabulaire exact

| À afficher | Éviter |
|---|---|
| `Exposed capital` | `Money lost` pour de la simple exposition |
| `Modeled loss` / `Estimated loss` | `Guaranteed loss` |
| `Liquidation threshold` | `Crash prediction` |
| `Price shock to first liquidation` | `Breaks at -12%` sans identifier le facteur |
| `Unsupported` / `Not modeled` | `0 risk` pour une donnée absente |
| `Snapshot · 10 min old` | `LIVE` si les données sont un snapshot |
| `Simulated — no transaction will be executed` | Bouton EXIT suggérant une vente effective |

---

## 5. Écran A — Risk Overview (P0, écran du jury)

### 5.1 But

En **moins de 10 secondes**, une personne doit voir **l'exposition**, **la dépendance critique**, **le seuil de rupture** et **l'impact plausible**. Breaking Point doit être visible **sans navigation**.

### 5.2 Wireframe desktop indicatif (1440 × 900)

```text
┌─────────────────┬────────────────────────────────────────────────────────────────────────┐
│ FAULTLINE       │ Portfolio: Demo Vault ▾  Network: All ▾  Snapshot 13:42 UTC · Demo     │
│                 ├────────────────────────────────────────────────────────────────────────┤
│ ◉ Overview      │ Risk Overview                                      [Methodology ↗]     │
│ ◈ Dependencies  │ See where concentration turns into liquidation risk.                   │
│ ◌ Stress Lab    │                                                                        │
│ ≋ Positions     │  [Capital monitored]  [Top dependency]  [First break]  [Modeled loss]  │
│                 │                                                                        │
│                 │ ┌─────────────────────────────────────────┬──────────────────────────┐ │
│                 │ │ DEPENDENCY MAP                          │ CRITICAL EXPOSURES       │ │
│                 │ │                                         │                          │ │
│                 │ │  [Vault] ─ [Aave] ─ [Oracle]            │ 1  Chainlink ...  62%   │ │
│                 │ │          ╲ [Curve] ─ [Stablecoin]      │ 2  USDC ...       41%   │ │
│                 │ │                                         │ 3  Aave ...       29%   │ │
│                 │ │ [Filters]  [Fit view] [Fullscreen]      │ [Open graph →]           │ │
│                 │ └─────────────────────────────────────────┴──────────────────────────┘ │
│                 │                                                                        │
│                 │ ┌─────────────────────────────────────────┬──────────────────────────┐ │
│                 │ │ BREAKING POINT                          │ DECISION SUPPORT         │ │
│                 │ │                                         │                          │ │
│                 │ │  First liquidation: ETH -18.4%*        │ Scenario: ETH -20%       │ │
│                 │ │  [health factor vs price shock]         │ Model loss: $...         │ │
│                 │ │             │ threshold                │ Exit cost: $...          │ │
│                 │ │  [Open Stress Lab →]                    │ Stay/Exit: ...           │ │
│                 │ └─────────────────────────────────────────┴──────────────────────────┘ │
└─────────────────┴────────────────────────────────────────────────────────────────────────┘
* chiffres purement illustratifs, ne pas les afficher comme calculs réels.
```

### 5.3 Quatre métriques d'accueil

1. **Capital monitored — $** : base de calcul explicitée (NAV, gross collateral, amount exposed — selon backend).
2. **Top dependency — nom + %** : % du portefeuille dépendant de ce nœud, selon la définition backend.
3. **First breaking point — facteur + shock %** : **première liquidation modélisée parmi les positions éligibles**, *ou* `Not available` (voir §7).
4. **Modeled downside — $ ou %** : perte selon **un scénario défini et visible**, pas un chiffre brut sans hypothèse.

La métrique « First break » doit être la plus mémorable. Pas de faux score « Risk 92/100 » si aucun modèle ne le fournit.

### 5.4 Interaction clé

`Clic sur dépendance “USDC”` → surbrillance des positions exposées, panneau `Dependency Inspector`, actualisation des métriques calculées pour le scope sélectionné (si backend le permet), boutons `View in Graph` et `Stress this dependency`. Les données qui ne peuvent pas être recalculées avec le scope restent explicitement marquées `Portfolio-wide` ; **ne pas prétendre qu'elles ont été filtrées**.

---

## 6. Écran B — Dependency Explorer (P0)

### 6.1 Structure

- **70 % de la zone** : graphe interactif avec zoom/pan, sélection et mini-légende.
- **30 %** : panneau d'inspection redimensionnable ou drawer fixe pour le nœud sélectionné.
- Barre de filtres : `Entity type`, `Chain`, `Protocol`, `Minimum exposure`, `Risk state` ; champ de recherche et bouton `Reset`.

### 6.2 Sémantique du graphe — non négociable

- **Nœud :** `portfolio | position | protocol | asset | oracle | chain | vault | bridge | other`, **uniquement les types réellement reconnus**.
- **Arête dirigée :** relation `depends_on | uses_oracle | collateralized_by | deployed_on | invested_in | other`, issue des données, avec sens défini par contrat.
- **Taille de nœud :** exposition visuelle *si valeur disponible et comparable*, sinon taille standard par type.
- **Couleur/contour :** état de risque ou catégorie, jamais deux sémantiques contradictoires.
- **Opacité :** nœuds non liés à la sélection atténués ; le chemin de propagation reste visible.
- **Panneau “Why exposed?” :** liste des positions et chemins qui relient le portefeuille à la dépendance.
- **Cycle :** si les données contiennent une boucle, la rendre sans dupliquer les montants ; le pourcentage d'exposition est fourni par le backend, pas par sommation naïve des descendants.

### 6.3 Exemple d'inspector

```text
CHAINLINK ORACLE
Type: Oracle             Chain: Ethereum
Dependent positions: 7    Exposed capital: $... / ...%

Why it matters
  Portfolio → Aave V3 → WETH market → Chainlink ETH/USD
  Portfolio → Morpho → ... → Chainlink ETH/USD

[Inspect positions]  [Simulate oracle incident]
Source · block #... · updated ... · View evidence ↗
```

**Important :** si `Exposed capital` ou le chemin ne sont pas présents, afficher `Unavailable` ou **masquer le détail**, plutôt que déduire faussement une exposition de la taille du nœud.

### 6.4 Optimisations UX

- Par défaut : **sous-graphe pertinent**, pas 250 nœuds illisibles. `Expand neighbors` / `Show all` sur demande.
- Deux modes : `Exposure map` (coloration par %) et `Failure path` (propagation sous scénario), second mode seulement si données fournies.
- Cliquer sur un edge révèle **le type de relation**, la source, le facteur d'exposition et la confiance si disponibles.
- `Fit to view`, `Reset filters`, touche `Esc` pour désélectionner, navigation clavier/fallback liste accessible.
- Indiquer `Graph is a dependency model, not a transaction flow` dans la légende.

---

## 7. Écran C — Stress Lab / Breaking Point (P0, différenciant)

**Cet écran est le cœur du projet.** Le design doit rendre compréhensible **quel choc minimal** déclencherait une **première liquidation** et quelles positions seraient ensuite touchées.

### 7.1 Principes financiers à préserver

- **Breaking Point n'est pas une probabilité.** `-18 %` signifie un choc conditionnel dans un modèle, **pas** « 18 % de chances de liquidation ».
- Un choc est défini **par facteur** (`ETH/USD`, `USDC/USD`, prix de collateral, spread, etc.) et par **sens** (hausse/baisse) ; un unique % universel n'est pas pertinent.
- Le seuil dépend du **protocole, de l'actif, de la dette, du health factor et des hypothèses du modèle**.
- Une position **sans emprunt liquidable** n'a pas forcément de liquidation threshold : utiliser `N/A · No eligible debt`, jamais `0%`.
- Un incident **oracle** ou **smart-contract** n'a pas automatiquement un « choc minimal de prix » calculable ; afficher `Not modeled` ou un autre résultat d'incident si backend le distingue.
- Si les prêts comportent plusieurs collatéraux, les réactions peuvent être **non linéaires** ; ne pas extrapoler une simple formule de prix de liquidation unique.

### 7.2 Layout de l'écran

```text
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ STRESS LAB                                         [Scenario: ETH selloff ▾] [Reset]   │
│ Explore the smallest modeled shock that triggers a liquidation.                         │
├───────────────────────────────┬──────────────────────────────────────────────────────────┤
│ SCENARIO BUILDER              │  BREAKING POINT                         [Model info]     │
│                               │                                                          │
│ Shock factor                  │  ETH/USD ↓ -18.4%* to first liquidation                  │
│ [ETH/USD ▾]                   │  Position: Aave V3 / WETH-backed USDC debt               │
│                               │                                                          │
│ Change (%)                    │  Health factor                                           │
│ [-30% ━━━●━━━━━━ 0%]          │  2.0 ┤                                                   │
│ [-30.0]                       │  1.5 ┤── current ───────╲                                 │
│                               │  1.0 ┼ - - - - - - - - -● - liquidation threshold        │
│ Presets                       │      0%      -10%      -18.4%       -30%                │
│ [-5%] [-10%] [-20%] [-30%]    │                                                          │
│                               │  [Current state] [At breaking point] [Selected shock]   │
│ [Run scenario]                │                                                          │
├───────────────────────────────┴──────────────────────────────────────────────────────────┤
│ CONSEQUENCES                                                                              │
│ [Positions affected]  [Debt at risk]  [Estimated loss]  [Liquidity needed]                │
│                                                                                          │
│ Position          Protocol  HF current  HF stressed  Breakpoint  Estimated impact        │
│ ...               ...       ...         ...          ...         ...                     │
│                                                                                          │
│ [View impact calculation]       [Compare stay vs exit]                                    │
└──────────────────────────────────────────────────────────────────────────────────────────┘
* valeurs illustratives uniquement.
```

### 7.3 Affichage du résultat principal

**Libellé recommandé :** `First modeled liquidation at ETH −18.4%` (chiffre **uniquement** si l'API renvoie cette valeur). En dessous : `Position [X] · Aave V3 · liquidates at health factor ≤ 1.00` **seulement si ce seuil est valide pour le protocole/marché configuré**. Pour les autres protocoles, utiliser `liquidation criterion` + règle reçue.

À droite de la métrique, petite carte : `Current HF`, `HF at selected shock`, `Liquidation threshold`, `Model version`.

### 7.4 La visualisation indispensable

**Courbe x/y :**

- Axe X : choc du **facteur sélectionné** en % (zéro clairement identifié).
- Axe Y : `Health factor` ou `Distance to liquidation` selon la sortie du moteur.
- Ligne horizontale : seuil de liquidation **source backend**.
- Marqueur vertical : premier point de rupture.
- Marqueur supplémentaire : choc actuellement choisi par l'utilisateur.
- Zone « liquidation possible » : légère teinte critique (ne jamais supprimer les labels).
- Tooltip exact : shock %, prix stressé (si pertinent), santé calculée, position, hypothèses ; formatage cohérent.

Si l'API ne fournit **que le seuil** et **pas une série de simulations**, ne pas fabriquer une courbe qui prétend être calculée. Afficher à la place **une échelle graduée avec le seuil** ou demander un endpoint de courbe. C'est un point fondamental de confiance.

### 7.5 Interactions détaillées et états

1. L'utilisateur choisit un facteur de risque et un preset `ETH -20%`.
2. Les sliders ne déclenchent pas 50 appels backend par seconde : état local + debounce approprié ; bouton `Run scenario` si calcul coûteux.
3. La zone résultat affiche `Calculating…` **sans conserver des valeurs périmées présentées comme actuelles**.
4. Les métriques se mettent à jour **atomiquement** à partir d'un même `scenario_id` / même timestamp.
5. La table des positions est triée par **distance à la liquidation croissante**.
6. Le clic sur une ligne ouvre son détail et met en évidence son chemin dans le graphe, si disponible.
7. Un clic `Reset` restaure exactement le scénario initial ; `Share scenario` seulement si URL/query params reproduisent réellement l'état.

**États à gérer :** `Idle`, `Loading`, `Success`, `No liquidation within modeled range`, `Not modeled`, `Unsupported factor`, `Stale snapshot`, `Backend error`, `Invalid input`. Les états « no liquidation within range » et « risk = zero » ne sont **pas** synonymes.

### 7.6 Variantes de scénario (seulement si moteur compatible)

- `Asset selloff`: baisse d'un collatéral.
- `Stablecoin depeg`: perte d'ancrage de stablecoin.
- `Correlated crash`: plusieurs facteurs varient ensemble, à partir d'une **matrice/règle explicite** du backend.
- `Oracle divergence`: événement de divergence / retard / indisponibilité d'oracle ; rendre comme un **incident** si aucun calcul de liquidation direct n'existe.

**Ne pas confondre** simulation de prix et défaillance logique d'un protocole. Toute variante non supportée est à laisser inactive, pas à maquiller.

### 7.7 Exigences d'intégration avec le moteur Breaking Point

Le frontend **n'invente jamais** les résultats de liquidation. Côté TypeScript, construire un adaptateur vers la réponse actuelle du backend. Exemple de modèle **cible indicatif** (à **adapter**, ce n'est pas une API existante documentée) :

```ts
// Types d'interface souhaitables, à mapper sur les contrats réels.
type ResultStatus =
  | 'computed' | 'not_applicable' | 'not_modeled'
  | 'outside_range' | 'insufficient_data' | 'error';

type BreakingPointView = {
  status: ResultStatus;
  portfolioId: string;
  scopeId?: string;
  scenarioId: string;
  asOf: string;                 // ISO 8601
  chainId?: number;
  factor: { id: string; label: string; unit: '%' | 'USD' | 'bps' };
  firstLiquidation?: {
    positionId: string;
    shockPercent: number;      // signe explicite : ex -18.4
    thresholdValue?: number;
    currentValue?: number;
  };
  samples?: Array<{
    shockPercent: number;
    healthFactor?: number;
    distanceToLiquidation?: number;
  }>;
  impactedPositions?: Array<{
    positionId: string;
    status: 'safe' | 'near_threshold' | 'liquidatable' | 'unknown';
    currentHealthFactor?: number;
    stressedHealthFactor?: number;
    estimatedLossUsd?: number;
  }>;
  methodology?: { version?: string; assumptionLabels?: string[] };
  errorMessage?: string;
};
```

**Critères :** un pourcentage n'est pas une fraction sans définition ; `-18.4` != `-0.184`. Les composantes en USD et les `Health Factor` sont distinctes. Séparer `null`, `undefined`, `0`, `not modeled`, `N/A`. Les champs facultatifs **n'existent pas toujours** : ne pas rendre `0` par défaut.

---

## 8. Écrans D–F — autres features, sans gonfler le scope

### 8.1 Positions (P0)

Table filtrable et triable : `Position`, `Chain`, `Protocol`, `Collateral`, `Debt`, `Exposure`, `Health factor`, `Breaking point`, `Modeled impact`, `Data status`. Priorité aux colonnes **disponibles**, pas à une grille vide. Clic sur ligne → détails avec provenance et lien vers Stress Lab préfiltré.

### 8.2 Impact Estimation & STAY/EXIT (P0)

Sur le scénario sélectionné : deux colonnes **mêmes hypothèses et timestamp** :

```text
STAY                                EXIT
Modeled downside: $...              Exit costs: $...
Positions at risk: ...              Liquidity / slippage: ...
Scenario assumptions: ...           Executability: ...

[Recommendation from backend] [Why?] [Evidence]
```

**Prudence :** `STAY` / `EXIT` doit apparaître comme **sortie d'un modèle**, pas comme conseil garanti. Si l'analyse de sortie n'est pas calculée, `Exit analysis unavailable` ; ne pas inventer frais, gas ou slippage. `EXIT` n'est **pas** un bouton d'exécution de trade sauf si une vraie transaction a été implémentée avec consentement utilisateur.

### 8.3 P1 Threat Intelligence

- **Leverage Hunter :** table `Liquidation proximity × Debt/exposure` ; positions les plus proches du seuil en tête ; vues agrégées si adresses publiques disponibles et légitimes.
- **Whale Impact :** flux onchain vérifiés → événements horodatés → actifs/protocoles concernés ; **ne pas inférer automatiquement le prix futur** d'une transaction.
- **Chain of Blame :** graphe causal d'un incident sélectionné avec distinction `observed` / `modeled` / `inferred` ; chemin `source → impacted dependency → affected positions → loss`.

Ces éléments ne doivent pas bloquer P0. Si backend absent, ne pas ajouter de faux écrans remplis de données statiques présentées comme live.

### 8.4 P2 Action Layer

- **Exit Feasibility :** profondeur de marché, liquidité, frais, slippage et restrictions, si récupérés/calculés.
- **Telegram Alerts :** seulement si **vrai** service + permissions + état de connexion ; message de simulation explicitement marqué comme test.
- **Reaction Window :** afficher une **estimation dépendant d'un scénario de vitesse** (ex. `% par minute`) uniquement si le modèle fournit hypothèses et temps estimé. Un seuil de prix seul ne donne **pas** un délai fiable.

---

## 9. La démo du jury : un parcours de 90 secondes

**Dataset de démonstration :** snapshot **synthétique**, cohérent entre graph, positions, metrics et simulation. Libellé `Demo data`. Pour les chiffres ci-dessous, il faut **construire un dataset mathématiquement cohérent** ou les remplacer par des résultats existants ; il ne faut pas afficher les valeurs ci-dessous comme authentiques.

1. **0–15 s : Overview.** `This portfolio looks diversified, but 62%* depends on the same oracle.` Pointer une dépendance commune derrière plusieurs positions.
2. **15–35 s : Graph.** Cliquer sur le nœud, mettre en évidence les positions et le chemin causal. _“The risk is not obvious by looking at protocol names alone.”_
3. **35–65 s : Stress Lab.** Appliquer `ETH −20%` ; faire apparaître un breakpoint à `−18.4%*`, la/les position(s) concernée(s), la courbe et la table mise à jour.
4. **65–80 s : Impact.** Montrer les pertes **estimées** et ce qui relève d'exposition, de liquidation et de perte.
5. **80–90 s : Decision.** Comparer STAY/EXIT ou montrer une action possible **seulement si calcul disponible** ; sinon finir sur le diagnostic et ses preuves.

`*` Valeurs narratives **fictives** pour illustrer le scénario. Remplacer par un seul fixture calibré avec les données réellement retournées par le moteur ; les cartes et courbes doivent correspondre aux mêmes paramètres.

**Mode présentation :** pouvoir passer à `Demo snapshot` sans wallet / clés / RPC. Aucun spinner infini en cas de coupure réseau. L'interface doit toujours indiquer que le mode démo est actif. **Ne jamais afficher un snapshot démo comme un flux live.**

---

## 10. Frontend stack recommandée (adapter au dépôt existant)

| Besoin | Choix recommandé | Pourquoi / limite |
|---|---|---|
| Application | **React + TypeScript + Vite** si app client existante ou greenfield ; **Next.js** si déjà utilisé | Ne pas migrer de framework pendant le hackathon sans raison. |
| Styles | **Tailwind CSS + CSS variables** | Vitesse + tokens contrôlables. |
| Composants accessibles | **shadcn/ui + Radix primitives** | Dialogs, selects, drawers, tooltips, tabs, table skeleton. Personnaliser fortement. |
| Iconographie | **lucide-react** | Cohérence. |
| Graph de dépendances | **@xyflow/react (React Flow)** | Custom nodes/edges, zoom, pan, selection, minimap ; prévoir layout automatique et performance. |
| Layout de graph | **dagre** ou **elkjs** selon complexité | DAG → dagre suffit souvent ; graphes denses/cycles → adapter soigneusement. |
| Séries de stress | **Recharts** si déjà présent, sinon bibliothèque stable du repo | Référence lines, markers, tooltips ; vérifier coût des overlays personnalisés. |
| Positions | **TanStack Table** si besoins de filtre/tri avancés | Table _headless_, sans imposer un style. Attention aux API qui évoluent entre versions. |
| API / cache | **TanStack Query** ou outil déjà présent | États réseau, cache, invalidation, refetch et fraîcheur. |
| Validation données | **Zod**, si utile au boundary réseau | Les contrats runtime doivent être validés, pas simplement castés en TS. |
| UI testing | **Playwright** | Parcours navigateur et screenshots. |
| Unitaires | **Vitest + Testing Library** si projet Vite | Fonctions de mapping, formatage, filtres, états et interactions. |

**Anti-patterns :** ajouter un moteur blockchain dans les composants React, recoder Breaking Point côté client, 5 bibliothèques de graphiques, dépendances non vérifiées, animations lourdes, simulation hardcodée dans `page.tsx`, fichiers monolithiques de 1500 lignes.

### 10.1 Architecture frontend indicative

```text
src/
  app/
    router.tsx
    AppShell.tsx
  pages/
    OverviewPage.tsx
    DependenciesPage.tsx
    StressLabPage.tsx
    PositionsPage.tsx
  features/
    overview/
    dependencies/
      DependencyGraph.tsx
      DependencyNode.tsx
      DependencyInspector.tsx
      graph-layout.ts
    breaking-point/
      BreakingPointPanel.tsx
      ScenarioBuilder.tsx
      StressCurve.tsx
      ImpactedPositionsTable.tsx
    positions/
  components/
    ui/                    # shadcn primitives, si utilisés
    risk/
      RiskBadge.tsx
      FreshnessIndicator.tsx
      DataSourceLink.tsx
      MetricCard.tsx
  lib/
    api/                   # client HTTP, adaptateurs et schemas
    format/                # USD, %, dates, locale
    data/                  # fixtures démo clairement étiquetées
    types/
  styles/
    tokens.css
```

**Frontière technique :** `API response → runtime validation → typed view-model adapter → components`. Aucun composant ne doit supposer le format backend sans adapter. Tous les écrans doivent pouvoir partager le **même** `scenarioId`, `portfolioId`, `selectedDependencyId`, `snapshotAt`.

---

## 11. Skills et outils à ajouter à Claude Code

**Mise à jour du 10/10/2026 :** pour les tools viraux (Higgsfield, Impeccable, 21st.dev, UI UX Pro Max), consulter aussi **§19** : recherche vérifiée, setup officiel, protocoles de revue visuelle et prompts spécifiques. **Installer peu, tester beaucoup.**

### 11.1 Ce qu'il faut installer, par priorité

| Priorité | Extension | Fonction | Source / installation |
|---|---|---|---|
| **P0** | **Anthropic `frontend-design`** | Choix graphiques volontaires, typographie, composition, éviter le rendu générique. | [Skill officiel](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) ; dans Claude Code, essayer `/plugin` puis chercher `frontend-design`. Si le marketplace échoue, utiliser la méthode skill locale (§11.3). |
| **P0** | **Playwright MCP** | Claude ouvre l'app, clique, teste navigation, responsive et récupère des captures/états. | [Microsoft Playwright MCP](https://github.com/microsoft/playwright-mcp) |
| **P0** | **CLAUDE.md du dépôt** | Règles permanentes sur données, composants, style et qualité. | [Guide officiel](https://code.claude.com/docs/en/memory) ; modèle §12. |
| **P0** | **Skill custom `faultline-frontend`** | Traduire cette spécification en implémentation contrôlée. | `.claude/skills/faultline-frontend/SKILL.md` ; modèle §13. |
| **P1** | **Chrome DevTools MCP** | Inspecter layout, console, réseau et perf quand Playwright seul ne suffit pas. | [Documentation Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/client-configurations.md) |
| **P1** | **Playwright Test** (tests du repo) | Tests déterministes indépendants du contexte de chat Claude. | [Playwright](https://playwright.dev/) |
| **P2** | **Skill custom `ui-qa`** | Checklist test et audit visuel récurrents. | Simple `SKILL.md` local ; voir §13.2. |
| **P1 après P0** | **Impeccable** | Audit, critique, affinage de l’interface. | [Installation officielle](https://impeccable.style/tutorials/getting-started/) et protocole §19. |
| **P2 si besoin** | **21st.dev MCP / Higgsfield** | Composants prêts à adapter / assets marketing et concept visuel. | **Voir limites et setup §19 ; non requis pour le moteur de risque**. |

Le plugin officiel `frontend-design` apparaît dans le répertoire Anthropic, mais des utilisateurs ont documenté des **problèmes d'installation selon l'état du marketplace**. Ne pas perdre 45 minutes sur l'install : un fichier `SKILL.md` local issu des recommandations officielles est un fallback valide. [Référence du problème documenté](https://github.com/anthropics/claude-plugins-official/issues/1438).

### 11.2 Commandes utiles

Dans un terminal, à la racine du repo (selon environnement / permissions) :

```bash
# Playwright MCP (commande fournie par Microsoft)
claude mcp add playwright npx @playwright/mcp@latest

# Optionnel : Chrome DevTools MCP (commande du projet)
claude mcp add chrome-devtools --scope user npx chrome-devtools-mcp@latest

# Vérifier les serveurs installés
claude mcp list
```

Dans la session Claude Code :

```text
/plugin
/skills
/doctor
```

Le plugin Chrome DevTools propose également une installation **plugin + skills** :

```text
/plugin marketplace add ChromeDevTools/chrome-devtools-mcp
/plugin install chrome-devtools-mcp@chrome-devtools-plugins
```

**Prudence :** installer uniquement des MCP/skills de sources fiables et vérifier les permissions ; un MCP navigateur peut accéder à des pages et données de session. Ne jamais placer de clés RPC ou API dans un prompt, une capture ou un fixture commité. Vérifier les versions présentes dans le projet avant tout ajout.

### 11.3 Structure des instructions Claude à commiter

```text
repo/
  CLAUDE.md                           # règles stables et courtes
  docs/
    FAULTLINE_FRONTEND_RESEARCH_AND_CLAUDE_SPEC.md
  .claude/
    skills/
      faultline-frontend/
        SKILL.md                      # workflow UI du projet
      ui-qa/
        SKILL.md                      # audit visuel et fonctionnel
```

Les skills Claude Code sont des dossiers contenant un `SKILL.md` avec métadonnées YAML ; ils peuvent être déclenchés automatiquement par leur description ou via une commande `/nom-du-skill`. Consulter la [documentation officielle](https://code.claude.com/docs/en/skills) pour les subtilités de version et de chargement.

---

## 12. Template prêt à copier dans `CLAUDE.md`

> Copier le **contenu de ce bloc** dans `CLAUDE.md` à la racine et ajuster les commandes après inspection du dépôt.

```md
# FAULTLINE — Instructions for Claude Code

You are building the FAULTLINE DeFi dependency risk frontend for a hackathon.

## Source of truth
- Read `docs/FAULTLINE_FRONTEND_RESEARCH_AND_CLAUDE_SPEC.md` before changing frontend UI.
- First inspect the repository, package scripts, existing components, actual backend types and API routes.
- The backend's existing financial/risk engines are authoritative. Do NOT rewrite Breaking Point, exposure, impact or Stay/Exit calculations in the frontend.
- Do NOT fabricate risk scores, price series, liquidation data, APYs, wallet balances or API responses and present them as live.
- Demo fixtures are allowed only if labeled "Demo data" and coherent across views.

## UX principle
- Build an institutional DeFi risk command center, not a DEX/trading clone.
- Primary sequence: Dependency -> Exposure -> Breaking Point -> Modeled loss -> Decision.
- Breaking Point is the visual and interaction centerpiece.
- Every meaningful selection must have a real effect on visible data or navigation.
- All numerical outputs must show units, scenario/scope and freshness as appropriate.
- Distinguish not-applicable, not-modeled, zero, and missing data.
- Never claim a risk calculation is real time unless refresh/freshness proves it.

## Visual conventions
- Dark-first, clean, restrained, content-led; use centralized design tokens.
- Precise typography, tabular numerals, meaningful state colors and accessible contrast.
- No neon crypto look, decorative 3D backgrounds, random gradients or gratuitous animation.
- Support laptop viewport 1440x900 and narrow layouts down to 375px.
- Keep graphs readable with filters, selection, inspection, fit-to-view and empty states.

## Engineering constraints
- Preserve the current framework, router, package manager, conventions and existing APIs when reasonable.
- TypeScript strict typing, reusable components, view-model adapters, validation of untrusted network data.
- No silent fallback from failed API to plausible-looking demo results.
- Never hardcode secret keys or expose them in client bundles.
- Avoid additional dependencies unless there is a clear benefit.
- Keep scenario selection, dependency selection and snapshot coherent across pages.

## Work protocol
1. Audit the existing app before implementation and state what is already available.
2. Identify backend contracts and list unsupported states before building visualizations.
3. Implement the smallest complete vertical slice (Overview + Breaking Point).
4. Run lint/typecheck/tests/build using real project scripts.
5. Open the page in a browser and inspect at least 1440x900 and 390x844.
6. Fix visual glitches, console errors, dead controls, overflow and data inconsistencies.
7. Summarize changed files, tested flows, known limitations and remaining mock/demo inputs.
```

---

## 13. Skill custom FAULTLINE — prêt à copier

### 13.1 `.claude/skills/faultline-frontend/SKILL.md`

```md
---
name: faultline-frontend
description: Build, refine or review FAULTLINE's DeFi risk frontend. Use whenever creating or changing a dashboard page, dependency graph, Breaking Point simulator, portfolio risk visualization, risk data integration or risk-related UI component.
---

# FAULTLINE Frontend Implementation Skill

## Goal
Build a polished, financially honest, interactive institutional risk terminal using the design and product spec in `docs/FAULTLINE_FRONTEND_RESEARCH_AND_CLAUDE_SPEC.md`.

## Required first steps
1. Read the spec and current repo architecture.
2. Inventory actual backend endpoints and response shapes; do not invent API contracts.
3. Identify any existing UI framework, routing, charts and component library; reuse first.
4. Produce a short implementation plan with concrete files and acceptance criteria.

## Aesthetic brief
Dark-first and precise. Emphasize the causal connection between a selected dependency, exposure, liquidation breakpoint, modeled impact and decision. Make Breaking Point the hero visualization. Use consistent tokens, refined typographic hierarchy, sparse signals of critical risk, and strong whitespace discipline.

## Component rules
- Use typed view models and shared formatters.
- Use loading, empty, unavailable, not-modeled, error, stale and demo states.
- Preserve units, scope, timestamp and methodology in financial data.
- Use keyboard-accessible controls; avoid color-only risk encoding.
- A graph edge represents a documented dependency, not an arbitrary correlation.
- Never render a fictitious stress curve if only a scalar threshold is available.

## Verification loop
1. Run typecheck, lint, tests and build where scripts are available.
2. Start the app; inspect it via Playwright MCP if installed.
3. Test 1440x900 and 390x844, plus empty/error/stale states.
4. Check navigation, scenario controls, selection synchronization and console errors.
5. Critique the screenshot: hierarchy, clipping, spacing, alignment, contrast, semantics.
6. Iterate until the interface is clean and all visible interactive controls function.

## Stop conditions
Never silently replace missing API data with hardcoded 'real' data.
Never claim a wallet action or alert succeeded without genuine backend confirmation.
Report which elements are real, simulated or not yet supported.
```

### 13.2 `.claude/skills/ui-qa/SKILL.md` (optionnel, mais très utile)

```md
---
name: ui-qa
description: Audit and test FAULTLINE frontend quality, screenshot fidelity, responsiveness, semantics, accessibility and true end-to-end interactions. Use after creating or changing user-facing components or routes.
---

# FAULTLINE UI QA

Test the running application, not only the source code.

- Check at 1440x900, 1280x800, 768x1024 and 390x844.
- Check no horizontal overflow, clipped labels, unreadable tables or off-screen drawers.
- Check hover/focus states and keyboard navigation.
- Check graph pan/zoom/select/clear/filter/inspect; provide fallback list if necessary.
- Check stress scenario selection, loading, results, reset, errors and stale data.
- Check unit formatting and that current portfolio/snapshot/scenario are consistent.
- Verify demo/synthetic data is clearly labeled and unavailable data is not shown as zero.
- Review screenshots critically; fix 3 most severe visual issues and retest.
- Run available build/typecheck/tests. Report concrete evidence and failures.
```

---

## 14. Prompt maître à donner à Claude Code

> Ce prompt suppose que le `.md` est commité dans `docs/` et que Claude travaille dans le dépôt du hackathon.

```text
You are the lead product designer and senior frontend engineer for FAULTLINE.

Read, fully understand, and implement:
  docs/FAULTLINE_FRONTEND_RESEARCH_AND_CLAUDE_SPEC.md
  CLAUDE.md
  Section 19 of the frontend spec (visual-director workflow, optional creative tools)

Objective:
Ship a memorable, production-quality frontend for the EPFL / Belem Capital
DeFi dependency-risk hackathon. The backend baseline required by the challenge
is assumed to be implemented already. Do not replace existing risk algorithms.

Follow this process strictly:

PHASE 1 — Repository and API audit
- Inspect package.json, routes, styles, components, test setup and available backend APIs.
- Determine what is real, partially implemented or missing; list any spec/API mismatches.
- Reuse the existing framework and only install truly necessary dependencies.
- Keep a minimal plan with files and realistic checkpoints.

PHASE 2 — Design foundation
- Create coherent tokens, typography, shell, sidebar, header, risk statuses and
  reusable components. Match the specific visual direction from the spec.
- No generic AI dashboard aesthetics. The result should feel like a real financial
  analyst workstation: restrained, deliberate and immediately legible.

PHASE 3 — Functional P0 vertical slice
- Risk Overview with real/high-fidelity data mapping and key metrics.
- Dependency Explorer with selectable graph nodes and relevant inspector.
- Breaking Point Stress Lab with meaningful scenario controls and actual backend
  results. If only a threshold is available, render a threshold gauge, not an invented curve.
- Link scope and selections so the same scenario drives related visualizations.
- Implement honest loading, empty, unsupported, stale and error states.

PHASE 4 — Polish and proof
- Run appropriate scripts (lint, typecheck, unit tests, production build).
- If browser automation is available, inspect 1440x900 and 390x844 screenshots.
- Interact with every visible control and fix broken or dead behavior.
- Verify spacing, clipping, chart labels, tooltips, contrast and keyboard access.
- Iterate at least once after a visual review.

Delivery requirements:
- Summarize actual file changes and where data comes from.
- List every placeholder/fixture and clearly mark whether it is demo only.
- Explain exactly how to run and demonstrate the app in 90 seconds.
- No false claims of real-time data, no fake computation, no decorative fake
  features, no hardcoded risk numbers posing as genuine engine output.
- Prioritize one exceptional, reliable path over ten unfinished screens.

Start now with Phase 1. Do not redesign the backend or generate code blindly
before inspecting the repository.
```

---

## 15. Critères d'acceptation — checklist de livraison

### P0 — obligatoire

- [ ] En 10 secondes, l'Overview répond à **exposure / breaking point / impact**.
- [ ] Sidebar, header et cartes fonctionnent à **1440 × 900** sans débordement.
- [ ] Graphe navigable, nœuds sélectionnables, liens compréhensibles, inspector renseigné.
- [ ] Une dépendance sélectionnée reste identifiée dans les vues qui la supportent.
- [ ] Breaking Point affiche **facteur + sens + % de choc + position affectée + critère**.
- [ ] Le graphique de stress utilise **des données calculées**, jamais une fausse courbe.
- [ ] Les changements de scénario produisent de vrais états de chargement/résultat/erreur.
- [ ] Les nombres de risque sont explicitement contextualisés (périmètre, scénario, unité, date).
- [ ] Les positions non liquidables / non calculées ne sont pas montrées comme `0 risk`.
- [ ] Tous les boutons visibles font réellement quelque chose, ou sont clairement désactivés.
- [ ] Mode démo hors ligne fiable et **identifié**, sans confusion avec le live.
- [ ] Build + typecheck + tests disponibles passent ; console sans erreurs bloquantes.
- [ ] Captures navigateur desktop + mobile inspectées et défauts majeurs corrigés.

### P1 — différenciation

- [ ] Table des positions filtrable/triable et reliée au graphe et au stress.
- [ ] Chemins de dépendance interprétables, visualisation du rayon d'impact.
- [ ] Historique/presets de simulation si cela apporte de la valeur réelle.
- [ ] Leverage Hunter / Whale Impact / Chain of Blame seulement avec data fiable.

### P2 — bonus

- [ ] Alertes réellement connectées, avec état de livraison vérifiable.
- [ ] Simulation d'exit qui distingue estimation de coûts et ordre exécutable.
- [ ] Partage/export de scénario reproductible.
- [ ] Reaction Window avec hypothèses explicites et aucune précision artificielle.

---

## 16. Pièges à éviter absolument

1. **L'énorme donut chart :** il dissimule souvent les dépendances partagées et la causalité.
2. **Le “risk score” arbitraire :** score faux ou non traçable détruit la crédibilité.
3. **Le graphe illisible :** prévoir regroupement, filtres, sélection et panneau de détail.
4. **La courbe inventée :** un seuil isolé ne suffit pas à interpoler des health factors sur toute une plage.
5. **Les % doublés :** les expositions partagées **peuvent se chevaucher** ; leur somme n'est pas nécessairement 100 %.
6. **Le mock qui se fait passer pour du live :** afficher `DEMO / snapshot` honnêtement.
7. **Le faux EXIT :** ne jamais donner l'impression qu'un clic exécute une transaction si l'app ne le fait pas.
8. **L'absence de source :** chaque chiffre critique doit être relié à une méthode, une période ou un endpoint.
9. **Le découpage par features uniquement :** la qualité est dans la synchronisation entre features.
10. **La course aux plugins :** `frontend-design` + Impeccable (polish) + MCP navigateur + les skills maison > vingt skills inconnus. Higgsfield et 21st.dev sont **optionnels** et documentés au §19.

---

## 17. Ordre de développement recommandé pour le hackathon

| Ordre | Livrable | Estimation relative | Pourquoi |
|---|---|---|---|
| **1** | Audit repo + contrat API + dataset démo sûr | Court | Réduit immédiatement les erreurs d'intégration. |
| **2** | Shell + tokens + header + Overview | Moyen | Définit le niveau de qualité visuelle visible au premier regard. |
| **3** | Stress Lab / Breaking Point **réel** | Élevé | **Principal “wow moment” analytique** ; investissement prioritaire. |
| **4** | Dependency Graph interactif + inspector | Moyen/élevé | Rend la notion de dépendance tangible. |
| **5** | Navigation croisée Graph ↔ Stress ↔ Positions | Moyen | Différenciateur produit ; évite l'effet « collage de widgets ». |
| **6** | Impact + STAY/EXIT exposés proprement | Moyen | Ferme la boucle “so what?”. |
| **7** | Visual QA + démo fiable hors réseau | Moyen | Plus important pour les juges qu'une feature P2 fragile. |
| **8** | P1/P2 si temps réel restant | Variable | Bonus seulement une fois P0 solide. |

**Arbitrage recommandé :** en cas de manque de temps, sacrifier des écrans P1/P2 avant de sacrifier **la lisibilité du Breaking Point**, la cohérence des chiffres ou le parcours de démo.

---

## 18. Références vérifiables et notes d'usage

**Produits :**

1. DeFi Saver — [Dashboard](https://help.defisaver.com/features/defi-saver-dashboard), [Health / Safety Ratio](https://help.defisaver.com/features/defi-saver-dashboard/health-safety-and-collateral-ratio), [Automation](https://defisaver.com/features/automation).
2. Gauntlet — [Risk Dashboard exemple](https://dashboards.gauntlet.xyz/protocols/moonwell/markets/base/assets/cbeth?fullscreen=asset_latest_liquidation_curve), [Risk Dashboard V2 / Aave](https://governance.aave.com/t/gauntlet-risk-dashboard-v2-launch/12663), [explications des indicateurs](https://discuss.jup.ag/t/gauntlets-real-time-dashboard-explained/20114).
3. Morpho — [Vault](https://app.morpho.org/arc/vault/0x389abDf4355e0cF4f19298179991705a98f21c18/galaxy-eurc), [Curator concept](https://docs.morpho.org/learn/concepts/curator/), [Data dashboards](https://docs.morpho.org/developers/ecosystem/data-dashboards/).
4. Arkham — [Visualizer](https://codex.arkm.com/the-intelligence-platform/visualizer), [Tracer](https://codex.arkm.com/the-intelligence-platform/tracer).
5. Dune — [RockawayX Dashboard](https://dune.com/rockawayxvault/rockawayx-dashboard), [Dune Data Hub](https://dune.com/data-hub).

**Claude et frontend :**

6. Anthropic — [Official frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md), [Claude Code skills](https://code.claude.com/docs/en/skills), [Project instructions](https://code.claude.com/docs/en/memory), [Plugin directory](https://github.com/anthropics/claude-plugins-official).
7. Microsoft — [Playwright MCP](https://github.com/microsoft/playwright-mcp) ; Google Chrome — [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/client-configurations.md).
8. [shadcn/ui](https://ui.shadcn.com/docs/installation/vite), [React Flow](https://reactflow.dev/learn/customization/custom-nodes), [TanStack Table](https://tanstack.com/table/latest/docs/framework/react).

**Notes :**
- Recherche conduite le **10/10/2026**, à partir des pages publiques et documentations citées.
- Ce document **ne remplace pas** le cahier des charges officiel de Belem : la capture des priorités P0/P1/P2 fournie par l'équipe est traitée comme référence de périmètre, mais aucune exigence supplémentaire du PDF n'est inventée.
- Pour trancher une ambiguïté produit, **les exigences officielles Belem + les API réellement présentes dans le repo priment** sur les propositions de layout, de lib ou de copy de ce document.

---

**Décision finale :** construire **une Overview élégante + un Stress Lab Breaking Point irréprochable + un Dependency Graph compréhensible**, tous reliés au même scénario et aux mêmes données. C'est une démonstration plus forte qu'une interface de vingt onglets.

---

## 19. Extension 2026 — Higgsfield, skills « premium » et méthode de direction artistique pour Claude Code

> **À lire et appliquer AVANT de générer ou de modifier le frontend.** Ce chapitre complète les §§4, 11–16. Il ne remplace pas la priorité métier : **tout le P0 doit être exact, interconnecté, utilisable, et démontrable avant les effets de style**.
>
> **Décision :** employer un trio resserré — `frontend-design` (direction), **Impeccable** (critique/polish), **Playwright** (preuve réelle) — plus **21st.dev** (composants, si nécessaire). **Higgsfield est optionnel** pour l'identité et les assets ; ne pas lui déléguer le dashboard analytique. Ajouter les autres skills seulement si un manque concret est identifié.

### 19.1 Ce que montrent les outils et les discussions (et ce que cela signifie)

| Outil / source | Capacité vérifiée | Valeur dans FAULTLINE | Limite importante | Décision |
|---|---|---|---|---|
| [Higgsfield — Website Builder](https://higgsfield.ai/skills/website) | Skill officiel qui génère un **site responsive**, avec interactions et séquences multimédias à partir d'un brief. | Explorer une proposition visuelle, créer un concept marketing / landing de présentation séparé de l'application. | Exemples principalement « showcase » narratif. **Ni l'export propre du code existant, ni la conservation de l'architecture du dépôt ne sont garantis par la page consultée.** | **Optionnel, exploration uniquement**, pas base de code P0. |
| [Higgsfield CLI / MCP](https://higgsfield.ai/mcp?tab=claude-code) | Génération d'images/vidéos depuis Claude Code par CLI/skills ; connexion MCP depuis Claude web/desktop. | Illustration de concept, fond abstrait discret, éventuelle courte séquence vidéo de **pitch**, export d'un visuel adapté. | Connexion, abonnement/crédits et droits d'utilisation à vérifier. Les outputs **ne sont pas des composants React inspectables**. | Seulement si un asset nécessaire manque réellement. |
| [Anthropic — Frontend Design](https://claude.com/plugins/frontend-design) | Skill officiel contre le rendu de template IA ; impose une direction esthétique cohérente. | Choix d'une composition « institutional risk terminal », identité et typographie. | Une direction audacieuse doit **rester subordonnée à la lisibilité du risque** ; le skill ne fournit pas la qualité par magie. | **Priorité 1**. |
| [Impeccable](https://impeccable.style/tutorials/getting-started/) | Skill de revue visuelle et UX avec commandes `audit`, `critique`, `polish`, `distill` et autres. | Corriger proportions, détails, hiérarchie, bruit, états, cohérence du design. | Outil d'**itération**, pas une justification pour remodeler indéfiniment le design. | **Priorité 1**, après première version fonctionnelle. |
| [21st.dev MCP](https://21st.dev/mcp) | Recherche et récupération de composants, patterns React/Tailwind, génération UI selon accès. | Trouver un bon `drawer`, `command palette`, `empty state`, `tabs` ou `tooltip` et adapter le code. | Dépendances, compatibilité, licence du composant, homogénéité graphique. **Magic MCP a été remplacé par le 21st MCP** en 2026. | **Priorité 2**, seulement si accélère vraiment. |
| [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | Référentiel de patterns, palettes, styles, typographie, stacks. | Inspiration comparative si Claude a du mal à fixer une direction. | Redondant avec `frontend-design` + Impeccable, recommandations parfois génériques. | **Alternative, pas installation obligatoire**. |
| [Vercel — web-design-guidelines](https://github.com/vercel-labs/agent-skills) | Audit d'ergonomie/accessibilité/performance suivant des règles web. | Validation finale objective, notamment focus, états, clavier, contrastes. | Complète les tests ; n'inspecte pas automatiquement une vraie UX sans navigateur. | **Priorité 2** pour audit. |
| [Context7](https://github.com/upstash/context7/blob/master/docs/clients/claude-code.mdx) | Documentation versionnée de bibliothèques dans Claude Code. | Éviter les APIs inventées pour React Flow, shadcn, Recharts, TanStack, etc. | Pas un « générateur de beau design ». | Optionnel si erreurs de doc ou libs récentes. |
| [Figma MCP officiel](https://help.figma.com/hc/en-us/articles/39888612464151-Claude-Code-and-Figma-Set-up-the-MCP-server) | Accès structuré à des maquettes et tokens **si l'équipe utilise Figma**. | Faire respecter le design approuvé plutôt qu'interpréter une image. | Aucun intérêt si l'équipe n'a ni fichier Figma ni intention de l'utiliser. | Conditionnel. |
| **Playwright MCP / Playwright Test** | Inspection réelle du navigateur et tests reproductibles. | Vérifier que l'UI est vraiment premium ET utilisable, pas seulement du JSX propre. | Nécessite app lancée et navigateurs configurés. | **Non négociable pour l'acceptation UI** (ou audit manuel documenté si indisponible). |

**Lecture de Reddit (signal qualitatif, pas benchmark scientifique) :**

- Un [fil `r/ClaudeDesign` du 2 octobre 2026](https://www.reddit.com/r/ClaudeDesign/comments/1wvfgec/best_claude_frontenddesignuxui_skill_set/) mentionne notamment **21st.dev**, **Impeccable**, l'inspiration depuis de vraies interfaces et des retours visuels itératifs.
- Le fil [`r/ClaudeCode` sur « AI slop »](https://www.reddit.com/r/ClaudeCode/comments/1p9srut/finally_figured_out_why_claudes_ui_generations/) insiste sur **une esthétique explicitement choisie** plutôt que « modern sleek dashboard ».
- Un autre [fil sur l'empilement de skills](https://www.reddit.com/r/ClaudeCode/comments/1u8c5qi/design_skills/) expose des retours mitigés et du chevauchement. La bonne stratégie n'est donc **pas** d'installer toutes les extensions virales.
- Des [retours Reddit sur Higgsfield MCP](https://www.reddit.com/r/claude/comments/1wf6rpy/how_do_you_create_nice_modern_websites_with_claude/) suggèrent un intérêt pour les vidéos/assets mais évoquent aussi le coût. **Aucun de ces commentaires ne prouve qu'il améliore la qualité d'un dashboard DeFi.**

**Conclusion opérationnelle :** les clips TikTok montrent souvent le résultat final et pas les essais ratés, le coût, les screenshots de correction ou les limites fonctionnelles. Pour ce hackathon, le « rendu pro » doit venir de **l'architecture de l'information, des tokens, d'une exécution précise, de données réelles et du contrôle en navigateur**.

### 19.2 Stack « premium mais sobre » : setup par paliers

#### Palier A — configuration indispensable (faire maintenant)

Dans **Claude Code** (si le plugin n'est pas déjà présent) :

```text
/plugin install frontend-design@claude-plugins-official
```

Dans le terminal du **projet**, en adaptant si Playwright est déjà configuré :

```bash
# Prérequis : Claude Code fonctionnel, environnement Node/npm compatible.
claude mcp add playwright npx @playwright/mcp@latest
claude mcp list
```

Après installation, demander à Claude de **vérifier** qu'il peut ouvrir le serveur local, cliquer, prendre une capture, lire la console et tester un changement de scénario. **Ne pas dire « installé » sans vérification.** Le plugin `frontend-design` peut connaître des incidents de marketplace : essayer `/plugin` ou la solution locale du §11 si nécessaire.

#### Palier B — polish pro (installer seulement après première version de l'Overview)

```bash
# Installer dans le repo, en suivant les invites officielles.
# Impeccable demande Node.js >= 22.18 lors de la consultation 2026.
npx impeccable install
```

Puis dans Claude Code :

```text
/impeccable init
/impeccable audit
/impeccable critique
/impeccable distill
/impeccable polish
```

**Important :** ces commandes sont des **outils de design**, non des commandes à exécuter aveuglément les unes après les autres. Utiliser la critique et l'audit, grouper les corrections, refaire des captures, puis arrêter. Le designer doit pouvoir dire « c'est suffisant ».

#### Palier C — composants et audits conditionnels

```bash
# 21st MCP actuel ; choisir `claude` au setup ; requiert compte et clé selon l'usage.
npx @21st-dev/cli@latest init --client claude

# Audit complémentaire Vercel (facultatif après Playwright).
npx skills add https://github.com/vercel-labs/agent-skills --skill web-design-guidelines

# Documentation technique vivante (facultatif, utile si API lib incertaine).
npx ctx7 setup --claude
```

- Avant de copier un composant 21st.dev : **examiner sa source et sa licence**, sa taille, ses dépendances, le focus clavier et sa compatibilité avec Tailwind/shadcn de FAULTLINE.
- Si un composant shadcn/ui existant suffit, **préférer le composant existant**. Ne jamais mélanger quatre systèmes de design sans nécessité.
- Ne pas suivre de tutoriels 2025 utilisant exclusivement l'ancien **Magic MCP** : il est maintenant regroupé dans **21st MCP** ; les anciennes clés Magic ont été réinitialisées ([migration officielle](https://github.com/21st-dev/magic-mcp/blob/main/llms-install.md)).
- Alternatives à choisir, pas à empiler : `npx ui-ux-pro-max-cli init --ai claude` pour enrichir les références esthétiques **à la place d'Impeccable** si ce style de workflow est préférable. Les deux peuvent coexister techniquement mais il faut **une seule autorité** de design pour FAULTLINE.

#### Palier D — Higgsfield, seulement avec un besoin clair et un budget validé

Pour **Claude Code**, la documentation **officielle** recommande la CLI :

```bash
# Commandes officielles : exécuter volontairement, pas dans un script d'install auto.
npm i -g @higgsfield/cli
higgsfield auth login
npx skills add higgsfield-ai/skills
```

Pour **Claude web/desktop**, la voie officiellement documentée est **Connectors → Higgsfield** avec l'URL `https://mcp.higgsfield.ai/mcp` puis authentification. Ce sont **deux voies différentes**. [CLI / MCP](https://higgsfield.ai/mcp?tab=claude-code) · [Guide d'intégration](https://higgsfield.ai/creator-hub/help-center/integrations/how-do-i-connect-higgsfield-to-ai-agent).

**Autorisation et budget :** demander l'accord humain avant tout achat, génération payante, connexion OAuth ou import d'actifs sensibles. La [documentation crédits Higgsfield](https://higgsfield.ai/creator-hub/help-center/credits/how-credits-work) décrit un coût variable par génération. Vérifier les droits d'usage et le format final avant intégration.

**Usage autorisé pour FAULTLINE :**

1. **Identité :** explorer 2–3 variantes statiques d'une texture de « faille / fracture » minimaliste, sans utiliser des logos de protocoles approximatifs ; choisir au plus une variante.
2. **Présentation :** éventuellement générer un court plan cinématique ou une vidéo de lancement **en dehors** de l'app de monitoring ; l'équipe décide si ce temps de démo vaut mieux qu'une simulation en direct.
3. **Asset utile :** créer un visuel statique pour l'état initial vide, une slide de pitch ou une zone non critique. Exporter un fichier local optimisé, revu à l'œil et soumis à licence.
4. **Interdit :** fabriquer des graphes de dépendance ou courbes de liquidation comme simples images, créer des faux résultats chiffrés, ajouter une vidéo pleine page gênant les contrôles, dépendre de Higgsfield pour rendre l'Overview.

**Règle de ROI :** s'il reste moins de 3 heures avant la démo ou si les P0 ne passent pas, **ne pas installer Higgsfield**. Le meilleur investissement est alors la correction de l'app et la fluidité du parcours jury.

### 19.3 Processus imposé à Claude — du brief au résultat « agence premium »

**Claude doit agir simultanément comme product designer et responsable QA, mais travailler par étapes explicites.** Pas de big-bang, pas d'« améliore toute l'UI » sans diagnostic.

**Étape 0 — Baseline et protection du projet (15–30 min)**

- Lire cette spécification et celle du challenge, `CLAUDE.md`, les composants, les routes, les contrats API et le code déjà implémenté.
- Capturer **l'existant** à `1440 × 900`, `1280 × 800` et `390 × 844` si une application tourne déjà, avec date et commit.
- Noter dans `docs/UI_BASELINE.md` ce qui marche, ce qui est cassé, les données mockées, les composants déjà disponibles. **Ne pas toucher aux calculs DeFi**.
- Préparer un plan de 4 jalons maximum, chaque jalon étant livrable et testable.

**Étape 1 — Brief et directions visuelles (20–40 min)**

- Résumer utilisateur, proposition de valeur, trois actions principales et démo de 90 s.
- Comparer **3 directions** très courtes (sans construire 3 apps) : (A) *Institutional Risk Terminal* — **préférée**, (B) *Editorial Fintech*, (C) *Dense Analytics Console*. Donner avantages/risques pour l'UX.
- Choisir **A par défaut** sauf si l'équipe fournit une direction contradictoire. **Verrouiller** la palette et les fonts du §4 au lieu d'itérer sans fin.
- Documenter : échelle d'espacement, bordures, radius, tailles textuelles, font pairs, iconographie, densité, hiérarchie, couleurs d'état, motion tokens ; créer `docs/DESIGN_DECISIONS.md`.
- Repérer 3 références fonctionnelles (DeFi Saver, Morpho, Gauntlet) et 2 références de qualité de finition (design system de shadcn / exemples 21st.dev si disponibles). **Réinterpréter**, ne pas cloner.

**Étape 2 — UX basse fidélité avant cosmétique (15–30 min)**

- Faire un layout simple de `Overview` avec : **risque principal**, **capital exposé**, **breaking point**, **impact**, **décision** et un grand composant analytique.
- Un seul **CTA primaire** pertinent par écran ; les actions de simulation doivent être évidentes.
- Le jury doit pouvoir répondre sans aide en 10 s : **« De quoi dépend ce portefeuille ? Qu'est-ce qui casse en premier ? Que perd-on ? »**
- Chaque terme (`health factor`, `dependency exposure`, `STAY / EXIT`, `slippage`) a un **tooltip d'une phrase** ou une aide contextuelle.
- Le bouton « voir pourquoi » doit permettre de remonter le **chemin de causalité** depuis l'impact jusqu'à la dépendance ; lien visible entre les vues.
- Ne pas cacher les fonctions P0 derrière un hover-only, un geste spécial, un onboarding ou un menu profond.

**Étape 3 — Implémenter un « vertical slice » impeccable (60–120 min)**

- Construire **un seul écran complet** avant de généraliser : shell, Overview et sélection d'une dépendance synchronisée avec le panneau `Breaking Point`.
- Utiliser des **composants contrôlés et des view-models typés** : la même sélection et le même scénario alimentent les vues. Définir explicitement `loading`, `error`, `empty`, `stale`, `unsupported`, `demo`, `success`.
- Mettre **des vrais graphiques SVG/canvas interactifs** pour les courbes et **React Flow** (ou stack existante) pour les liens de dépendances, pas des images « magnifiques » qui mentent sur les données.
- Fixer la première expérience sans connecter de wallet si un dataset d'exemple clairement labellisé facilite la démo ; ensuite permettre un changement de portefeuille.
- Conserver une **densité informative maîtrisée** ; desktop riche, mobile simplifié et scrollable, pas une copie écrasée du desktop.

**Étape 4 — Vérifier en navigateur et corriger en batches (2 tours maximum par jalon)**

- Démarrer le frontend, ouvrir **la vraie URL locale** avec Playwright.
- Capturer `1440 × 900`, `1280 × 800`, `390 × 844` ; si besoin `768 × 1024`.
- Lire les **erreurs console**, requêtes en échec et états de chargement ; vérifier focus clavier, click targets, scrolling, overlays, contrastes, `prefers-reduced-motion`.
- Effectuer un flux complet : sélectionner une dépendance → ouvrir son détail → modifier le choc → observer le breaking point / impact → consulter STAY/EXIT → revenir au scénario initial.
- Classer les défauts **bloquant / important / cosmétique** et les corriger **ensemble**. Faire une seconde capture après correction ; **ne pas continuer en boucle sans limite**.
- Demander à Impeccable de `critique` puis `polish` **uniquement** quand le parcours fonctionne. Utiliser les suggestions compatibles avec les tokens ; rejeter celles qui diminuent l'accessibilité ou créent une nouvelle charte.

**Étape 5 — « Design freeze » + vérification P0 (30–60 min)**

- Geler tokens et grands layouts après 2 cycles visuels. Priorité ensuite à la fiabilité, aux données et à la démo.
- Faire un dernier audit Vercel/web-design-guidelines si installé, plus Playwright Test, lint, build, types.
- Livrer captures avant/après, un tableau de tests avec statut et la liste des limitations **vraies**, y compris les modes `demo`, `stale` et les dépendances non modélisées.
- Fournir un parcours de démo « 90 secondes », sans réglage manuel délicat ni dépendance extérieure fragile.

### 19.4 Brief prêt à envoyer à Higgsfield (OPTIONNEL — assets seulement)

> Ne lancer cette génération que si l'équipe l'a approuvée et si un budget existe. L'objectif n'est **PAS** de faire dessiner les graphiques de risque par une IA générative.

```text
Create up to 3 VISUAL CONCEPT assets for FAULTLINE, a serious institutional
DeFi dependency-risk analysis app used by risk analysts. This is NOT a gaming,
crypto trading or memecoin product. The visual identity is a subtle fault line
or connected stress fracture: a precise technical trace on a dark slate ground.

Palette reference: #0A1018, #111A25, #293747, restrained #66D5E8 accent;
reserve orange/red for meaningful risk states in the actual product UI.

Deliver (1) a tasteful static SVG-like conceptual backdrop or raster equivalent
with generous negative space, (2) a minimalist wordmark exploration, and (3)
optionally a 3–5s silent product-intro motion study. No human figures,
no generic purple gradients, no 3D spinning coins, no neon cyberpunk,
no mock numerical data, no simulated protocol logos, no fake UI components.

This is DESIGN INSPIRATION, not executable product UI.
The existing React dashboard, live dependency graph and real financial charts
will be implemented separately by Claude Code. Prefer static assets; motion
is disposable and must not be part of the critical user path.
```

### 19.5 Prompt « directeur artistique + engineer » prêt à donner à Claude Code

```text
You are FAULTLINE's lead fintech product designer, senior React engineer and
visual QA lead. Build a PROFESSIONAL, UNDERSTANDABLE, CREDIBLE risk-analysis app,
not an animated startup marketing page.

FIRST read:
- docs/FAULTLINE_FRONTEND_RESEARCH_AND_CLAUDE_SPEC.md (especially sections 0,
  4, 11, 14, 15 and 19)
- CLAUDE.md and the official hackathon requirement verification document, if present
- actual repository/frontend/api data contracts

Working rules:
1. P0 correctness and usability > visual polish > optional modules > effects.
2. Activate Anthropic frontend-design if available; follow OUR design tokens.
   If installed, use Impeccable for AUDIT/CRITIQUE/POLISH after functionality.
   Use 21st.dev only when an existing UI component genuinely saves time.
3. Higgsfield is OPTIONAL: use only for bounded brand/visual assets with explicit
   approval for credentials and paid credits. Do NOT generate the graph/charts as
   images and do not replace the repo with a one-shot website builder.
4. Keep the UI immediately understandable: 3 navigation groups, clear scenario,
   plain-language tooltips, one primary action per screen, details on demand.
5. Strongly prioritize Breaking Point; graph, exposure, impact and STAY/EXIT
   must be logically connected through the same typed shared state.
6. No fake risk engine values, fake "LIVE" labels, arbitrary probabilities,
   decorative dead buttons, invisible important actions or invented API fields.
7. Before implementing: show a brief repository audit, design-system choices,
   implementation order, and exactly which 3–5 browser states you'll verify.
8. Implement the first complete Overview vertical slice before expanding.
9. Open the actual app with Playwright. Screenshot desktop and mobile. Test a
   real risk-analysis user journey. Fix all blockers and key visual defects.
   Do two bounded QA passes and deliver evidence (screenshots + test results).
10. Finish with a report: what is real vs simulated, what tests ran, what still
    needs work, and the 90-second jury demonstration walkthrough.

Definition of "looks professionally designed":
- visual hierarchy instantly highlights the primary risk and threshold;
- typography, alignment, density, borders, spacing and colors are consistent;
- readable charts with correct labels and provenance;
- purposeful micro-interactions, never animation noise;
- all states and responsive layouts feel intentionally designed;
- accessibility and functional correctness are not sacrificed for the hero shot.

If a plugin/skill isn't installed, report it and continue with available tools.
Never install paid tools, use paid credits, change credentials or overwrite
existing backend logic without explicit approval. Start with the repo audit.
```

### 19.6 Grille de validation visuelle/UX à exécuter avant de dire « terminé »

Une **note doit s'appuyer sur des captures et interactions**, pas sur l'impression de Claude. Sur chaque critère, marquer `PASS / FAIL / N/A` et une preuve (capture, URL, test ou composant). **FAIL critique bloque la livraison.**

| Domaine | Vérification concrète | Gravité si échec |
|---|---|---|
| Compréhension en 10 s | Test à froid : un juré identifie exposition, dépendance critique, premier seuil et impact sans explication. | **Bloquant** |
| Navigation | Trouver `Overview`, `Dependencies`, `Breaking Point` en un clic ; retour et état de sélection clairs. | **Bloquant** |
| Cohérence sémantique | Même asset/dépendance sélectionné dans graphe, métriques et stress ; même scénario/date. | **Bloquant** |
| Vérité des données | Provenance, snapshot et hypothèses accessibles ; aucun nombre fictif affiché comme réel. | **Bloquant** |
| Lisibilité graphes | Labels/unités, direction du choc, légende, tooltip accessible ; pas de graphes coupés. | **Bloquant** |
| Design system | Pas d'écart inexpliqué dans fonts, spacing, radius, couleurs, états et icônes. | Important |
| Hiérarchie | Une métrique majeure, accent de risque parcimonieux, zone « décision » facile à repérer. | Important |
| États UX | Chargement, erreur, vide, données périmées, unsupported, mode démo réellement gérés. | **Bloquant** |
| Actions | Chaque contrôle visible a un comportement ; pas de CTA décoratif ou désactivé sans raison. | **Bloquant** |
| Clavier / a11y | Focus visible, tab ordre logique, contraste, labels, accès aux infos graphes par voie alternative. | Important |
| Responsive | Pas de débordement à 390/768/1280/1440 px ; priorité au contenu et à un tableau accessible. | Important |
| Performance | Pas d'animation pesante en continu ; le graphe reste manipulable avec le dataset de démo. | Important |
| Sécurité / confiance | Pas de secrets côté client, pas de fake action exécutée, pas d'impression de transaction sans confirmation réelle. | **Bloquant** |
| Raffinement | Pixel alignment, espace négatif, icônes cohérentes, tooltips précis, hover/focus soignés. | Cosmétique/important |

**Livrables du QA** : `docs/UI_QA_REPORT.md`, captures `artifacts/ui/` (ou emplacement déjà prévu par le projet), tableau d'incidents trié par priorité et scripts de tests. **Ne pas affirmer que Playwright a tourné si seul un raisonnement sur le code a été fait.**

### 19.7 Garde-fou anti-surdesign / anti-perte de temps

Le contexte est un **hackathon sur le risque**, pas un concours de landing pages :

- **Investir 70 % du temps frontend** sur le chemin critique et la qualité des données/états, **20 %** sur design/QA, **10 % maximum** sur les assets optionnels. Ce sont des ratios indicatifs, à ajuster si P0 bloque.
- **Ne pas installer 5 skills redondants** et demander à tous de « prendre le contrôle ». Un design system écrit reste la source de vérité ; un outil = un rôle.
- **Higgsfield ≠ dépendance produit** : aucun chargement sur le parcours critique, aucune animation non essentielle sur Breaking Point, aucun rendu des chiffres de risque en image.
- **Pas de refonte du backend** pendant les passes de polish. Un faux chiffre joliment présenté est pire qu'une carte sobre et exacte.
- **L'UX est terminée quand l'utilisateur comprend et agit**, pas quand le dashboard ressemble à une compilation de tendances.

### 19.8 Liens officiels et sources complémentaires (consultés en octobre 2026)

1. [Higgsfield Website Builder](https://higgsfield.ai/skills/website) ; [CLI Claude Code](https://higgsfield.ai/mcp?tab=claude-code) ; [intégration](https://higgsfield.ai/creator-hub/help-center/integrations/how-do-i-connect-higgsfield-to-ai-agent) ; [crédits](https://higgsfield.ai/creator-hub/help-center/credits/how-credits-work).
2. [Anthropic — frontend-design](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/frontend-design/skills/frontend-design/SKILL.md), [Plugin officiel](https://claude.com/plugins/frontend-design).
3. [Impeccable — getting started](https://impeccable.style/tutorials/getting-started/) et [source GitHub](https://github.com/pbakaus/impeccable).
4. [21st MCP — migration et commandes](https://github.com/21st-dev/magic-mcp/blob/main/llms-install.md), [21st.dev](https://21st.dev/mcp).
5. [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) ; [Vercel agent-skills](https://github.com/vercel-labs/agent-skills) ; [Context7](https://github.com/upstash/context7/blob/master/docs/clients/claude-code.mdx) ; [Figma MCP](https://help.figma.com/hc/en-us/articles/39888612464151-Claude-Code-and-Figma-Set-up-the-MCP-server).
6. Discussions communautaires : [meilleurs skills de design](https://www.reddit.com/r/ClaudeDesign/comments/1wvfgec/best_claude_frontenddesignuxui_skill_set/), [anti-rendu générique](https://www.reddit.com/r/ClaudeCode/comments/1p9srut/finally_figured_out_why_claudes_ui_generations/), [stacking et limites](https://www.reddit.com/r/ClaudeCode/comments/1u8c5qi/design_skills/), [Higgsfield pour sites](https://www.reddit.com/r/claude/comments/1wf6rpy/how_do_you_create_nice_modern_websites_with_claude/).

---
