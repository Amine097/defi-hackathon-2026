# FAULTLINE — Audit technique « Countermove »

> Objet : vérifier ce que le backend sait déjà faire pour répondre à « est-ce qu'il y a mieux que sortir ? ». Contrôler la cohérence économique de la sortie partielle et lister les manques. Aucun code modifié.
> Code audité : `main` @ `8f577ef`. Preuves live : bloc 26 163 735–26 163 748 (≈ 10 oct. 2026).

---

## 1. Inventaire réutilisable

### 1.1 Côté vault (déposant), `src/defirisk/vault_model.py`, `vault_reader.py`, `uncertainty.py`

| Fonction | Fichier:ligne | Ce qu'elle fait (vérifié) | Réutilisable pour Countermove |
|---|---|---|---|
| `reads()` | `vault_model.py:46` | Simule le redeem complet. Si échec, simule un redeem partiel à 99,9 % de la capacité | Oui, base de la route ordinaire |
| `capacity(snap, liquidity_factor)` | `vault_model.py:117` | V2 : idle + min(supply du vault, liquidité) du **seul** marché `liquidityData`. Lignes `force_rows` séparées avec la pénalité de l'adapter | Oui. Les `force_rows` sont déjà calculées |
| `bad_debt_fraction`, `oracle_drain_fraction` | `vault_model.py:~154`, `:183` | Fraction de perte d'un marché après un choc | Oui, pour les seuils déclencheurs |
| `build_graph(..., sev, liquidity_factor)` | `vault_model.py:199` | Graphe de dépendances avec sévérités | Oui |
| `assess()` | `vault_model.py:358` | EL, bandes, exécution, carry, verdict | À étendre (voir §2) |
| `scenarios()` | `vault_model.py:684` | Crash de collatéral, oracle, marché, crise de liquidité (`liquidity_factor=0`), corrélé, depeg, choc custom | Oui |
| `sensitivity()` | `vault_model.py:732` | Tornado, courbe de crash, multiplicateur de breakeven | Oui |
| `read_market` | `vault_reader.py:115` | Utilisation, taux, liquidité, IRM par marché | Oui. Ajouter `rateAtTarget` (lecture déjà faite manuellement, §4) |
| `borrowers` | `vault_reader.py:150` | Dette et LTV par emprunteur | Oui, pour les déclencheurs |
| `api_withdrawal_options` | `vault_reader.py:382` | API Morpho : liquidité force-deallocatable et pénalité par adapter | Oui (contrôle croisé) |
| `simulate_redeem`, `_with_shares`, `_share_slot` | `vault_reader.py:413–433` | `eth_call` redeem avec override du solde de parts (slot V2 = 12) | Oui. Généraliser en `simulate_calls(multicall)` |
| `max_withdraw_v1` | `vault_reader.py:459` | `maxWithdraw` MetaMorpho V1 | Oui (V1) |
| `loss_band`, `exit_band`, `robust_signal` | `uncertainty.py:170/209/224` | Bandes ±, verdict REVIEW si les bandes se chevauchent | Oui. **Le signal « cannot discriminate » existe déjà** |

### 1.2 Côté emprunteur, `src/defirisk/morpho.py`, `leverage.py`

