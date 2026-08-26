# Bigfish Architecture

## 1. Purpose

Bigfish is a private, single-user, long-term investment research operating system.

It is not intended to be merely a stock-analysis prompt, a financial-data warehouse, or a server-side multi-agent platform. Its purpose is to turn years of investment research into a durable, testable, revisable body of private investment knowledge and methodology.

The target system is:

```text
Bigfish
=
Investment Philosophy
+ Research Workflow
+ Research Router
+ Evidence System
+ Tool Orchestration
+ Valuation Engine
+ Investment Memory
+ Thesis / Assumption / Prediction Ledgers
+ Decision Journal
+ Calibration System
+ Learning System
```

The core design principle is:

> **ChatGPT handles the world; Bigfish Skill handles the investment methodology; Cloud Run exposes lightweight deterministic tools and memory APIs; Neon PostgreSQL preserves long-term private knowledge; Codex periodically upgrades the Skill from accumulated experience.**

This architecture reflects the current design. Where older Bigfish designs conflict with this document, this document takes precedence.

---

## 2. System Responsibility Boundaries

```text
                     ChatGPT
                        |
                        | public research / reasoning / synthesis
                        v
                  Bigfish Skill
                        |
              Research Router
                        |
              Research Modules
          +-------------+-------------+
          |                           |
          v                           v
  ChatGPT native tools          Bigfish Tools
  - Web research                - Memory tools
  - Company IR                  - Calculation tools
  - SEC / HKEX                  - Optional data tools
  - News / public data               |
  - Source cross-checking            v
                                  Cloud Run
                            min instances = 0
                            max instances = 1
                                      |
                                      v
                              Neon PostgreSQL
                         +------------+------------+
                         |                         |
                  Investment Memory           Skill Learning
```

### ChatGPT

ChatGPT is the primary intelligence and interaction layer.

It should:

- understand the user's natural-language investment question;
- retrieve current public information;
- search company IR, SEC, HKEX, exchange filings, regulatory sources, reputable media, and other relevant public sources;
- reason about business quality, competitive advantage, financials, valuation, risk, and uncertainty;
- synthesize evidence into conclusions;
- generate investment analyses and reports;
- use Bigfish Tools when persistent memory or deterministic computation is needed.

ChatGPT should not depend on the Bigfish backend for routine public-data retrieval.

### Bigfish Skill

The Skill defines **how to research**.

It should encode:

- investment philosophy;
- Research Router logic;
- research workflow;
- evidence hierarchy;
- dynamic research planning;
- rules for facts, claims, assumptions, estimates, and opinions;
- valuation methodology;
- Devil's Advocate / disconfirmation workflow;
- memory rules;
- prediction and decision-recording rules;
- learning and self-improvement rules.

The Skill should not become a database of company facts.

### Cloud Run

Cloud Run is a thin Tool & Memory Server.

It should:

- authenticate Bigfish Tool calls;
- query and update Neon;
- run deterministic calculations;
- optionally expose a small number of reliable data utilities;
- remain stateless.

It should **not** normally:

- run the main investment Agent;
- maintain a server-side multi-agent orchestration system;
- call GPT/OpenAI for routine research;
- crawl or warehouse public financial information.

Recommended initial configuration:

```text
min instances = 0
max instances = 1
```

The local Cloud Run filesystem is ephemeral and must never contain the only copy of important memory.

### Neon PostgreSQL

Neon is the persistent memory layer.

It stores:

- investment research history;
- thesis versions;
- assumptions;
- predictions;
- decision records;
- valuation history;
- critical unknowns;
- watch variables;
- research updates;
- mistakes and reviews;
- calibration records;
- Skill-improvement candidates.

It should not be used as a warehouse of publicly re-downloadable reports, PDFs, filings, or raw market data.

### Codex

Codex is the development and maintenance environment.

It should:

- modify `SKILL.md` and Tool Server code;
- maintain this architecture document;
- run tests and evals;
- periodically review Skill-improvement records;
- propose Skill changes;
- show diffs;
- publish only after explicit user approval.

---

## 3. Bigfish Maturity Model

Bigfish should evolve through three conceptual levels.

### Level 1 — Prompt Skill

```text
fixed investment framework
-> company analysis
```

### Level 2 — Workflow Skill

```text
question
-> search
-> evidence
-> calculations
-> validation
-> output
```

### Level 3 — Agent System Skill

