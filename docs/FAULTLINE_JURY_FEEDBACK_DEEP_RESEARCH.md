# FAULTLINE — Recherche approfondie sur le feedback du jury

> Statut : recherche uniquement (aucun code Phase 2). Date des mesures on-chain : bloc Ethereum 26 163 735–26 163 748 (≈ 10 oct. 2026, 18:12 UTC).
> Conventions : **[VERBATIM]** = citation exacte · **[FAIT]** = vérifié (code, doc officielle ou on-chain) · **[INTERPRÉTATION]** = notre lecture · **[HYPOTHÈSE]** = non vérifié · **[SECONDAIRE]** = presse/analyse tierce · **UNVERIFIED** = non confirmé.

---

## 1. Ce que le jury a réellement dit

Source : `docs/The Hackathon BSA.docx`, section des retours du jury.

| # | Verbatim | Portée |
|---|---|---|
| J1 | « est-ce qu'il y a mieux que sortir ? » | Question centrale |
| J2 | « comment sortir / mitiger / combien on perd » | Exigence de quantification |
| J3 | « enlever chain of blame » | Coupe de périmètre |
| J4 | « enlever part 3 préparer la sortie » | Coupe de périmètre (Exit Feasibility, Reaction Window, Telegram Ping) |
| J5 | « être spécifique pas général (prendre un protocole) » | Focalisation |

Ce qui **n'est pas** une parole du jury :
- Le texte « jury » de pré-présentation du docx relève du conseil de type assistant. Il n'est pas officiel.
- Les listes de stratégies (HOLD, REPAY, REINFORCE, DELEVERAGE, WAIT & EARN…) sont des propositions de l'équipe, avec des chiffres illustratifs.

La slide BSA distingue deux blocs :
- **Cœur demandé par Belem :** DÉCOUVRIR → SIMULER → DÉCIDER (STAY / EXIT / REVIEW).
- **Vision bonus :** les modules que le jury a demandé de retirer (J3, J4).

**Contradiction apparente entre J2 et J4.** [INTERPRÉTATION] Le jury ne rejette pas le *sujet* de la sortie. Il rejette un *bloc de fonctionnalités génériques* (alertes, fenêtres, Telegram) présenté comme une vision. Il demande au contraire que la décision du cœur réponde à « comment » et « combien », sur un protocole précis.

---

## 2. Interprétations classées de l'intention du jury

| Rang | Interprétation | Indices | Confiance |
|---|---|---|---|
| **1** | « Votre binaire STAY/EXIT est trop pauvre. Montrez les actions intermédiaires, chiffrées, et dites laquelle est la meilleure. » | J1 + J2 | Élevée |
| 2 | « Sortir a un coût et un effet de bord. Prouvez que la sortie est faisable et dites combien elle coûte réellement. » | J2 (« comment sortir ») | Élevée |
| 3 | « Choisissez un protocole et allez au fond de sa mécanique plutôt que d'empiler des modules. » | J5 + J3/J4 | Élevée |
| 4 | « Pour un investisseur institutionnel, mitiger (réduire, attendre rémunéré, conditionner) est souvent supérieur à fuir. » | J1 | Moyenne |
| 5 | « Sortir en premier transfère le risque aux autres déposants : quel est votre rôle ? » | Implicite | Faible (non dit) |

**Conclusion de lecture.** La demande est une **décision multi-actions, chiffrée, sur un protocole unique (Morpho)**. La sortie y devient *une option parmi d'autres*, avec son coût exact, et non un module « préparer la sortie ».

---

## 3. Qui est Belem, et donc qui est l'utilisateur

