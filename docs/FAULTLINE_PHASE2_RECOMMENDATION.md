# FAULTLINE — Recommandation Phase 2 : « Countermove »

> Réponse produit au jury : « est-ce qu'il y a mieux que sortir ? », « comment sortir / mitiger / combien on perd », « être spécifique (prendre un protocole) ».
> Base factuelle : `FAULTLINE_JURY_FEEDBACK_DEEP_RESEARCH.md` et `FAULTLINE_COUNTERMOVE_TECHNICAL_AUDIT.md`.

---

## 1. Décision : Option B, Morpho **Vault** Countermove (côté déposant)

| Critère | A — Countermove emprunteur Morpho | **B — Countermove déposant Vault Morpho** |
|---|---|---|
| Utilisateur réel de Belem | Non : Belem est déposant ; le curateur est RockawayX | **Oui** |
| Spécificité protocole (J5) | Morpho Blue | Morpho Vault V2 + Blue + IRM |
| Concurrence | DeFi Saver, Summer.fi, pre-liquidation Morpho existent déjà | **Aucun outil déposant ne compare les actions** ; DeFiLlama simule la sortie, sans décision |
| « Mieux que sortir » chiffrable | Repay / add collateral (déjà connu) | HOLD + déclencheurs, PARTIAL(w), WAIT & EARN, route `forceDeallocate` |
| « Comment sortir » | Deleverage atomique (Bundles) | **Route `forceDeallocate` prouvée live sur Belem** (pénalité 0, 570k gas) |
| Réutilisation Phase 1 | Partielle (`leverage.py`) | Forte (`vault_model`, `uncertainty`, `vault_reader`) |
| Risque de livraison | Moyen (quotes de swap) | Faible à moyen (simulation `eth_call` déjà maîtrisée) |

**Choix : B.** Les données emprunteur (LTV de `0xa122…`, seuils −9,1 % / −24,8 %) restent des **entrées de risque** pour le déposant. Ce ne sont pas des recommandations qui lui sont adressées.

---

## 2. Moteur de décision

### 2.1 Ensemble d'actions (déposant uniquement)

| Action | Définition | Faisabilité vérifiée par |
|---|---|---|
| `HOLD` | Rester, sans condition | — |
| `HOLD_WITH_TRIGGERS` | Rester, avec des seuils de sortie chiffrés et surveillés | Données live |
| `PARTIAL(w)` | Retirer une fraction $w$ | Simulation $w·V$ |
| `FULL_ORDINARY` | `redeem` simple (idle + liquidityAdapter) | `eth_call` |
| `FULL_FORCE` | `multicall([forceDeallocate…], redeem)` | `eth_call` + `eth_estimateGas` |
| `WAIT_AND_EARN` | Rester pendant une illiquidité, avec projection IRM | Lecture de `rateAtTarget` |

### 2.2 Fonction objectif (horizon $H$, même base USD)

Pour chaque action $a$ de fraction retirée $w_a$ :

$$\text{Coût}(a) = \underbrace{EL_H\,(1-w_a)}_{\text{risque gardé}} + \underbrace{\text{exec}_a + \text{pénalité}_a}_{\text{simulés}} + \underbrace{\text{carry}_H\,w_a}_{\text{rendement abandonné}}$$

- $EL_H$ vient du moteur existant (graphe et MC), sur $V$.
- $\text{exec}_a$ et $\text{pénalité}_a$ sont **simulés pour la taille exacte $w_a V$**. Jamais un coût partiel avec un $w$ total (correctif F2).
- $\text{carry}_H = V \cdot \text{APY net} \cdot H/365$ (existant), multiplié par $w_a$.

**Contraintes :**

1. **Exécutabilité** : $w_a V \le$ capacité simulée de la route.
2. **Pénalité** : ≤ pénalité lue on-chain (≤ 2 % par construction).
3. **Budget de stress (mandat)** : $\text{PerteStress}_s \cdot (1-w) \le L$ pour le scénario $s$ choisi.

**Propriété honnête.** Le coût est **linéaire** en $w$. Sans contrainte, l'optimum est donc toujours un coin (HOLD ou FULL). Une sortie partielle n'est justifiée que par une contrainte :
- capacité limitée ;
- ou budget de stress du mandat, qui donne $w^* = \max\big(0,\,1 - L/\text{PerteStress}_s\big)$.

Le produit doit le dire, plutôt que d'inventer une concavité.

### 2.3 Signal « cannot discriminate »

Il réutilise `uncertainty.robust_signal`. On compare les **bandes** de coût des deux meilleures actions. S'il y a chevauchement, on renvoie **REVIEW**, avec :
- le multiplicateur de risque qui inverserait le choix (`breakeven_risk_multiplier`, déjà calculé) ;
- la donnée qui trancherait (par ex. la NAV mGLOeuro, la politique de pénalité du curateur) ;
- l'action par défaut prudente (`HOLD_WITH_TRIGGERS`) et ses déclencheurs.

### 2.4 Déclencheurs (dérivés live, jamais fixés en dur)