| Fonction | Fichier:ligne | Réutilisable |
|---|---|---|
| `liquidation_incentive_factor` | `morpho.py:61` | Oui |
| `max_borrow`, `borrower_state`, `compute_state` (HF, prix de liquidation, distance, buffer) | `morpho.py:65/131/161` | Oui : base de « repay minimal pour survivre à X » |
| `liquidation_outcome(state, drop)` | `morpho.py:185` | Oui |
| `borrow_rate_view`, `accrue`, `market_rates` | `morpho.py:92/106/220` | Oui (projection d'intérêts) |
| `_borrower_decision` | `leverage.py:96` | HOLD vs vente de **tout** le collatéral (quote Pendle `simulate=False`) + gas repay de 120k (hypothèse, `leverage.py:22`). **Pas de repay partiel, pas d'ajout de collatéral, pas de carry** |

---

## 2. Cohérence économique de la sortie partielle (P1)

### 2.1 Ce que fait le code

Toutes les références sont dans `vault_model.assess` :

| Terme | Calcul actuel | Base |
|---|---|---|
| Perte attendue EL, bande de perte | Graphe et MC sur **V complet** | Totale |
| Friction d'exécution | Redeem complet simulé si OK ; **sinon redeem partiel à 99,9 % de la capacité** (l. 505–508) | **Partielle** si le complet revert |
| Gas | Celui de la simulation retenue | Partielle ou totale |
| Carry | `carry_usd = V · net · H/365` (l. 524) | **Totale** |
| Côté sortie | `exit_band(ex, cr)` = exécution + carry (l. 546) | Mixte |
| Verdict | `robust_signal(loss_band, exit_band)` (l. 597) ; EXIT rétrogradé en REVIEW si `feas != "full"` (l. 599–604) | — |
| Note | « partial: exit $X now » si REVIEW penche EXIT (l. 613) | Texte seulement |

### 2.2 Le défaut

Lorsque `feas = "partial"`, on compare :

$$EL_{\text{total}} \quad\text{vs}\quad \text{exec}_{\text{partiel}} + \text{carry}_{\text{total}}$$

Or une action réellement exécutable de fraction $w = \text{imm}/A$ produit :

| Terme | Valeur cohérente |
|---|---|
| Perte évitée | $EL \cdot w$ (EL linéaire en exposition, couvert par `test_v14_linear_in_exposure`) |
| Carry abandonné | $\text{carry} \cdot w$ |
| Exécution | $\text{exec}_{\text{partiel}}$ (tranche $w$) |
| Résiduel | $EL \cdot (1-w)$ toujours exposé, avec une sortie future incertaine |

La règle cohérente pour la tranche est $EL\cdot w$ vs $\text{exec}_w + \text{carry}\cdot w$, soit $EL$ vs $\text{exec}_w/w + \text{carry}$. Le code compare $EL$ vs $\text{exec}_w + \text{carry}$. **Il mélange des coûts partiels et totaux**, ce que l'exigence interdit.

**Impact chiffré sur Belem.** Négligeable : exec = $0,06, donc $0,06/0,405 = $0,16. Le verdict ne change pas. **Le défaut est conceptuel, mais réel.** Sur un vault à forte friction (MetaMorpho V1 avec des marchés illiquides), il biaise vers EXIT.

### 2.3 Le défaut le plus grave : la capacité est sous-estimée (P0)

Le code (l. 573–578) dit explicitement :

> `forceDeallocate` … « NOT part of the standard exit, not simulated, not used in the verdict »

**Preuve live.** Lecture seule ; aucune transaction envoyée. Script de session `exp_force_dealloc.py`.

| Test | Bloc | Résultat |
|---|---|---|
| `redeem(892 509,36 parts)` = 893 330,36 EURCV ($1M) | 26 163 739 | **revert : insufficient liquidity** (capacité ordinaire 361 743 EURCV) |
| `VaultV2.multicall([forceDeallocate(adapter, WBTC params, 0,999·dispo, 0xdEaD), forceDeallocate(adapter, cbBTC params, …), redeem(parts, 0xdEaD, 0xdEaD)])` via `eth_call` | 26 163 739 | **succès** ; `eth_estimateGas` = 647 152 |
| Même multicall via `eth_simulateV1` (https://1rpc.io/eth) | 26 163 745 | status 1 ; gasUsed **570 473** ; deallocations WBTC 455 097,10 + cbBTC 116 324,27 (force) + mGLOeuro 321 909,00 (liquidityAdapter) ; **pénalité 0 / 0** ; Withdraw **893 330,37 EURCV** pour 892 509,36 parts |

Détails de la reproduction :
- Override d'état sur le solde de parts de `0xdEaD`, slot 12 vérifié.
- Adapter `0xA671880d813D4cacaCA63984bc0Ab676c400A874` (MorphoMarketV1AdapterV2, seul adapter), `forceDeallocatePenalty = 0`.
- Signature `forceDeallocate(address adapter, bytes data, uint256 assets, address onBehalf)` avec `data = abi.encode(MarketParams)`.

**Conséquences :**
1. L'API prod affiche pour Belem $1M « partial — immediate $404 938, blocked $595 062 ». **C'est faux** : la sortie totale est exécutable atomiquement, à friction ≈ 0 et pénalité 0, pour ~570k de gas.
2. Les scénarios de crise de liquidité (`liquidity_factor = 0`) annulent aussi la liquidité des autres marchés. Ils sont donc cohérents. En revanche, les scénarios de crash gardent la liquidité au facteur 1, donc la sortie y est **aussi** sous-estimée.
3. Une simulation de redeem qui réussit au-delà de la capacité ordinaire n'est signalée que par un warning (l. 487–488).

**Réserves à afficher (pas des blocages) :**
- La pénalité est modifiable par le curateur (≤ 2 %, timelockée ; durée du timelock **UNVERIFIED** pour ce sélecteur).
- La capacité est **partagée** : premier arrivé, premier servi.
- La liquidité des marchés WBTC et cbBTC appartient aussi à d'autres prêteurs.

### 2.4 Externalité de sortie (non modélisée)

Après la sortie de $1M simulée :
- utilisation mGLOeuro : 91,0 % → **98,9 %** ;
- vault restant ≈ 3,82M EURCV, dont **97,4 % en mGLOeuro**.

Le code n'expose qu'un drapeau `shared_with_other_depositors: True`. Aucun chiffre.

### 2.5 Chemin Phase 0.5 (emprunteur PT)

`api_payload._with_carry` (l. 40) applique un carry sur la position totale. **C'est cohérent ici**, car la sortie PT est une vente totale exécutable. Aucune action partielle n'y est proposée.

---

## 3. Données manquantes et lectures ad hoc déjà validées

Lecture manuelle (shell de session), bloc 26 163 748, IRM `0x870ac11d…00bc`. Elle **n'est pas** dans le code produit.

| Marché | u | rateAtTarget (APR) | Borrow APR à u = 100 % | Emprunteur max (LTV / LLTV) |
|---|---|---|---|---|
| mGLOeuro | 91,05 % | 2,524 % | **10,09 %** | `0xa122…E7c6` 3,68M EURCV, 0,700 / 0,77 |
| WBTC | 89,1 % | 1,962 % | 7,85 % | 0,602 / 0,86 |
| cbBTC | 89,5 % | 1,915 % | 7,66 % | 0,726 / 0,86 |
| wstETH | 89,7 % | 1,957 % | 7,83 % | 0,453 / 0,86 |

Projection mGLOeuro si l'utilisation reste à 100 % (k_p = 50/an, borne 200 %) :

| Jours | r_T | Borrow APR (= supply APR à u = 1, fee 0) |
|---|---|---|
| 0 | 2,52 % | 10,1 % |
| 5 | 5,01 % | 20,0 % |
| 10 | 9,93 % | 39,7 % |
| 20 | 39,1 % | 156 % |

Seuils dérivés pour l'emprunteur dominant de mGLOeuro (LIF = 1,0741) :

| Seuil | Formule | Valeur |
|---|---|---|
| Début de liquidation | $1 - LTV/LLTV$ | **−9,1 %** sur le prix oracle (NAV) |
| Début de bad debt | $1 - LTV \cdot LIF$ | **−24,8 %** |

Cohérent avec la courbe de crash de l'API prod : perte 0 à −20 %, $53 529 à −30 %, $157 451 à −40 %.

---

## 4. Ce qui manque pour un « Countermove » déposant

| # | Manque | Priorité | Réutilise |
|---|---|---|---|
| M1 | **Route `forceDeallocate` simulée.** Construire le multicall (force sur les marchés non-liquidityAdapter, triés par liquidité, puis redeem), le simuler avec `eth_call` / `eth_estimateGas`, intégrer la pénalité et le gas | **P0** | `simulate_redeem`, `capacity().force_rows`, `api_withdrawal_options` |
| M2 | **Économie partielle cohérente.** Toutes les grandeurs indexées par $w$ ; ne jamais mélanger partiel et total | **P0** | `assess`, `uncertainty` |
| M3 | **Comparateur multi-actions** HOLD / PARTIAL(w) / FULL-ordinaire / FULL-force / WAIT avec déclencheurs, réutilisant `robust_signal` pour « cannot discriminate » | P1 | `uncertainty.robust_signal` |
| M4 | **Projection IRM** (`rateAtTarget`, courbe, vitesse) pour WAIT & EARN | P1 | `read_market`, `morpho.accrue` |
| M5 | **Déclencheurs chiffrés** : seuils de NAV ou oracle (liquidation, bad debt), utilisation, liquidité force-deallocatable, pénalité, LTV emprunteur | P1 | `borrowers`, `morpho.compute_state`, `liquidation_outcome` |
| M6 | **Externalité de sortie** : composition du vault et utilisation après sortie | P2 | `capacity`, `read_market` |
| M7 | Scénarios de crash utilisant aussi la route `forceDeallocate` | P2 | `scenarios` |
| M8 | « Repay minimal / collatéral minimal pour survivre à X » (emprunteur) | P3, hors cible Belem | `morpho.compute_state` |

---

## 5. Correctifs recommandés (Phase 2, par ordre)

| ID | Gravité | Correctif | Test d'acceptation |
|---|---|---|---|
| F1 | **P0** | `feasibility` distingue `ordinary` / `with_force_deallocate`. Pour Belem $1M → `full_via_force_deallocate` (pénalité 0, gas simulé) | Test live : sur Belem, le multicall simulé est en status 1 ; `immediate_usd ≥ 0,999·V` ; pénalité lue on-chain |
| F2 | **P0** | Côté sortie à base unique : si l'action est partielle, EL, carry et exécution sont **tous** multipliés par $w$ | Test unitaire : pour w = 0,4, `exit_side == exec_w + carry·w` et `avoided == EL·w` ; aucun terme total dans une action partielle |
| F3 | P1 | Comparateur d'actions avec score = $EL_{\text{résiduel}} + \text{exec} + \text{pénalité} + \text{carry abandonné}$ ; REVIEW si les bandes des 2 meilleures actions se chevauchent | Tests : HOLD gagne si EL ≪ carry ; FULL gagne si EL ≫ carry ; REVIEW si chevauchement |
| F4 | P1 | Lecture de `rateAtTarget` + projection WAIT | Test : u = 1, rT 2,52 % → 10,09 % ; doublement en 5,06 j ±0,01 |
| F5 | P1 | Déclencheurs dérivés des données live | Test : seuils −9,1 % / −24,8 % recalculés à partir du LTV et du LLTV |
| F6 | P2 | Externalité affichée | Test : u après sortie = 98,9 % ±0,2 pp sur le snapshot figé |

Les tests existants (Phase 0.5 / Phase 1, V01–V26) doivent rester verts. Le verdict Phase 0.5 ne doit pas changer.
