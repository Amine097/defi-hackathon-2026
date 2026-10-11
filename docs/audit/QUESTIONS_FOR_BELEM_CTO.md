# Questions for the Belem Capital CTO

Five questions, ranked by expected effect on the score (discovery 30%, defensible impact 30%, decision usefulness 25%, real data 15%).
Every number below comes from committed recordings (`public/data/recorded/*.json`, Ethereum mainnet blocks 26,166,578–26,166,582,
recorded 2026-10-11). The notionals are **hypothetical**: $1M unless stated. "Our arithmetic" means a hand calculation from recorded
values, not a model output.

## Already resolved, so not a question for the CTO

**$761, $216,597 and $192,784 are comparable and consistent.** All three come from the same recording (`analyze-pt.json`: $1M PT-reUSD-10DEC2026,
Morpho USDC market, **no debt**, 30 days, block 26,166,580). They measure different things:

- **$761**: probability-weighted expected loss (band $39–$19,664).
- **$216,597**: conditional loss if the fiat base behind reUSD loses 30%. The 30% is an assumption, × transmission 0.72.
- **$192,784**: conditional loss if Pendle or Morpho contracts are exploited, at the calibrated 19.2% severity.

The earlier **"EXIT $192k"** and **"EXIT $154k"** came from a bug in the old browser-side recalculation, which ignored that the AMM and
Morpho market cannot cause principal loss without debt. That code was removed. See `docs/backend/FIGURE_TRACEABILITY.md`. Note that
`$154,504` also appears legitimately, as the *Oracle failure* conditional loss of the **borrower** recording.

---

## 1. Reinvestment rate and base currency (immediate clarification needed)

**Question.** When your desk exits a position, what rate should forgone yield be measured against? Options include 0%, a T-bill/€STR
rate, or the next-best venue in the same mandate. For the Belem RWA EURCV vault, do you measure the decision in EUR or USD?

**What we know.**
- **Belem RWA EURCV** Morpho Vault V2 `0xD6d4…48Ec`, $1M hypothetical, 30 days, block 26,166,578:
  - Net APY 2.566%. Carry is computed with a **0% reference rate** (hard-coded in `vault_model.py`), giving $2,109.
  - Execution cost: $0.11 through a simulated `forceDeallocate` with a $0 penalty.
  - Expected loss: $656 (band $112–$3,519).
  - Verdict: REVIEW, lean STAY (×3.22).
  - An indicative EURCV→USDC conversion would cost **$11,852** (KyberSwap quote). It is shown but not counted.
- **PT-reUSD:** the reference is the Morpho USDC supply APY, 6.66%. PT implied APY 11.81% → carry $4,230.
- `core/book.py` uses a single reference rate for all ten pockets (`BACKEND_GAPS.md` C3).

**Uncertainty.** Our arithmetic says the vault's lean flips to **EXIT** if the reference rate reaches about **1.77%**. Above about
**2.48%**, the exit side falls below the low end of the loss band: a firm EXIT under the current rule. In USD terms, the conversion
cost would instead dominate and push strongly toward STAY. The PT verdict is insensitive to the reference rate, because the $1,217
execution cost alone exceeds the $761 expected loss.

**Why it matters.** This assumption decides the verdict on Belem's own vault (decision usefulness 25%). A Belem juror could spot it
immediately.