| Déclencheur | Valeur Belem (bloc 26 163 748) | Délai d'avertissement |
|---|---|---|
| NAV / oracle mGLOeuro : début de liquidation | −9,1 % | Saut (NAV mensuelle) : **aucun délai garanti** |
| NAV / oracle mGLOeuro : début de bad debt | −24,8 % | idem |
| LTV de l'emprunteur dominant | 0,700 → alerte à ≥ 0,74 (LLTV 0,77) | Progressif (intérêts) |
| Utilisation mGLOeuro | 91 % → alerte ≥ 98 % | Progressif |
| Liquidité force-deallocatable < $V$ | $750k aujourd'hui (WBTC + cbBTC + wstETH) | Progressif |
| `submit(setForceDeallocatePenalty)` ou hausse de cap en attente | Aucune | **Timelock = délai garanti** |

---

## 3. Démo sur cas réel : Belem RWA EURCV, $1M, 30 jours

Chaque chiffre est étiqueté **LIVE** (on-chain / API au bloc), **SIMULÉ** (`eth_call` / `eth_simulateV1`), ou **HYPOTHÈSE** (entrée utilisateur ou prior).

1. **Découvrir (LIVE).** Vault V2 → adapter unique → 6 marchés. 85,8 % en mGLOeuro, un emprunteur de 3,68M EURCV à LTV 0,70, oracle NAV Fasanara/Midas. Curateur RockawayX.
2. **Combien on perd (LIVE + modèle).**
   - EL sur 30 j : $632 (bande $113–$3 233).
   - Stress : NAV −40 % → $157k ; défaillance du marché → $600k.
3. **Comment sortir (SIMULÉ).**
   - Aujourd'hui, le produit affiche « $405k now / $595k blocked ».
   - Countermove montre : `redeem` simple → revert ; `multicall(forceDeallocate WBTC + cbBTC, redeem)` → **succès, $1M, pénalité 0, 570k gas (~quelques $)**.
4. **Mieux que sortir ? (calcul).**

   | Action | Coût central sur 30 j |
   |---|---|
   | HOLD | EL $632 |
   | FULL_FORCE | exec ≈ $0 + carry abandonné $2 149 |

   Les bandes se chevauchent : **REVIEW, lean HOLD**. L'action par défaut est `HOLD_WITH_TRIGGERS`.
5. **Mitiger (HYPOTHÈSE de mandat).** Avec un budget de stress de $50k sous NAV −40 % : $w^* = 1 - 50/157 = 68\,\%$. On retire $680k par la route force, le reste est conservé sous déclencheurs.
6. **Externalité (calcul).** Une sortie totale porte l'utilisation de mGLOeuro à 98,9 %. Le vault restant est à 97,4 % en mGLOeuro. **Sortir tôt transfère le risque** ; le message pour Belem est d'agir **avant** la file d'attente.
7. **WAIT & EARN (LIVE + projection).** Si la liquidité se tarit (u = 100 %), l'APY monte à 10,1 %, puis ~20 % à J+5. C'est l'option de rester rémunéré. Elle n'est **pas une garantie** de retour de liquidité (cas Stream, nov. 2025).

Ce qui disparaît de la présentation (J3/J4) :
- Chain of Blame ;
- les modules séparés Exit Feasibility, Reaction Window et Telegram Ping.

Leur substance utile (faisabilité, déclencheurs) est **intégrée** dans la décision.

---

## 4. Plan Phase 2 (ordre strict)

| Étape | Livrable | Tests | Critère d'acceptation |
|---|---|---|---|
| P2-01 | Route `forceDeallocate` (F1) : construction du multicall, `eth_call` / `estimateGas`, pénalité, gas | Unitaire (encodage `MarketParams`) ; live Belem | Belem $1M : `feasibility = full_via_force_deallocate`, status ok, pénalité = valeur on-chain |
| P2-02 | Base unique partielle / totale (F2) | Unitaires sur w ∈ {0 ; 0,4 ; 1} | Aucun terme total dans une action partielle ; `test_v14` vert |
| P2-03 | Comparateur d'actions + REVIEW (F3) | STAY / EXIT / REVIEW synthétiques ; non-régression V01–V26 | Verdicts Phase 0.5 inchangés |
| P2-04 | Projection IRM (F4) | Formules (×4 à u = 1 ; doublement 5,06 j) | Écart < 0,01 % vs formule doc Morpho |
| P2-05 | Déclencheurs live (F5) + budget de stress (entrée utilisateur) | Seuils recalculés ; $w^*$ | Belem : −9,1 % / −24,8 % ±0,1 pp |
| P2-06 | Externalité (F6) | Snapshot figé | u post-sortie 98,9 % ±0,2 pp |
| P2-07 | API `/api/vault` + écran X-Ray « Countermove » (tableau d'actions, étiquettes LIVE / SIMULÉ / HYPOTHÈSE) | Node + E2E | Rendu cohérent avec le JSON ; aucun chiffre non étiqueté |
| P2-08 | Validation sur 2 autres vaults Morpho réels (dont un MetaMorpho V1) | Live | La route force est absente en V1 ; dégradation propre |

**Hors périmètre Phase 2 :** Whale Tracking, Breaking Point avancé, Solana, Chain of Blame, Telegram.

**Risques :**
- RPC publics instables (1rpc OK ; drpc 429).
- `eth_simulateV1` n'est pas universel : `eth_call` + `estimateGas` en repli.
- La pénalité et la liquidité peuvent changer entre la simulation et l'exécution : afficher le bloc et la fraîcheur.