```text
understand objective
-> create research plan
-> identify missing information
-> continue investigating
-> seek disconfirming evidence
-> value the company
-> form investment judgment
-> save long-term memory
-> later verify predictions
-> learn from errors
```

The long-term target is Level 3, but the implementation should remain lightweight: the Agent intelligence lives mainly in ChatGPT + Bigfish Skill, not in a large server-side Agent cluster.

---

## 4. Research Router

Bigfish must not launch full research for every question.

The first step is to identify the user's actual intent and select the cheapest sufficient workflow.

```text
Simple investment question
-> Direct Answer

Financial-number question
-> Primary-source retrieval + Calculation Tool

Valuation question
-> Valuation Engine

Focused single-topic question
-> Focused Research

Full company analysis
-> Full Research Workflow

Major investment decision
-> Full Research
   + Valuation
   + Devil's Advocate
   + Scenario Analysis
   + Decision Journal if user confirms an actual decision
```

Example:

```text
"What EPS growth does META need to achieve my target return?"
-> valuation module only
```

versus:

```text
"Fully analyze META and judge whether it is worth buying."
-> full research workflow
```

This routing system is also the main research-cost control mechanism.

---

## 5. Dynamic Research Planning

Bigfish should not mechanically apply the same checklist to every company.

For each meaningful research task it should first ask:

> **What actually determines this company's long-term value?**

Then construct a dynamic Research Tree around the decisive variables.

Example for AppLovin:

```text
APP
├── Does AXON have a real data flywheel?
├── Where does advertiser conversion data come from?
├── How do iOS privacy restrictions affect signal quality?
├── Can e-commerce ads reproduce the gaming advantage?
├── Is ROAS superiority durable?
├── Can Google / Meta replicate the system?
└── How much growth is already embedded in valuation?
```

The research should focus on value-driving questions rather than a generic sequence such as:

```text
revenue
profit
PE
risk
```

---

## 6. Evidence System

Bigfish must explicitly rank evidence quality.

Default hierarchy:

```text
SEC / regulatory filing
>
company financial statements / official IR disclosure
>
company earnings call
>
regulator / exchange
>
high-quality news media
>
reliable third-party database
>
industry material
>
forums / social media
```

Material valuation inputs should prefer primary sources whenever practical.

Bigfish must distinguish:

```text
FACT
MANAGEMENT CLAIM
ESTIMATE
ASSUMPTION
OPINION
```

Example:

```text
"Management says Rubin can reduce token cost by 10x"
```

must not silently become:

```text
"Real customer token cost has already fallen 10x"
```

Third-party financial APIs such as Yahoo/FMP may be used as optional convenience sources, but they are not authoritative dependencies. If they disagree with primary-source data, primary sources take precedence.

---

## 7. Unknown Awareness

Bigfish must be allowed to conclude:

> **I don't know.**

A material unresolved variable should be recorded as a formal research output rather than filled with an invented number.

Example:

```text
Critical Unknown:
Long-term true ROAS advantage of AXON e-commerce ads

Impact:
Very High

Evidence:
Insufficient

Confidence:
Low
```

The system can then decide whether to:

- continue searching;
- find customer evidence;
- look for earnings-call commentary;
- find industry evidence;
- move to scenario analysis.

Unknowns are part of the research record and should be reviewable later.

---

## 8. Calculation Layer

Complex calculations should not rely on LLM mental arithmetic.

Bigfish should ask:

```text
What should be calculated?
```

and deterministic tools should answer:

```text
Calculate it precisely.
```

Important calculations include:

- TTM derivation;
- CAGR;
- FCF;
- ROIC;
- reverse valuation;
- required EPS growth;
- terminal PE analysis;
- expected return;
- scenario analysis;
- period comparison;
- normalization adjustments.

Possible implementations:

```text
reverse_valuation.py
ttm_financials.py
fcf_normalizer.py
roic.py
scenario_analysis.py
return_calculator.py
```

The Tool Server should expose these as deterministic interfaces rather than requiring ChatGPT to execute arithmetic manually.

---

## 9. Valuation Must Be Linked to Thesis

Valuation cannot be an isolated final step that arbitrarily assigns a multiple.

The reasoning chain should be traceable:

```text
Business Thesis
-> Revenue
-> Margin
-> EPS / FCF
-> Terminal Multiple
-> Expected Return
```

Key valuation assumptions should be traceable to evidence and assumptions in the research record.

Bigfish must distinguish accounting earnings from owner economics. In particular:

```text
EPS Growth != FCF Growth
```

If a company enters a major CapEx cycle, Bigfish should explicitly model the possibility that accounting EPS grows faster than free cash flow and that PE may understate true capital-intensity pressure.

---

## 10. Devil's Advocate / Kill the Thesis

A full research workflow should not immediately end with BUY / HOLD / SELL.

Before the final investment judgment, Bigfish should ask:

> **If this investment eventually fails, what are we most likely getting wrong today?**

Then actively seek evidence capable of breaking the thesis.

For example, for Google:

```text
Search economics weakened by AI
Gemini monetization disappoints
AI CapEx produces poor ROIC
TPU advantage narrows
Cloud growth slows
regulatory pressure destroys economics
```

The goal is not to list generic risks; the goal is to identify disconfirming evidence that could materially invalidate the investment thesis.

---

## 11. Investment Memory Model

Bigfish should preserve the evolution of thought rather than overwrite history.

### 11.1 Thesis Ledger

Each company should maintain versioned thesis records.

Suggested fields:

```text
ticker
created_at
supersedes_thesis_id
thesis
supporting_evidence
contrary_evidence
confidence
status
```

Conceptually:

```text
Thesis(t0)
-> Thesis(t1)
-> Thesis(t2)
```

This enables later review of what was actually believed at the time and reduces hindsight bias.

### 11.2 Assumption Ledger

Key assumptions should be explicit, particularly those with high impact.

Example:

```text
META

Assumption:
AI continues improving advertising conversion
Confidence: High
Impact: Very High

Assumption:
AI CapEx eventually earns acceptable ROIC
Confidence: Medium-Low
Impact: Very High

Assumption:
Advertising revenue remains double-digit
Confidence: Medium-High
Impact: Very High
```

Future updates should focus on:

- which assumptions were confirmed;
- which were falsified;
- which changed in confidence;
- which new assumptions became important.

### 11.3 Prediction Ledger

Important research should produce falsifiable predictions where appropriate.

Suggested fields:

```text
prediction
prediction_date
expected_verification_date
confidence
actual_result
outcome
error_reason
reviewed_at
```

Example:

```text
Ticker: META
Prediction Date: 2026-08-24
Prediction: 2027 CapEx > $150B
Confidence: 70%
Expected Verification Date: 2027
```

Later:

```text
Prediction
-> Actual Result
-> Correct / Wrong / Partially Correct
-> Error Analysis
```

### 11.4 Decision Journal

Real investment decisions should be distinct from research opinions.

Suggested fields:

```text
ticker
decision_date
decision
price
position_size
target_return
base_expected_return
bear_expected_return
bull_expected_return
core_thesis
critical_assumptions
major_risks
buy_more_conditions
sell_conditions
confidence
```

The system must not infer a transaction merely because the user discusses a stock positively or negatively.

Research records may be saved automatically when useful.

Actual actions such as:

```text
BUY
SELL
ADD
REDUCE
POSITION SIZE
```

must only be saved as real decisions/transactions after explicit user confirmation or an unambiguous user statement that the transaction occurred.

### 11.5 Critical Unknowns

Store high-impact unresolved questions with:

```text
ticker
description
impact
evidence_status
confidence
created_at
resolved_at
resolution
```

### 11.6 Watch Variables

Each company should maintain a small set of variables that truly determine the thesis.

Example for META:

```text
Advertising Growth
AI CapEx
FCF Margin
AI Monetization
```

These become the priority checks in future updates.

---

## 12. Incremental Research

Bigfish should not regenerate the full company thesis from zero each quarter.

Initial research creates a baseline:

```text
Company
├── Thesis
├── Moat
├── Financials
├── Valuation
├── Assumptions
├── Predictions
├── Risks
├── Critical Unknowns
└── Watch Variables
```

Subsequent updates should run:

```text
Old Research
+
New Information
->
What Changed?
```

The update should answer:

- which facts changed;
- which assumptions changed;
- which predictions were verified;
- which predictions failed;
- whether the thesis changed;
- whether valuation changed;
- how expected return changed.

The purpose of memory is to make future research incremental, not repetitive.

---

## 13. Calibration System

Prediction history should eventually be used to measure Bigfish's judgment quality by domain.

Examples:

```text
technology-trend prediction accuracy
revenue-growth prediction accuracy
margin prediction accuracy
terminal-multiple prediction accuracy
```