| Élément | Statut | Détail |
|---|---|---|
| Belem Capital = AIF luxembourgeois donnant accès à la DeFi à des investisseurs professionnels | [SECONDAIRE] | Site et communication Belem ; méthode : profondeur de liquidité, audit, gouvernance, historique |
| Vault « Belem RWA EURCV » `0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec` = Morpho Vault V2, actif EURCV | [FAIT] on-chain | |
| Owner = curator = `0xbBacDCFB…f918` (RockawayX) ; allocators `0x1CDa83fE…ba02`, `0x22D4dbFf…676A` ; sentinel `0x040EAaCb…3A47` | [FAIT] on-chain + attribution [SECONDAIRE] | **Belem n'est pas le curateur**, ni l'allocateur |
| Frais : performance 10 %, management 0 | [FAIT] `performanceFee()` / `managementFee()` | |
| Gates : toutes à `address(0)`, donc retrait non gaté | [FAIT] | |

**Conséquence de conception [INTERPRÉTATION, forte].** L'utilisateur de FAULTLINE est un **déposant institutionnel** (Belem ou ses clients). Il ne peut pas réallouer, plafonner ni liquider. Ses seuls leviers sont :
- retirer ou rester ;
- choisir *la route* de sortie (ordinaire ou `forceDeallocate`) ;
- retirer partiellement ;
- attendre avec des déclencheurs ;
- faire pression sur le curateur.

Les actions emprunteur (repay, add collateral) **ne sont pas** ses actions. Ce sont des *facteurs de risque* qui pèsent sur lui.

---

## 4. Mécanique Morpho : faits vérifiés utiles à la décision

Sources principales :
- code `morpho-org/morpho-blue` `src/Morpho.sol` (commit `ab064b6`) ;
- `morpho-org/vault-v2` `src/VaultV2.sol` (sha `1c292f9`) et `ConstantsLib.sol` ;
- `morpho-org/morpho-blue-irm` ;
- docs.morpho.org (pages vivantes, non datées, consultées en oct. 2026).

| Mécanisme | Fait | Effet sur le déposant | Source |
|---|---|---|---|
| Liquidation | Liquidable si `borrowed > collateral·price·LLTV`. Pas de close factor. LIF = min(1.15, 1/(0.3·LLTV+0.7)) | Pour LLTV 77 % : LIF = 1,0741 | `Morpho.sol::liquidate`, https://docs.morpho.org/learn/concepts/liquidation/ |
| Bad debt Blue | Réalisée **atomiquement** dans `liquidate()` quand le collatéral atteint 0 : soustraite de `totalSupplyAssets` | Perte immédiate pour les prêteurs du marché isolé | `Morpho.sol::liquidate` (branche bad debt) |
| Perte Vault V2 | `accrueInterestView` : `newTotalAssets = min(realAssets, maxTotalAssets)`. Les gains sont plafonnés par `maxRate`, **les pertes passent immédiatement** | Le prix de part chute à la prochaine interaction | `VaultV2.sol` |
| Retrait Blue | Revert `INSUFFICIENT_LIQUIDITY` si `totalBorrow > totalSupply` après retrait | Liquidité = supply − borrow | `Morpho.sol::withdraw` |
| `maxWithdraw` V2 | Retourne **toujours 0** (`pure`) | Inutilisable pour mesurer la capacité ; il faut simuler | `VaultV2.sol` « MAX FUNCTIONS » |
| `liquidityAdapter` | Les retraits puisent dans idle puis dans **un seul** marché désigné | Capacité ordinaire = idle + liquidité de ce marché | https://docs.morpho.org/learn/concepts/vault-v2/ |
| **`forceDeallocate`** | **Permissionless**, pénalité ≤ 2 % (`MAX_FORCE_DEALLOCATE_PENALTY = 0.02e18`), fixée par le curateur sous timelock | Le déposant peut lui-même rapatrier la liquidité d'**autres** marchés vers l'idle, puis redeem | `VaultV2.sol::forceDeallocate`, https://docs.morpho.org/learn/concepts/vault-v2/ |
| In-kind redemption | Flashloan → supply dans le marché → `forceDeallocate` → retrait → remboursement. Le déposant finit **prêteur direct** du marché | Change la forme de l'exposition, **ne crée pas de liquidité** | https://docs.morpho.org/curate/concepts/liquidity/ |
| Flash loans Blue | Gratuits | Rend l'in-kind et le deleverage atomiques sans capital | `Morpho.sol::flashLoan` |
| AdaptiveCurveIRM | u* = 90 %, k_d = 4, k_p = 50/an. À u = 100 % : r = 4·r_T. r_T double en ln2/50 an ≈ **5,06 j** ; borné à [0,1 %, 200 %] | « Attendre rémunéré » : le rendement monte, mais le retour de liquidité reste **comportemental** | https://docs.morpho.org/developers/contracts/irm/ |
| Timelocks V2 | 0 à 3 semaines par sélecteur. Les actions réduisant le risque (baisse de cap, deallocate) ne sont pas timelockées | Le curateur peut dé-risquer vite ; une hausse de pénalité de sortie est timelockée | `VaultV2.sol`, https://docs.morpho.org/curate/tutorials-v2/emergency/ |
| Pre-liquidation | Opt-in **emprunteur** (preLLTV, preLCF, preLIF). Aucun équivalent prêteur | Hors levier déposant | https://morpho.org/blog/introducing-pre-liquidations-enhanced-loan-management-on-morpho/ |
| Public Allocator | `reallocateTo()` permissionless, payant, borné par flow caps | **Concerne MetaMorpho V1** ; non pertinent pour ce vault V2 | `morpho-org/public-allocator` |

