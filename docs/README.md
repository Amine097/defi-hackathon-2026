# FAULTLINE Documentation

The documentation is organized by responsibility: **core** for the Belem risk engine and requirements; **features** for modules added to it. Each capability has its own folder. The [frontend blueprint](design/frontend.md) covers the shared interface.

| Area | Content | Product priority |
| --- | --- | --- |
| [Core Risk Engine](core/README.md) | [Dependency Graph](core/dependency-graph/README.md) · [Dependency Exposure %](core/dependency-exposure/README.md) · [Impact Estimation](core/impact-estimation/README.md) · [STAY / EXIT](core/stay-exit/README.md) | P0 — foundation |
| [Breaking Point](features/breaking-point/README.md) | Minimal shock triggering liquidation | P0 — additional feature |
| [Threat Intelligence](features/README.md#p1--threat-intelligence) | Leverage Hunter · Whale Impact · Chain of Blame | P1 |
| [Action Layer](features/README.md#p2--action-layer) | Exit Feasibility · Telegram Ping · Reaction Window | P2 |

The [Official Belem PDF](core/BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf) takes precedence over its [summary](core/belem.md). The [audit procedure](core/spec_compliance.md) shows how to verify the core; it is not a completed audit report. [PLAN.md](../PLAN.md) preserves the historical context, but its progress reports may be dated.

**Phase 1 — Vault Risk Analyzer** (`/vault.html`, `/api/vault`): [spec](core/BELEM_PHASE_1_VAULT_RISK_ANALYZER.md) · [validation](core/BELEM_PHASE1_VALIDATION.md) · [progress](core/BELEM_PHASE1_PROGRESS.md) · [evidence](../audit/BELEM_PHASE1_EVIDENCE.json).

**Phase 2 — Autonomous Countermove** (`/countermove.html`, `/api/countermove`, `contracts/`, local fork only): [reference spec](FAULTLINE_Countermove_v3_Autonomous_Crisis_Response.md) · [implementation report](FAULTLINE_PHASE2_IMPLEMENTATION_REPORT.md) · [security report](FAULTLINE_PHASE2_SECURITY_REPORT.md) · [demo guide](FAULTLINE_PHASE2_DEMO_GUIDE.md) · [progress](FAULTLINE_PHASE2_PROGRESS.md) · [evidence](../audit/FAULTLINE_PHASE2_EVIDENCE.json). Also contains the P0 fixes of the Phase 1 vault exit model (forceDeallocate route, single economic basis).

**Backend, deployment and frontend:** [API contracts](backend/API_CONTRACTS.md) · [figure traceability ($761 / $216,597 / $192,784)](backend/FIGURE_TRACEABILITY.md) · [known gaps](backend/BACKEND_GAPS.md) · [Railway keeper](backend/RAILWAY_KEEPER_DEPLOYMENT.md) · [frontend](frontend/README.md) · [jury demo script](frontend/FINAL_JURY_DEMO.md). **Repository audit:** [GitHub cleanup](audit/GITHUB_CLEANUP.md) · [questions for the Belem CTO](audit/QUESTIONS_FOR_BELEM_CTO.md). `reference-context/` is a historical context pack, not a description of the current code.

**Statuses:** “implemented” means code exists; it does not establish correctness or real-data operation. “Specified” means the behavior is documented but no implementation has been identified. The P0/P1/P2 ranking comes from the team roadmap (image from October 10, 2026), not the official PDF: Breaking Point is a product P0, not an explicit challenge requirement.