The goal is not to claim perfect prediction ability. The goal is to learn:

> **Where are we systematically overconfident or weak?**

Calibration should influence future confidence levels and Skill-improvement proposals.

---

## 14. Outcome vs Process

Investment outcome and decision quality must be evaluated separately.

Possible combinations include:

```text
Outcome Good / Process Good
Outcome Good / Process Poor
Outcome Poor / Process Good
Outcome Poor / Process Poor
```

A stock rising 200% does not prove the original thesis was correct. Likewise, a losing investment can still have been based on a sound probabilistic process.

The long-term objective is to improve decision quality, not merely record realized returns.

---

## 15. Research Budget Awareness

Bigfish should allocate research effort according to decision importance.

```text
Simple Question
-> Low Cost

Financial Calculation
-> Data + Script

Focused Research
-> Medium Cost

Full Company Research
-> High Cost

Major Investment Decision
-> Full Research
   + Devil's Advocate
   + Scenario Analysis
```

Research depth should be intentional rather than automatic.

---

## 16. Investment Knowledge Graph

Long term, Bigfish should be able to relate companies and investment assumptions across the portfolio.

Example:

```text
GOOGL
META
MSFT
AMZN
   |
   v
Hyperscaler AI CapEx
   |
   v
AI Infrastructure Demand
   |
   v
NVDA
TSMC
AVGO
Memory
```

A change in one shared driver may affect multiple companies differently.

For example:

```text
Hyperscalers raise CapEx
-> may pressure GOOGL / META FCF
-> may increase confidence in NVDA / TSMC demand assumptions
```

The initial implementation does not need a dedicated graph database. Relationships can begin as normal PostgreSQL tables and evolve only if actual usage justifies a graph layer.

---

## 17. Memory Scope and What Not to Store

The database should store **private knowledge that cannot simply be reconstructed by searching the public web again**.

### Store

- theses and thesis history;
- assumptions;
- predictions and reviews;
- valuation judgments;
- investment decisions;
- watch variables;
- critical unknowns;
- mistakes and post-mortems;
- research updates;
- confidence changes;
- calibration records;
- Skill-improvement candidates.

### Do not routinely store

- full annual or quarterly reports;
- SEC/HKEX filing copies;
- PDFs and images;
- news archives;
- complete price histories;
- raw pages;
- large quantities of easily reproducible financial facts.

Public facts should normally be re-retrieved by ChatGPT when needed. What matters is preserving what Bigfish concluded, assumed, predicted, decided, and later learned.

---

## 18. Database Model

The schema should evolve gradually rather than being over-designed up front.

Likely core tables:

```text
companies
research_sessions
theses
assumptions
predictions
decisions
valuations
critical_unknowns
watch_variables
research_updates
prediction_reviews
decision_reviews
skill_improvements
company_relationships
```

`financial_snapshots` may exist only if a specific use case proves valuable; the current architecture does **not** require a financial-data warehouse.

Minimum schema principles:

```text
appendable
queryable
versionable
time-traceable
company-linked
```

Historical records should not be destructively overwritten when preserving the old state is useful.

---

## 19. Tool Layer

The Tool Server should remain deliberately small.

### Memory tools

```text
search_memory(...)
get_company_memory(...)
get_thesis_history(...)
save_thesis(...)
save_assumption(...)
save_prediction(...)
save_decision(...)
save_watch_variable(...)
save_critical_unknown(...)
save_research_update(...)
```

### Review / learning tools

```text
record_prediction_result(...)
save_decision_review(...)
save_skill_feedback(...)
save_improvement_candidate(...)
list_improvement_candidates(...)
mark_improvement_status(...)
```

### Deterministic calculation tools

```text
calculate_cagr(...)
calculate_irr(...)
reverse_valuation(...)
calculate_required_eps_growth(...)
calculate_ttm(...)
calculate_roic(...)
normalize_fcf(...)
scenario_analysis(...)
compare_periods(...)
```

### Optional data tools

Reliable convenience tools may be added later, but they must remain optional:

```text
get_exchange_rate(...)
get_stock_price(...)
get_filing_metadata(...)
```

If an optional data tool is unreliable, the Skill should fall back to ChatGPT's normal public-information retrieval.

---

## 20. Natural-Language User Interface

The user should not interact directly with database forms or tables.

The primary interface remains ChatGPT.

Examples:

```text
$bigfish analyze Google
$bigfish update META
$bigfish I bought Google, position size 5%
```

