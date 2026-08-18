# References

The research this architecture rests on. Read before proposing changes to §3, §4 or §6 of
`ARCHITECTURE.md` — the design choices are responses to specific findings, not defaults.

Verified August 2026. Regulatory timelines in particular move; re-check before relying on a date.

---

## Market input

- **Romanian banking-app comparative brief, 10 apps, 2025–2026** (project input document,
  `rezumat-brief-banking-apps-pentru-opus.md`). Source of: the incident-communication requirement,
  the re-authentication and diaspora onboarding pain points, the escalation-to-human rule, the
  reversible-personalisation principle, and the finding that no Romanian banking chatbot can
  execute a transaction.

## Ledger and core banking

- Fintechly, *Ledger System Design: Principles for Accuracy, Auditability, and Scale* —
  https://fintechly.com/infrastructure/infrastructure-ledger-system-design/
  Balances computed from journal lines as the source of truth; snapshots as derived data;
  DB-enforced idempotency keys returning the first result on replay.
- freeCodeCamp, *Build a Bank Ledger with PostgreSQL using Double-Entry Accounting* —
  https://www.freecodecamp.org/news/build-a-bank-ledger-in-go-with-postgresql-using-the-double-entry-accounting-principle/
  Serializable transactions with exponential backoff, settlement accounts, idempotency on retry.
- Crassula, *Banking Database Design 2026* —
  https://crassula.io/guides/banking-database-design/
  Separating the general ledger from the customer-facing account layer; append-only postings;
  retention partitioning designed in from the start.
- AWS, *Building a core banking system with Amazon QLDB* —
  https://aws.amazon.com/blogs/industries/building-a-core-banking-system-with-amazon-quantum-ledger-database/
  Core banking as system of record; ledger organised into accounts with computed balances.
- SDK.finance, *Ledger vs Core Banking System* —
  https://sdk.finance/blog/ledger-vs-core-banking-system-whats-the-difference/
  Why the ledger layer is worth isolating from product/workflow logic.

## Architecture style

- Fernando Moretes, *ADR: Modular Monolith vs Microservices in a Greenfield Fintech* —
  https://fernando.moretes.com/studies/adr-monolito-modular-vs-microservices-fintech
  The closest analogue to this project's situation: domain-bounded modules, ports/adapters,
  one database with a schema per module, pre-agreed extraction criteria.
- Viascom, *The Modular Monolith: A Field Guide* —
  https://medium.com/viascom/the-modular-monolith-a-field-guide-36dcf21a477b
  Boundaries decay without enforcement; direct calls for questions, events for facts; never
  integrate through shared data.
- Nimble AppGenie, *Microservices vs Monolith for Fintech Backends: 2026 Guide* —
  https://www.nimbleappgenie.com/blogs/microservices-vs-monolith-for-fintech-backends/
  Keeping payment logic bounded also keeps PCI-DSS audit scope narrow.

## EU regulation

- Norton Rose Fulbright, *PSD3 and PSR: From provisional agreement to 2026 readiness* —
  https://www.nortonrosefulbright.com/en/knowledge/publications/cedd39c6/psd3-and-psr-from-provisional-agreement-to-2026-readiness
- Open Banking Tracker, *PSD3 & PSR for Developers (2026)* —
  https://www.openbankingtracker.com/guides/psd3-psr-readiness
  Verification of Payee is a present-tense obligation under the Instant Payments Regulation
  (euro-area PSPs since 9 October 2025), not a future PSD3 one.
- KPMG Law, *PSD3 and PSR* —
  https://kpmg-law.de/en/psd3-and-psr-new-payment-regulation-for-payment-service-providers-and-banks/
  The mandatory authorisation dashboard for third-party access consents — why `/settings` is
  designed to grow one.
- IDnow, *PSD3 News: 5 Critical Changes* —
  https://idnow.io/insights/blog/psd3-news-5-changes-psp-act/
  SCA's two-factor rule survives; two inherence factors newly permitted.

## Accessibility

- Accessible.org, *EAA Requirements for Online Banking Accessibility* —
  https://accessible.org/online-banking-accessibilityeaa/
  In force 28 June 2025; covers websites, apps, **and authentication flows**.
- accessibility.build, *European Accessibility Act compliance* —
  https://accessibility.build/compliance/eaa
  EN 301 549 incorporates WCAG Level AA; auditing against WCAG 2.2 gives headroom as the
  harmonised standard updates.

## Agent architecture

- Anthropic, *Building Effective Agents* —
  https://www.anthropic.com/research/building-effective-agents
  Workflows vs agents; the orchestrator-workers pattern; start with the simplest thing that works.
- Anthropic, *How we built our multi-agent research system* —
  https://www.anthropic.com/engineering/multi-agent-research-system
  Each subagent needs an objective, an output format, tool guidance and clear boundaries — or
  agents duplicate work and leave gaps.
- decodethefuture, *Multi-Agent Systems Explained: 2026 Patterns* —
  https://decodethefuture.org/en/multi-agent-systems-explained/
  Orchestrator-worker dominates production deployments; the token overhead is real, so
  multi-agent should not be a default.
- Beam, *6 Multi-Agent Orchestration Patterns for Production* —
  https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production
  Orchestrator as single point of failure; context accumulation across workers; cost blow-ups at
  scale. Motivates the per-run token/cost counters.
- arXiv, *The Hitchhiker's Guide to Agentic AI* — https://arxiv.org/pdf/2606.24937
  Agent design patterns; graduate to autonomy only where dynamic routing is genuinely needed.
- arXiv, *Invisible Orchestrators Suppress Protective Behavior* — https://arxiv.org/pdf/2605.13851
  Safety risks specific to orchestrator-worker topologies. Relevant to seams 3, 4 and 7.

## Agentic payments standards (track, do not implement yet)

- Universal Commerce Protocol blog, *Agent Payments Protocol (AP2)* —
  https://universalcommerceprotocol.blog/en/agent-payments-protocol/
  Signed mandates moving between open and closed states; AP2 and Mastercard Verifiable Intent
  contributed to the FIDO Alliance in May 2026.
- eco.com, *AP2 Protocol Explained* —
  https://eco.com/support/en/articles/15192002-ap2-protocol-explained-google-s-agentic-commerce-standard-2026
  Intent / Cart / Payment mandates as W3C Verifiable Credentials; MCP as the tool layer beneath.
- eco.com, *Mastercard Agent Pay vs Visa Trusted Agent* —
  https://eco.com/support/en/articles/15192003-mastercard-agent-pay-vs-visa-trusted-agent-2026-compared
  Agentic Tokens scoped to agent, merchant and consent policy.
- Internet Pros, *Agentic Commerce 2026* —
  https://internet-pros.com/blog/agentic-commerce-ai-payments-visa-mastercard-2026/
  The operational lessons that became the agent constitution: adopt a standard rather than
  inventing one, treat agents as a security perimeter, enforce limits server-side, assume prompt
  injection, keep a human in the loop for high-stakes actions.
- Applied Technology Index, *2026 Comparative Analysis: Agentic Commerce Payment Protocols* —
  https://appliedtechnologyindex.com/research/2026-comparative-analysis-agentic-commerce-payment-protocols/
  The four-layer split: checkout orchestration, delegated payment authority, agent identity,
  metered resource access.

---

## How to use this list

The `mandates` table shape comes from the common denominator of AP2, Visa TAP and Mastercard
Agent Pay: **scoped, capped, time-bounded, revocable, attributable authority**. If those standards
converge differently, change the table, not the seam. The seam — a policy engine that every write
passes through regardless of who initiated it — is the durable part.
