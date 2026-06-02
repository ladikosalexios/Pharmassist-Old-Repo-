# B2B API Pricing & Packaging — Review Notes

Review of `PharmAssist_B2B_API_Pricing.md` (Enterprise / multi-location operator tiering, May 2026 draft).

This document collects the substantive feedback before the pricing/packaging is shared externally. It's organised by severity: pre-empt-before-sales-conversation issues first, then smaller calibrations.

## What works

- **Removing prescription execution** is the right call. It sidesteps HMVS approval, HL7 CDA generation, dispense liability, and positions PharmAssist as a *layer on top of* an IMS rather than a replacement. Chains keep Pharmaca/SAPHE for POS+inventory and add PharmAssist for clinical intelligence — a far easier sale.
- **Three-tier structure** (Core / Clinical / Platform) maps cleanly to buyer motivation: commodity infrastructure → clinical differentiator → network-scale features. Clean upsell path.
- **"Cheaper than building it yourself" framing** on Core is genuinely true and quantifiable: 3–6 months × senior engineer + ongoing maintenance ≫ the annual subscription at any reasonable customer size.
- **Honest dependency notes** (ΕΟΠΥΥ category requirement, HMVO registration, EU-LLM DPA) set realistic expectations.
- **Pharmacovigilance intro rate** (€42 → €52 at month 7) is a clever contractual mechanism for the chicken-and-egg problem of signal quality requiring data volume.

## Major concerns to address before external sales conversations

### 1. Pricing is likely too low — possibly by 2-3×

At €52/location/month, even the Platform tier is < €1.75/day. Reference points:

- A single Twilio SMS costs ~€0.05
- US clinical decision support APIs (UpToDate, Clinical Pharmacology) bill €1-3 per query
- Greek hospital pharmacy software runs €200-500/seat/month
- A real-world pharmacy makes 200-500 transactions/day; one prevented adverse event/month is worth €1000s

The €15 Core tier is especially underpriced — ΗΔΥΚΑ integration + safety engine + drug catalog sync at €0.50/day reads like a freemium tier, not core revenue.

**Suggested baseline:** Core €40, Clinical €85, Platform €150. Or keep €15 as a single-pharmacy/developer tier and introduce "Chain Core" at €40+ with SLA + support.

### 2. Per-location pricing ignores usage variance and creates LLM cost risk

A 50-transactions/day pharmacy and a 500-transactions/day pharmacy pay the same. That leaves money on the table for high-volume customers AND creates real LLM cost exposure on Clinical tier:

- SPC Q&A (RAG) via Claude/GPT-4: €0.01-0.05/query
- Heavy-use pharmacy at 500-1000 queries/month → €10-50 in LLM cost
- That already eats the €17 marginal margin between Core and Clinical

**Suggested:** per-location BASE fee + included query budget + per-call overage. E.g. "Clinical includes 500 SPC queries/location/month, additional at €0.05 each." Standard usage-based SaaS pattern.

### 3. The "1,000 locations" example is unrealistic for the Greek market

Greece has ~10,500 pharmacies total, but the actual multi-location chain market is small. Most "chains" are 5-50 locations. SYFA-style cooperatives are large but operationally decentralised.

Implications:
- Reaction Network Alert + Pharmacovigilance Signal Detection are operationally useless below ~100 locations
- A 10-location chain at Platform tier = €520/month for minimal network value
- The TCV table reads as a slide for a VC, not a realistic procurement conversation

**Suggested:** show two scenarios in the pricing doc — "20-location regional chain (realistic year-1 customer)" and "1,000-location enterprise (aspirational)." The realistic case is the one a procurement team will benchmark against.

### 4. Some Platform features are not actually shippable yet

| Feature | Reality |
|---|---|
| **Insurance Pre-Authorization Agent** | ΕΟΠΥΥ has no electronic submission API. "Prepare paperwork" half ships; "submit + track" doesn't. Selling the full vision is selling something blocked on a third-party. |
| **Reaction Network Alert** | Works for *customer's own* locations (good — they own that data). But the doctor / other-pharmacy contact directory referenced in earlier scoping is missing. Scope clearly to "your network" not "any pharmacy." |
| **HMVS in Platform tier** | Operationally weird placement. Any pharmacy doing prescription dispense needs FMD verification, regardless of whether they want AI features. Forcing upsell-to-Platform doesn't match real need. |

**Suggested:**
- HMVS as a **separate add-on** (~€10/location/month), available with any tier
- Insurance Pre-Auth sold as "Prep-only" now, full version "when ΕΟΠΥΥ API ships"

### 5. Missing pieces enterprise buyers will ask for

| Missing | Why it matters |
|---|---|
| **SLA commitment** | At €600k+ TCV, buyers expect 99.5%/99.9% uptime guarantees with service credits |
| **Data residency statement** | Greek pharmacies require Greek/EU hosting commitments in writing |
| **Integration approach** | Most chains don't have engineering teams — either we provide integration consulting (already charging for it) OR we sell *through* IMS vendors (Pharmaca, SAPHE) — different sales motion. Be explicit which |
| **Webhook delivery guarantees** | Retry policy, dead-letter queue, idempotency — basics for enterprise webhook offerings (Recall, Pre-Auth, Reaction Network) |
| **Security posture** | SOC2-equivalent statement, customer-managed encryption keys option, audit log retention policy — healthcare procurement asks for these by month 2 |
| **DPA framework** | Per-customer Data Processing Agreement template |

### 6. Onboarding fee is too low

€35-60k for an enterprise healthcare API integration is below market. Similar US/EU healthcare integrations bill €100-300k. Even adjusted for Greek market, €60-100k is more defensible — the buyer's procurement won't blink at the higher number; you're leaving margin.

## Smaller calibrations

- **€32 / location for Clinical** — odd round number. €30 or €35 processes faster in buyer's head.
- **3-year discount of 20%** is generous given LLM costs are falling fast (locking in 3-year price gives back margin you don't need to). Consider 15%.
- **"AI Safety Flag Explanations"** — be explicit about Greek-language quality. If general-purpose Claude/GPT-4 Greek is good enough, great; if it needs Greek-tuned models, that's additional cost.
- **"No PII to LLM" policy** is currently a footnote. Surface it as a sales asset / competitive moat — "our competitors will leak patient data to LLMs; we don't" is a procurement-meeting line, not a footnote.
- **Patient Condition Inference** (Clinical tier) — beautiful feature, legally interesting. Add the same disclaimer used for AI ADR narrative ("suggestions only — caller confirms before write").

## Concrete proposed changes (summary)

1. **Reprice:** Core €40, Clinical €85, Platform €150 (or split Core into "Developer" €15 / "Chain Core" €40+).
2. **Add usage-based component** on Clinical & Platform (per-location base + included query budget + overage).
3. **Split HMVS into a separate add-on** rather than Platform-locked.
4. **Scope-down or remove Insurance Pre-Auth** until full loop ships — sell "Prep-only" interim.
5. **Add: SLA table, data residency commitment, integration approach (direct vs IMS-partner), webhook delivery guarantees, security posture statement.**
6. **Update TCV scenarios** to lead with a realistic 20-100 location chain alongside the 1,000-location aspirational case.
7. **Surface "no PII to LLM"** as a feature/moat, not a footnote.
8. **Raise onboarding fee floor** to €60k minimum (range €60-120k).

## Out of scope for this review

This review covers the *Enterprise / multi-location operator* offering as written — buyers who already have or will integrate via an IMS. A separate offering is needed for **independent pharmacies without an IMS partner** (standalone PharmAssist for safety/clinical workflows without prescription execution). That packaging is its own conversation.