Flow:

```text
User Conversation
-> Bigfish
-> Structured Extraction
-> Tool Call
-> Neon PostgreSQL
```

The Tool layer exists to serve natural-language workflows, not to force the user to manage database records manually.

---

## 21. Memory Responsibility Split

The system should distinguish between three memory layers.

### ChatGPT Memory

Used for durable user-level preferences and context such as:

- investment style;
- target return;
- research preferences.

### Bigfish Skill

Stores stable investment methodology and workflow rules.

### Neon / Investment Research OS

Stores formal investment history:

- Thesis;
- Assumptions;
- Predictions;
- Decisions;
- Valuations;
- Research Updates;
- Mistakes;
- Calibration;
- Skill Improvements.

The Skill should not become a substitute for the database, and ChatGPT Memory should not become the formal investment ledger.

---

## 22. Learning System

Bigfish should form three loops.

### Research Loop

```text
Question
-> Research
-> Evidence
-> Conclusion
```

### Investment Loop

```text
Conclusion
-> Valuation
-> Decision
-> Outcome
```

### Learning Loop

```text
Prediction
-> Reality
-> Error
-> Review
-> Method Improvement
```

The long-term purpose is continuous improvement of process quality.

---

## 23. Skill Improvement System

Bigfish should learn from research without autonomously rewriting its production Skill.

Store methodological issues in `skill_improvements`.

Suggested fields:

```text
id
created_at
category
problem
evidence
proposed_change
confidence
status
implemented_version
reviewed_at
```

Example:

```text
problem:
Fixed financial APIs repeatedly produced inconsistent or missing data.

proposed_change:
Prioritize primary sources for material investment facts; keep fixed financial APIs auxiliary.

confidence:
high

status:
pending
```

The learning pipeline is:

```text
Experience
-> Reflection
-> Improvement Candidate
-> Evidence Accumulation
-> Codex Review
-> Proposed Rule
-> Tests / Evals
-> Diff
-> User Approval
-> Skill Upgrade
```

Bigfish may automatically detect and save improvement candidates.

Bigfish must not automatically publish changes to its production investment methodology.

---

## 24. Periodic Codex Upgrade Workflow

Skill upgrades should be low-frequency rather than continuous — for example monthly, or when enough high-quality improvement candidates have accumulated.

A dedicated Codex workflow such as:

```text
$bigfish-upgrade
```

should:

1. read `docs/architecture.md`;
2. read the current `SKILL.md`;
3. retrieve pending Skill-improvement records;
4. review relevant historical errors and prediction outcomes;
5. deduplicate proposals;
6. judge whether lessons are generalizable;
7. detect conflicts with existing methodology;
8. propose edits;
9. run tests/evals;
10. show a clear diff and rationale;
11. wait for explicit user approval;
12. publish only after approval;
13. mark adopted improvements with the implemented Skill version.

The user should not need to re-explain Bigfish architecture in each Codex session.

---

## 25. Project Documentation as Source of Truth

ChatGPT and Codex should not be assumed to automatically share complete conversation history.

Therefore this file should live in the Bigfish repository as:

```text
docs/architecture.md
```

It is the persistent source of truth for architecture decisions.

A new Codex session should be able to resume with:

```text
Read docs/architecture.md and continue developing Bigfish according to the current architecture.
```

Major architecture changes should update this document in the same code change.

---

## 26. Development and Production Data Separation

Use separate Neon environments or branches.

```text
Neon Project
|
+-- production
|   +-- real Bigfish investment memory
|
+-- development
    +-- Codex development and automated tests
```

Codex must not run destructive tests against production.

Database connection credentials must come from environment variables / secret management and must never be committed to Git.

Production Cloud Run should use an appropriate pooled/serverless-friendly PostgreSQL connection.

---

## 27. Infrastructure and Cost Philosophy

The system is intentionally optimized for a private, single-user workload.

Expected profile:

```text
ChatGPT                     -> primary intelligence layer
Bigfish Skill               -> methodology and orchestration
Cloud Run                   -> very low usage; scale to zero
Neon PostgreSQL             -> low-volume serverless memory
financial-data APIs         -> optional, not core dependencies
server-side OpenAI usage    -> normally none
```

The system should avoid paying for infrastructure whose main purpose is hypothetical scale.

High concurrency, Kubernetes, permanent workers, GPU infrastructure, and server-side multi-agent clusters are out of scope unless real usage later justifies them.