---

## 5. État live du cas Belem (preuves on-chain)

Bloc 26 163 748. Mesures en EURCV, avec EURCV ≈ 1,1194 USD.

| Marché | Part du vault | Utilisation | LLTV | Liquidité libre | Borrow APY | rateAtTarget (APR) |
|---|---|---|---|---|---|---|
| mGLOeuro (`0x987b…19b0`, liquidityAdapter) | 85,8 % | 91,0 % | 0,77 | 361 743 | 3,40 % | 2,52 % |
| WBTC | 9,7 % | 89,1 % | 0,86 | 501 575 | 1,97 % | 1,96 % |
| cbBTC | 2,5 % | 89,5 % | 0,86 | 1 412 711 | 1,92 % | 1,92 % |
| wstETH | 2,1 % | 89,7 % | 0,86 | 179 725 | 1,97 % | 1,96 % |
| steakEURCV, oTFYe | ≈ 0 | — | — | — | — | — |

**Concentration emprunteur [FAIT].** Le marché mGLOeuro a un emprunteur dominant, `0xa122…E7c6`, avec une dette de 3 678 924 EURCV. Il représente 99,99 % de la dette du marché, à un LTV de 0,6997 pour un LLTV de 0,77. Le vault fournit 100 % de l'offre du marché.

- Liquidation déclenchée si le prix oracle de mGLOeuro baisse de **9,1 %** (1 − 0,6997/0,77).
- Bad debt si la baisse dépasse **24,8 %** (1 − 0,6997 × 1,0741).

