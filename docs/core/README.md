# Core Risk Engine

The core answers the challenge question: **what dependencies support a position, what loss could their failure cause and should we stay or exit?** It forms the path `position → dependencies → exposure → shock → impact → STAY/EXIT`.

| Folder | Responsibility | Current status |
| --- | --- | --- |
| [Dependency Graph](dependency-graph/README.md) | Discover and represent direct and indirect dependencies. | Code present; real end-to-end case to be verified. |
| [Dependency Exposure %](dependency-exposure/README.md) | Measure the portion of the portfolio exposed to each dependency. | Calculations present; denominator and provenance to be verified. |
| [Impact Estimation](impact-estimation/README.md) | Propagate a shock and estimate the financial loss. | Simulation present; hypotheses and results to be validated. |
| [STAY / EXIT](stay-exit/README.md) | Compare potential loss and exit cost. | Decision logic and Pendle exit quotes exist; a labeled approximation is used when a quote is unavailable. |

The [Official PDF](BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf) is the source of truth. The [summary](belem.md) and [audit procedure](spec_compliance.md) help to read and verify the requirements without turning the examples in the PDF into obligations.

**Expected validation:** Run a traceable real-data case, record sources and freshness, then follow the same data from position to recommendation. The API can return `mock-fallback` and the frontend includes samples; these demo modes do not prove real-data operation.