**What depends on it.** The vault reference rate (0% → Belem's rate), whether the FX conversion cost is counted, per-pocket references
in the book, and the vault slide.

## 2. The reference structure behind the brief's worked example (immediate clarification needed)

**Question.** In the PDF's Pendle PT example, the incident hits the **oracle** layer. Do you assume the PT is posted as collateral **with
debt** (a PT loop), and at what LTV? Which one or two structures you actually run should we demonstrate on? Is the RWA EURCV vault
representative?

**What we know.**
- Our hero recording holds the PT **without debt**. There, an oracle failure has **no effect**: $761, STAY. Only exit cost changes.
- The borrower recording is the largest live borrower in the same market (`0xAa34…5Dd5`):
  - Collateral $12.66M, debt $11.06M, LTV 87.4% against an LLTV of 91.5%.
  - 4.5% from liquidation.
  - Oracle failure: **$154,504, EXIT**, on a $1M analysed slice.
- Countermove S5 replays an oracle incident on PT collateral with debt, on a fork.
- The PDF offers "the portfolio structures we actually run as reference cases" and also mentions vaults routing into a **perp venue**. That
  dependency type is not covered.

**Uncertainty.** We don't know whether the brief intends a levered PT, what a realistic Belem size and LTV are, or whether PT-reUSD and
EURCV fit Belem's market-neutral mandates.

**Why it matters.** If the intended case is levered, leading with the no-debt PT shows "the brief's incident does nothing"
(discovery 30%, real data 15%).

**What depends on it.** Which recording leads the demo, which notional and LTV we use, and whether to present principal-loss and
liquidation-loss channels side by side.

## 3. Failure probabilities, severities and correlation

**Question.** Does your pre-selection scorecard assign incident probabilities and loss severities per dependency class? If so, what ranges
would you consider defensible for (a) a blue-chip smart-contract exploit, (b) the off-chain backing of an RWA/synthetic stablecoin, and
(c) the settlement chain? And do you model correlated failures explicitly, or reason from conditional stress scenarios?

**What we know.**
- Exploit probability uses the DefiLlama cohort base rate (0.020–0.044% per 30 days). Exploit severity is **calibrated** at 19.2%
  (23 incidents, 95% CI 9.4–31.5%).
- The other parameters are **structural assumptions** (`priors.py`, comment "tune with Belem's mentors"): chain LGF 30%, base-asset
  severity 30%, expert transmission weights ±25%.
- Correlation is **bounded, not estimated** (independence → union bound).
- The two largest stress rows are assumption-driven: Ethereum $300,446 and base asset $216,597.
- The largest expected-loss contributor is USDC depeg history ($434 of $761). This is counter-intuitive for a reUSD PT.

**Uncertainty.** We can't tell whether a professional risk desk trusts the expected-loss framing at all, or which assumed severities it
would challenge.

**Why it matters.** Defensible impact is 30% of the score. It determines whether we lead with expected loss plus the breakeven multiplier,
or with conditional stress plus probability thresholds.

**What depends on it.** Parameter replacement (only with Belem's figures, documented as such), slide framing, and how loudly we caveat the
$216k and $300k rows.

## 4. Exit cost and timing during a real incident

**Question.** During a real incident, how much time does your desk have, and what unwind cost do you observe? Is the brief's **11%
slippage** a realistic stressed cost? Should a recommendation use the calm live quote, a stressed cost, or both? Would you act on
**hold to maturity** or a **partial exit**?

**What we know.**
- The live Pendle quote is $1,217 (0.12%) on $1M at a calm block. Our *Liquidity crisis* scenario only doubles it, to $2,434.
- The model assumes you sell **before** the shock reaches the PT price.
- Over the 60 days to maturity, the lean is HOLD TO MATURITY (low confidence).
- The vault's full exit relies on `forceDeallocate` liquidity that is "first come, first served".
- In the brief's book example, 11% of a 10% pocket equals 1.1% of the book. Our recorded book shows 0.012% of the book.

**Uncertainty.** Our exit costs may be about 90× more optimistic than Belem's own example, and the timing assumption is untested.

**Why it matters.** It affects decision usefulness (25%) and the credibility of every STAY verdict.

**What depends on it.** The default exit-cost basis, the stressed-exit scenario, and whether HOLD TO MATURITY and partial exits are shown
prominently.

## 5. Which automated protective actions Belem would actually accept

**Question.** Belem reports zero liquidations and runs market-neutral mandates. Do any mandates hold borrow or loop positions where a
**pre-authorised keeper** would be acceptable, for example repaying or topping up collateral from a pre-funded, narrowly permissioned
contract? Or would fund rules and custody or multisig policy only allow alert-and-approve, or an automated vault withdrawal?

**What we know.**
- `RescueVault` plus the keeper ran S1–S5 on a **local Anvil fork**. The contract is unaudited and nothing runs on mainnet.
- The Railway keeper protects a test position only.
- A mainnet policy can be drafted but has `keeper_executable = false`.

**Uncertainty.** We don't know whether automatic repay or top-up matches any real Belem workflow, or what blocks it (custodian policies,
governance, pre-funding cost).

**Why it matters.** It decides whether Countermove is pitched as core decision value or as an optional extension, and keeps the claims
honest.

**What depends on it.** The emphasis on Countermove in the demo, whether to reframe it as automated EXIT for vaults versus borrower
protection, and the wording of "controlled fork execution versus real deployment".

---

## Not asked (we can resolve these ourselves)

- Linear scaling of the loss fraction to the real borrower's size (`BACKEND_GAPS.md` C4).
- Using finalized checkpoints instead of fixed confirmations.
- Why *Underlying depeg* ($270,503) differs from the base-asset stress row ($216,597). They shock different nodes (reUSD versus its fiat
  base, transmission 0.72).