---

## 28. Security Principles

Private investment memory should be treated as sensitive application data.

Minimum requirements:

- Tool endpoints require authentication.
- Database credentials never appear in source control.
- Production secrets use Cloud Run secret/environment configuration.
- Development and production databases are separated.
- Destructive operations are difficult to invoke accidentally.
- Appropriate database backup/recovery is enabled.
- Tool responses expose only the data required by the Skill.
- Public raw data is not stored unnecessarily.

---

## 29. Implementation Phases

Do not prematurely create a large multi-agent architecture.

### Phase 1 — Core Bigfish

```text
Bigfish Skill
+ Research Framework
+ Research Router
+ Evidence Rules
+ Dynamic Research Planning
+ Calculation Tools
+ Cloud Run Tool Server
+ Neon Memory
```

Implement first:

1. Neon development and production environments.
2. Minimal company/memory schema.
3. Search and company-memory retrieval.
4. Thesis / assumption / prediction / critical-unknown / watch-variable writes.
5. Valuation and calculation tools.
6. Skill-improvement storage.
7. Authentication.
8. Cloud Run deployment with `min instances = 0`, `max instances = 1`.
9. Tests for memory CRUD and deterministic calculations.

### Phase 2 — Research Discipline

Add:

- Devil's Advocate;
- incremental research;
- research updates;
- thesis comparison;
- stronger evidence labeling;
- valuation-to-thesis traceability.

### Phase 3 — Investment History

Add:

- Prediction Ledger;
- prediction reviews;
- Decision Journal;
- decision reviews;
- explicit separation of research and real transactions.

### Phase 4 — Learning

Add:

- calibration;
- outcome-vs-process review;
- mistake/post-mortem workflow;
- `$bigfish-upgrade`;
- Skill eval suite.

### Phase 5 — Cross-Company Intelligence

Add only if useful:

- company relationships;
- cross-company assumption propagation;
- Investment Knowledge Graph views.

### Multi-Agent Phase — Only if real need emerges

Only later consider distinct roles such as:

```text
CIO Agent
Financial Agent
Industry Agent
Valuation Agent
Risk Agent
```

Multiple Agents must solve real task-separation problems. They must not merely run similar prompts multiple times.

---

## 30. Architectural Non-Goals

Unless real requirements change, Bigfish should not become:

- a Bloomberg-style financial warehouse;
- a permanent financial crawler;
- a warehouse of annual reports, filings, PDFs, and public news;
- a system dependent on Yahoo, FMP, or any single market-data API;
- a server-side GPT research cluster;
- a Kubernetes deployment;
- a high-concurrency SaaS platform;
- a system that automatically treats research discussion as a real trade;
- a Skill that autonomously rewrites and publishes itself.

---

## 31. Final Operating Model

The intended long-term workflow is:

```text
User discusses an investment in ChatGPT
        ↓
Bigfish identifies the real research objective
        ↓
Research Router chooses the appropriate depth
        ↓
Bigfish builds a dynamic Research Tree
        ↓
ChatGPT retrieves high-quality public evidence
        ↓
Evidence is labeled and Critical Unknowns are identified
        ↓
Deterministic tools perform precise calculations
        ↓
Bigfish builds or updates Thesis + Assumptions
        ↓
Bigfish creates falsifiable Predictions where useful
        ↓
Devil's Advocate searches for disconfirming evidence
        ↓
Valuation is linked explicitly to the business thesis
        ↓
Investment judgment is formed
        ↓
Formal research memory is saved to Neon
        ↓
Future public information arrives
        ↓
Old predictions and assumptions are reviewed
        ↓
Errors are analyzed
        ↓
Process quality is calibrated
        ↓
Methodological lessons become Skill-improvement candidates
        ↓
Codex periodically turns validated lessons into tested Skill upgrades
```

The final objective is not simply to make Bigfish know more stock facts.

> **The real objective is to build a private Investment Research Operating System that compounds years of research history, preserves what was believed at the time, tests predictions against reality, separates luck from process quality, and continuously improves the user's investment methodology.**

---

## 32. One-Sentence Architecture

> **ChatGPT researches and reasons over the current public world; Bigfish Skill supplies investment discipline and orchestration; Cloud Run provides lightweight memory and deterministic tools; Neon preserves formal long-term investment knowledge; Codex periodically converts accumulated evidence and mistakes into tested, user-approved Skill upgrades.**