L'oracle est de type NAV (Fasanara → Midas/eOracle → haircut Steakhouse), mis à jour par la NAV. Le risque porte donc sur une **révision de NAV** ou une **défaillance d'oracle**, pas sur la volatilité de marché [SECONDAIRE pour la chaîne d'oracle].

**Expérience clé [FAIT, simulation lecture seule].** Un redeem simple de $1M (893 330 EURCV) **revert**, car la capacité ordinaire n'est que de 361 743 EURCV. En revanche, ce multicall réussit :

`VaultV2.multicall([forceDeallocate(WBTC), forceDeallocate(cbBTC), redeem])`

- `eth_simulateV1` : status 1, gas 570 473 ;
- pénalité 0 ;
- Withdraw de 893 330,37 EURCV.

**La sortie totale de $1M est exécutable maintenant, à coût quasi nul.** Le produit actuel affiche « partial : $405k now / $595k blocked » : il **sous-estime** la sortie.

Détails : `docs/FAULTLINE_COUNTERMOVE_TECHNICAL_AUDIT.md` §3.

**Externalité [FAIT, calcul].** Après cette sortie :
- l'utilisation du marché mGLOeuro passe à 98,9 % ;
- le vault restant (≈ 3,82M EURCV) est à **97,4 % en mGLOeuro**.

Le risque est transféré aux déposants restants. C'est la dynamique de run (Diamond–Dybvig).

---

## 6. Matrice des stratégies : emprunteur vs déposant (séparées)

### 6.1 Stratégies DÉPOSANT (utilisateur cible de Belem)

| Stratégie | Faisable on-chain ? | Ce qu'il faut calculer | Sources / précédents | Pertinence Belem |
|---|---|---|---|---|
| **HOLD** | Oui | EL(H) + carry gagné | — | Base de comparaison |
| **FULL EXIT, route ordinaire** | Jusqu'à idle + liquidité du liquidityAdapter | Friction et gas simulés | `simulate_redeem` existant | Bloquée au-delà de 361k EURCV |
| **FULL EXIT, route forceDeallocate** | Oui, si la liquidité existe dans d'autres marchés. Pénalité ≤ 2 % | Pénalité × montant + gas (~570k) ; tx atomique | Docs V2 ; **prouvé live** | **Faisable maintenant à 0 %** |
| **PARTIAL EXIT (w)** | Oui | EL évitée = EL·w ; carry perdu = carry·w ; coût de la tranche ; risque résiduel (1−w) dont la sortie future est incertaine | Linéarité testée (`test_v14`) | Utile si les bandes se chevauchent |
| **WAIT & EARN** | Oui | Projection IRM : si u → 100 %, l'APY monte (4·r_T, doublement / 5 j) ; probabilité de retour de liquidité | docs IRM ; Telos (nov. 2025) a relevé les taux plutôt que liquider [SECONDAIRE] | Réponse directe à J1, mais conditionnelle |
| **CONDITIONAL / TRIGGERS** | Off-chain (surveillance), exécution on-chain | Seuils : LTV emprunteur, prix oracle (−9,1 % / −24,8 %), utilisation, liquidité force-deallocatable, pénalité | Pratique des curateurs (killswitch Steakhouse ~90 %) [SECONDAIRE] | **Meilleure réponse à « mieux que sortir »** |
| **IN-KIND REDEMPTION** | Oui (flashloan gratuit) | Change la forme d'exposition (part de vault → supply Blue direct) | Docs V2 | Utile seulement si aucune liquidité ; ne réduit pas le risque mGLOeuro |
| **Pression curateur / gouvernance** | Hors chaîne | — | Lista DAO vs Re7 (nov. 2025) [SECONDAIRE] | Hors outil (à mentionner) |
| **Assurance** | Oui (OpenCover / Nexus) | Prime vs EL couverte | OpenCover Covered Vaults [SECONDAIRE] | Couvre smart contract / oracle étroit, **pas** le risque de contrepartie RWA |

### 6.2 Stratégies EMPRUNTEUR (contexte, pas l'utilisateur de Belem)

| Stratégie | Mécanique | Outils existants |
|---|---|---|
| REPAY (partiel / total) | `repay()`, sans auth sur `onBehalf` | DeFi Saver, app Morpho |
| REINFORCE (add collateral) | `supplyCollateral()` | idem |
| DELEVERAGE atomique | Bundles `blueBundlesV1RepayAndWithdrawCollateral`, flashloan gratuit | Morpho Bundles, DeFi Saver |
| Pre-liquidation | Opt-in preLLTV | Morpho |
| « Repay minimal pour survivre à un choc X » | min Δdebt tel que LTV·(1−X) < LLTV | **Aucun outil trouvé** [absence de preuve] |

**Pourquoi la séparation est essentielle.** Le cas Phase 0.5 (emprunteur PT) et le cas Phase 1 (déposant de vault) n'ont **pas** le même ensemble d'actions. Mélanger « REPAY » dans une recommandation à un déposant serait une erreur de domaine.

---

## 7. Concurrence et pratique institutionnelle

| Outil | Côté | Compare des actions économiquement ? | Simulation on-chain ? | Lacune comblable |
|---|---|---|---|---|
| DeFi Saver / Summer.fi / Instadapp | Emprunteur | Non (règles) | Aperçu mécanique | Aucune logique déposant |
| Morpho pre-liquidation | Emprunteur | Non | — | Pas d'équivalent prêteur |
| Gauntlet / Chaos Labs | Curateur / protocole | Paramètres, pas par déposant | Backtests | Ne sert pas le déposant individuel |
| Steakhouse / Block Analitica / LlamaRisk | Curateur / analyste | Politique implicite | Non | Descriptif |
| Credora (RedStone) | Notation | Non (score) | Non | Statique |
| Hypernative / Hexagate | Infrastructure | Binaire (pause ou non) | Oui, côté protocole | Autre problème |
| **DeFiLlama « Verified Yields / Exit Status »** | Déposant | **Partiel** (données de sortie, pas de recommandation) | **Oui** (retrait réel simulé chaque jour) | Pas de graphe de dépendances Morpho, pas d'EL, pas de décision |
| OpenCover Covered Vaults | Déposant (assurance) | n/a | n/a | Ne couvre pas curateur / contrepartie |

Source principale de l'art antérieur le plus proche : https://newsletter.defillama.com/p/we-built-a-way-to-see-what-yield-pools-actually-pay-out [SECONDAIRE, consulté oct. 2026].

**Honnêteté sur la nouveauté.** La simulation de sortie *en soi* n'est pas nouvelle (DeFiLlama). Ce qui n'existe pas, c'est une décision **déposant** qui fusionne trois éléments :
- **dépendances Morpho** ;
- **perte attendue** ;
- **route de sortie exécutable**, y compris `forceDeallocate`.

Cette décision compare HOLD, PARTIAL, EXIT et WAIT.

---

## 8. Incidents de référence

| Événement | Date | Faits | Leçon pour FAULTLINE | Source |
|---|---|---|---|---|
| Stream Finance / xUSD | 4 nov. 2025 | Perte de $93M annoncée. xUSD −75 à −88 %. Marchés isolés à 100 % d'utilisation. Expositions : Re7 (~$27M), MEV Capital (~$34M), Telos (~$124M estimé), Silo ($15,4M) | Illiquidité ≠ perte, mais elle **précède** la perte. Les premiers sortis s'en sortent. Telos a **relevé les taux** au lieu de liquider. | https://x.com/StreamDefi/status/1985556360507822093 ; https://protos.com/stream-finance-meltdown-winners-and-losers-in-defi-risk-curator-reckoning/ [SECONDAIRE] ; https://silofinance.medium.com/stream-finance-incident-transparency-report-cc21fb76f0b5 |
| Position de Morpho | 4 nov. 2025 | Frambot : « only 1 out of ~320 vaults… had limited exposure » | L'isolement fonctionne ; le risque est **par vault** | https://x.com/PaulFrambot/status/1985702190820807046 |
| Post-incident | nov. 2025 | Credora intégré à Morpho (scores de risque) | Le marché veut des signaux de risque par vault | https://x.com/MerlinEgalite/status/1986458349542805617 |
| Euler hack | mars 2023 | ~$197M drainés, ~$240M récupérés en ~3 semaines | Attendre a payé, mais grâce à une négociation, pas à un mécanisme | blog euler.finance [SECONDAIRE] |
| USDC / SVB | mars 2023 | USDC ≈ $0,87, puis retour au pair | Attendre a payé **grâce à un backstop public** : ne pas sur-vendre le « wait » | UNVERIFIED (source primaire à confirmer) |

---

## 9. Ce que la recherche confirme et contredit

**Confirme :**
1. Un déposant de vault Morpho V2 dispose d'un levier rarement montré : **`forceDeallocate`, permissionless**. Sur Belem il est à pénalité 0, et il rend la sortie totale possible aujourd'hui (prouvé live).
2. « Mieux que sortir » existe et se chiffre :
   - attendre rémunéré (l'IRM pousse le rendement quand la liquidité se tend) ;
   - sortie partielle ;
   - **rester avec des déclencheurs précis** (−9,1 % / −24,8 % sur la NAV mGLOeuro, utilisation, liquidité force-deallocatable).
3. Il n'existe pas d'outil déposant qui compare économiquement ces actions.
4. Pour Belem, l'EL sur 30 jours ($632 central) est inférieure au carry ($2 149). **Rester est économiquement défendable aujourd'hui**, à condition de surveiller les bons seuils.

**Contredit ou nuance :**
1. Les stratégies emprunteur (REPAY, REINFORCE, DELEVERAGE) ne s'appliquent **pas** au déposant Belem.
2. « Wait & Earn » n'est **pas** garanti. La hausse d'IRM est une incitation ; le retour de liquidité est comportemental. Au-delà d'un seuil, attendre rend la sortie moins accessible (cas Stream).
3. Le produit actuel **sous-estime** la sortie. L'affirmation « partial / blocked » est fausse en présence de `forceDeallocate` à pénalité 0.
4. Le Public Allocator ne s'applique pas à ce vault V2.

---

## 10. Questions à poser à Belem

1. Votre rôle sur ce vault : simple déposant/distributeur, ou avez-vous un accord avec RockawayX (curateur) sur la pénalité `forceDeallocate`, les caps ou des alertes ?
2. Quelle est votre tolérance à une concentration de 86 % sur un seul marché (mGLOeuro) et à **un seul emprunteur** ? Le cadre RockawayX sur le forum Morpho laisse « No single market exceeds [TBD]% ».
3. Quelle est la fréquence et la gouvernance de la NAV mGLOeuro (Fasanara / Midas), et existe-t-il une clause de rachat au pair ?
4. Quel horizon et quel montant type par décision ($1M / 30 j est notre hypothèse) ?
5. Acceptez-vous une recommandation « HOLD + déclencheurs » plutôt qu'un binaire STAY/EXIT ?
6. Considérez-vous l'externalité de sortie (risque transféré aux autres déposants) comme un critère de décision ?

---

## 11. Sources (consultées oct. 2026, sauf mention)

**Code et doc officiels Morpho :**
- `morpho-org/morpho-blue` `src/Morpho.sol` (commit `ab064b646bf161b1510e2575a99412cdc2a43ebb`)
- `morpho-org/vault-v2` `src/VaultV2.sol` (`1c292f9f…`), `src/libraries/ConstantsLib.sol` (`d87ff28b…`), `src/adapters/MorphoMarketV1AdapterV2.sol` (`b5c99cc1…`)
- `morpho-org/morpho-blue-irm` `AdaptiveCurveIrm.sol`, `ConstantsLib.sol`
- https://docs.morpho.org/learn/concepts/liquidation/
- https://docs.morpho.org/learn/concepts/vault-v2/
- https://docs.morpho.org/curate/concepts/liquidity/
- https://docs.morpho.org/curate/concepts/gates/
- https://docs.morpho.org/curate/tutorials-v2/emergency/
- https://docs.morpho.org/developers/contracts/irm/
- https://docs.morpho.org/developers/contracts/bundles/
- https://morpho.org/blog/introducing-pre-liquidations-enhanced-loan-management-on-morpho/

**Incidents :** liens du §8 (X primaires, Protos, Silo).

**Art antérieur :** https://newsletter.defillama.com/p/we-built-a-way-to-see-what-yield-pools-actually-pay-out.

**Littérature :**
- FMI WP/26/74 « Making Stablecoins Stable » (avr. 2026)
- Banque du Canada SAP 2026-13
- arXiv 2506.12855
- BIS WP 1164 (conclusions UNVERIFIED)

**On-chain :** RPC public https://1rpc.io/eth, blocs 26 163 735–26 163 748 ; API prod FAULTLINE `/api/vault`.

**Rapports de recherche bruts (session) :** mécanique Morpho, concurrence, contexte Belem. Les éléments marqués UNVERIFIED y sont listés.
