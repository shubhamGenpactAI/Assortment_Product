# Retail Assortment Optimization — Business Walkthrough Guide

> **Purpose:** Three story-driven walkthroughs for presenting the four-page platform to category managers, buyers, and merchandising leads. Each walkthrough follows a different narrative arc, so you can pick the one that best fits your audience and the time available.

---

## The Four Pages at a Glance

| Page | Icon | Core Question Answered |
|------|------|----------------------|
| **Category Intelligence** | 🧠 | What is the complete picture of every SKU's assortment decision — and why? |
| **Decision Hub** | ⚡ | What is urgent right now, and what is the financial cost of inaction? |
| **New SKU Intelligence** | ✨ | Should we list a new SKU, where, and how much will it sell? |
| **Agent Hub** | 🕵️ | What do I need to do *today*, are my decisions right for every cluster, and how do I communicate them? |

---

## Walkthrough 1 — "The Morning Briefing"
### *Start your day in five minutes, act in fifty*

---

### 1. Ideal Audience
Category Managers and Merchandising Analysts who use the platform daily or weekly. This walkthrough mirrors how a CM would actually open the tool on a Monday morning before a buyer review. It is the most **operationally realistic** of the three approaches and works best for internal team demos or change-management sessions where you need to prove day-to-day usefulness.

---

### 2. Where to Start — and Why
Begin on the **Agent Hub → Watchdog tab**. This is the only page that answers the question "What do I *not* already know?" before the user has clicked anything else. Starting here creates immediate engagement because the screen shows a ranked, financial-impact-sorted list of exceptions — not a blank filter bar.

---

### 3. Page-by-Page Flow

```
Agent Hub (Watchdog)
      ↓  "Here are today's top 3 problems"
Decision Hub
      ↓  "Let me prove why those problems are real"
Category Intelligence
      ↓  "Let me see the full decision landscape around that SKU"
Agent Hub (Brief)
      ↓  "Now I can document and share my decision"
```

---

### 4. What Each Stop Answers

| Stop | Page | Business Question |
|------|------|-------------------|
| 1 | Agent Hub → Watchdog | What are the top 10 assortment exceptions I need to act on today, ranked by financial impact? |
| 2 | Decision Hub | What does the data say about those specific SKUs — inventory, demand trajectory, delist risk? |
| 3 | Category Intelligence | What is the formal Keep/Watch/Delist recommendation for each problem SKU, and what is the narrative justification? |
| 4 | Agent Hub → Brief | How do I turn this analysis into a vendor negotiation brief or a delist rationale I can share? |

---

### 5. KPIs and Insights to Emphasise

**Agent Hub — Watchdog:**
- **Red count** in the summary strip — e.g. "5 critical items need same-day attention"
- **Total Financial Impact** — e.g. "$482K is at risk across today's digest"
- **Conflict flag** — SKUs simultaneously flagged as Stock-out Risk AND Delist Candidate; these are the ones where doing nothing is actively harmful in both directions
- **Priority Score** — explain that it combines severity, financial scale, and whether signals conflict

**Decision Hub:**
- **Revenue at Risk** KPI card — stockout gap translated into dollars
- **Category Health strip** — which sub-categories are green vs. red as a quick portfolio heartbeat
- **Exception Alerts feed** — the same items the Watchdog surfaced, now with store-level detail and weeks-of-cover context
- **Risk Matrix** — show the Transfer Candidate row: "This SKU is simultaneously starved in one store and overstocked in another — we can solve both problems with one internal transfer"

**Category Intelligence:**
- **Delist Score + Health Score** in the SKU drawer — reinforce the data-backed recommendation
- **Recommendation Narrative** — the system's plain-English explanation of why the decision was made
- **Forecast fan chart** — show that the 6-week forward view underpins the replenishment or delist decision, not just historical data

**Agent Hub — Brief:**
- **Section count and auto-populated content** — emphasise that a complete vendor brief was drafted in seconds
- **Polish Tone (AI)** button — demonstrate that a human reviews everything; the AI only improves style, never invents a number

---

### 6. Sample Narration

> "It's Monday morning. Before I open a single spreadsheet, I come here — the Watchdog. The system has already analysed every SKU across every store and ranked my exceptions by financial impact. Right now I can see 5 critical items, and together they put $482K at risk this week.
>
> Notice item number two: *[SKU name]* is flagged with both a **Stockout Risk** and a **Delist Candidate** signal — that conflict badge in red tells me the system found a tension I need to resolve before I do anything. I can't delist something I'm also about to run out of; I need to understand which signal is dominant first.
>
> Let me jump to Decision Hub and filter to that store. The Category Health strip immediately tells me Anti-Dandruff Treatment is the weakest sub-category — composite score 42. The KPI bar shows $18,400 of lost revenue just from that one SKU. The Risk Matrix confirms it's a Stock-out Risk with 1.2 weeks of cover left.
>
> Now I flip over to Category Intelligence, search for the SKU, and open the drawer. The delist score is 0.83 — but the forecast shows a demand *uptick* in the next 6 weeks. That's why there's a conflict. The system flagged it for delist based on historical performance, but the forward-looking model says demand is recovering. My decision: replenish for this cycle and re-evaluate at the next reset.
>
> I'm presenting to the supplier in two hours. I go to Agent Hub → Brief, select Vendor Negotiation, scope it to this sub-category, and in 8 seconds I have a structured brief with the cross-sell pairs, the delist rationale for the truly weak SKUs, and a suggested ask. I hit *Polish Tone* and it reads like a professional document — every number came directly from the data I just walked through."

---

### 7. Best Practices

- **Lead with money, not methodology.** Open with "$482K at risk today" before explaining what a delist score is.
- **Use the conflict flag as a story hook.** The tension between two opposing signals is immediately relatable — every CM has faced "should I reorder or delist this?"
- **Don't over-click.** This walkthrough visits 4 screens but each for a specific, stated reason. Narrate the *why* before you click.
- **Leave the AI Copilot for questions from the audience.** When someone asks "but what about Shampoo?", type it live into the Copilot. Real-time answers to audience questions are more persuasive than a pre-rehearsed demo.
- **Time budget:** 15–20 minutes for the full flow; 10 minutes if you focus on Watchdog → Decision Hub only.

---
---

## Walkthrough 2 — "Following the Evidence"
### *One SKU, one store, one end-to-end decision journey*

---

### 1. Ideal Audience
Buyers, Senior Category Managers, or anyone who needs to see **accountability and auditability** in a data-driven recommendation. This walkthrough works well for stakeholders who are sceptical of "AI black boxes" because it shows every number, every source, and every human decision point. Also ideal for training new team members on how to use the platform end to end.

---

### 2. Where to Start — and Why
Begin on the **Decision Hub → Exception Alerts** panel. Identify a specific red alert — a Stockout Risk with the highest lost revenue — and treat that single SKU × Store pair as the protagonist of the whole story. Every subsequent step is asking "what else does the system know about this specific protagonist?"

The reason for starting in the alerts panel rather than the Watchdog is that it lets you **point to the raw signal first**, then show how the Agent Hub synthesises and ranks many such signals. This sequence (raw → synthesised) is better for sceptical audiences.

---

### 3. Page-by-Page Flow

```
Decision Hub (Exception Alerts — pick the top red alert)
      ↓  "Here is the raw signal — a specific SKU at a specific store"
Decision Hub (Risk Matrix — filter to that store + sub-category)
      ↓  "The risk matrix confirms and quantifies the exposure"
Decision Hub (Lost Sales chart — same filter)
      ↓  "Here is what this is costing us in dollars, today"
Decision Hub (Inventory Scatter — hover on the SKU bubble)
      ↓  "Is this a one-off or a symptom of a structural inventory problem?"
Category Intelligence (filter to SKU, open SKU Drawer)
      ↓  "What is the full decision recommendation and its justification?"
Agent Hub (Localization — filter to sub-category)
      ↓  "Should the decision be the same in every cluster, or do we need a nuanced call?"
Agent Hub (Watchdog — show where this SKU ranks)
      ↓  "How urgent is this relative to everything else on my list?"
```

---

### 4. What Each Stop Answers

| Stop | Page / Panel | Business Question |
|------|-------------|-------------------|
| 1 | Decision Hub → Alerts | Which store and SKU is at immediate risk, and what type of risk is it? |
| 2 | Decision Hub → Risk Matrix | How does this SKU compare to others in the same risk tier? |
| 3 | Decision Hub → Lost Sales | What is the exact dollar cost of the stock gap today? |
| 4 | Decision Hub → GMROI Scatter | Is this SKU fundamentally efficient, or is it structurally weak? |
| 5 | Category Intelligence → SKU Drawer | What is the formal recommendation, and can I see the 6-week demand forecast? |
| 6 | Agent Hub → Localization | Does this SKU perform differently in different store clusters? |
| 7 | Agent Hub → Watchdog | Where does this item rank in my overall priority queue? |

---

### 5. KPIs and Insights to Emphasise

- **Weeks of Cover (WoC)** in the alert card — the single most actionable inventory metric; below 2 weeks means a stockout is virtually guaranteed before the next delivery window
- **Lost Revenue vs Lost Margin** side by side in the Lost Sales chart — helps the audience understand that margin erosion is often worse than topline revenue loss
- **GMROI scatter quadrant** — point to the "High GMROI + Low WoC" quadrant and say "this is exactly where you *don't* want a stockout — these are your most profitable, fastest-moving SKUs"
- **Forecast fan chart** (in SKU Drawer) — the confidence band around the forecast is crucial: a narrow band means high certainty, a wide band means the replenishment decision carries more risk
- **Divergence magnitude** (Localization) — even a 0.04–0.08 difference in delist score across clusters can mean the difference between keeping and delisting a SKU in one geography
- **Priority rank and conflict flag** (Watchdog) — close the loop by showing that the system already knew this SKU was a priority before you clicked on it

---

### 6. Sample Narration

> "Let me tell you the story of a single SKU — and show you how the platform walks us from an alert to a defensible decision in under 10 minutes.
>
> I'm on the Decision Hub. I can see a red alert at the top of the feed: *[SKU name]* at Store ST04, 1.2 weeks of cover. That is a ticking clock. The next delivery is in 2 weeks — if we don't act today, this store runs out and we miss every sale until restocking.
>
> I filter the Risk Matrix to that store. The SKU sits in the Stock-out Risk bucket with $18,400 of financial impact — that's the model's estimate of revenue we will lose if we do nothing.
>
> I move down to the Lost Sales chart. Same story: $18,400 in lost revenue, $5,200 in lost margin. Now this is no longer a theoretical risk — it's a forecast liability.
>
> The GMROI scatter is interesting. The SKU sits in the top-left quadrant: High GMROI, Low Weeks of Cover. That means it's a *star performer* that's been stripped lean. This is not a weak SKU we should delist — it's a strong SKU we've under-replenished.
>
> I open Category Intelligence, find the SKU, and pull up the drawer. The forecast fan confirms the demand is stable and slightly growing. The Recommendation Narrative says 'Replenish — strong commercial metrics, insufficient cover given forecast uplift.'
>
> But before I send a replenishment order, I check one more thing: Agent Hub → Localization. Is the demand pattern the same in all three store clusters? I can see that in the Digital-First Urban cluster, the delist score is measurably lower than the global score — meaning this cluster is actually *stronger* than the global average. This confirms our replenishment decision: not only should we refill ST04, we should investigate whether the whole Digital-First Urban cluster is under-served.
>
> Finally, the Watchdog confirms this SKU sits at rank #2 in today's priority digest — it was already surfaced without me having to hunt for it. The system knew. We just walked through the evidence trail that explains *why*."

---

### 7. Best Practices

- **Pre-select your protagonist SKU before the demo.** Pick a SKU that appears in the Exception Alerts, shows up in the Risk Matrix, has a non-trivial Lost Revenue figure, and has cluster divergence. Running through the filters live adds authenticity but requires rehearsal.
- **Show the evidence trail explicitly.** Each panel should feel like a confirmation of what the previous panel revealed — never a surprise or a contradiction. If they do contradict, address it directly; it shows the system is nuanced, not broken.
- **Narrate decisions out loud.** At every step, say "therefore my decision is…" before moving to the next panel. The audience should never have to infer what the manager *would* do.
- **Use the Localization override live.** If the data supports a cluster-specific decision, click Approve Override during the demo. The override gets written to the audit log in real time — this is a powerful proof point for auditability.
- **Time budget:** 20–25 minutes for the full flow.

---
---

## Walkthrough 3 — "The Category Review"
### *Start with the portfolio, drill to the planogram decision*

---

### 1. Ideal Audience
Category Directors, Buyers, and Merchandising Leads who are responsible for a full sub-category — not individual stores. This walkthrough starts at the highest level of abstraction (which sub-category is performing?) and progressively drills to SKU-level decisions and cluster-level nuances. It's the right approach for **quarterly or monthly category reviews**, range resets, or any conversation where the audience thinks in terms of sub-categories and brands before thinking about individual products.

---

### 2. Where to Start — and Why
Begin on the **Decision Hub → Category Health Strip**. The pill-badges across the top of the page give an immediate portfolio snapshot — "Shampoo is healthy (score 74), Hair Mask is struggling (score 38)" — in a single visual that requires no explanation. This creates an agenda for the entire walkthrough: the audience naturally asks "why is Hair Mask at 38?" and you spend the rest of the demo answering that question.

---

### 3. Page-by-Page Flow

```
Decision Hub (Category Health Strip — pick the lowest-scoring sub-category)
      ↓  "Here is the category in trouble. What does 'in trouble' mean financially?"
Decision Hub (KPI Header — filter to that sub-category)
      ↓  "Revenue, margin, inventory waste — the financial case for action"
Decision Hub (Delist & Rationalization Hub — same filter)
      ↓  "Which specific SKUs are carrying the category down?"
Decision Hub (Inventory Scatter — same filter)
      ↓  "Are weak SKUs just sitting on shelves tying up working capital?"
Decision Hub (AI Copilot — ask a category-level question)
      ↓  "What should I prioritise in this sub-category?"
Category Intelligence (filter to Sub-Category — view all SKU decisions)
      ↓  "See every SKU's full decision, health band, and justification"
Agent Hub (Localization — filter to Sub-Category)
      ↓  "Do the same delist decisions hold across all store clusters?"
New SKU Intelligence
      ↓  "If I delist weak SKUs, what do I replace them with?"
Agent Hub (Brief — Vendor Negotiation)
      ↓  "I now have everything I need to walk into the supplier meeting"
```

---

### 4. What Each Stop Answers

| Stop | Page / Panel | Business Question |
|------|-------------|-------------------|
| 1 | Decision Hub → Health Strip | Which sub-categories are healthy and which need intervention right now? |
| 2 | Decision Hub → KPI Header | What is the financial scale of the problem in the weak sub-category? |
| 3 | Decision Hub → Delist Hub | Which specific SKUs are anchoring the sub-category down? |
| 4 | Decision Hub → GMROI Scatter | Are the weak SKUs also inefficient from an inventory perspective? |
| 5 | Decision Hub → AI Copilot | What is the highest-leverage action in this sub-category? |
| 6 | Category Intelligence | What is every SKU's formal recommendation across every granularity level? |
| 7 | Agent Hub → Localization | Should any delist decisions be modified for specific store clusters? |
| 8 | New SKU Intelligence | What new products could replace the delisted SKUs? |
| 9 | Agent Hub → Brief | How do I package this into a supplier meeting brief? |

---

### 5. KPIs and Insights to Emphasise

**Category Health Strip:**
- The composite score (0–100) and its five drivers: health, growth, GMROI, sell-through, delist-free %
- Use the colour system as a rapid triage: green (≥70) = leave alone, amber (45–69) = watch, red (<45) = act

**KPI Header (filtered to sub-category):**
- **Excess Inventory Value** alongside **Revenue at Risk** — this contrast tells the story of a category that has over-stocked the wrong SKUs and under-stocked the right ones
- **Delist Candidates count** — show as a % of total SKUs in the sub-category (e.g. "8 of 12 SKUs in Hair Mask are delist candidates — that's a 67% cull rate. This range needs rebuilding, not tweaking")

**Delist & Rationalization Hub:**
- The auto-generated insight sentence at the top (e.g. *"14 SKUs contribute only 4.2% of forecast revenue but consume significant shelf space"*) — this is the single most quotable line in the platform; it translates a data table into a boardroom argument
- **Watch bucket** — these are the borderline SKUs where the decision is not yet clear; show that the system doesn't pretend to know everything, it flags uncertainty appropriately

**GMROI Scatter:**
- Focus on the bottom-right quadrant: **Low GMROI + High WoC** — these are the dead inventory SKUs; every bubble in this quadrant is capital that should be freed up
- Bubble size shows revenue scale — a large bubble in the dead quadrant is a compelling argument for action

**AI Copilot:**
- Ask: *"Which 3 SKUs in Hair Mask should I delist first, and what is the total shelf space and working capital I would recover?"*
- The streamed response gives a ranked, dollar-quantified recommendation in real time — this moment often generates the most reaction from a live audience

**Agent Hub → Localization:**
- Highlight cases where a global Delist recommendation has a cluster with meaningfully lower divergence — e.g., "This SKU is a global Delist candidate, but in Digital-First Urban stores its cluster score is lower — maybe it has a niche following online-adjacent shoppers that we'd be destroying with a blanket delist"

**New SKU Intelligence:**
- Show the similarity score table for a proposed replacement SKU — top analog SKUs, their historical demand curves, and the store-level 6-week forecast
- The cannibalization analysis is key for the supplier conversation: "If I list your new product, it cannibalizes 12% of SKU X — I'll need better margin on the new line to compensate"

---

### 6. Sample Narration

> "Every category review starts the same way: where do we have a problem, and how big is it?
>
> Look at this health strip across the top of the Decision Hub. Shampoo and Conditioner are both in the green — healthy, nothing urgent. But Hair Mask is sitting at 38 out of 100. That's red. Something is wrong in that sub-category.
>
> I filter to Hair Mask. The numbers land immediately: $142K in forecast revenue over the next 6 weeks, but also $47K in excess inventory value and 8 delist candidates. This is a category with too many SKUs fighting for the same shelf space — and most of them are losing.
>
> The Delist Hub makes the case in one sentence: *'8 SKUs contribute only 3.1% of forecast revenue but consume significant shelf space and working capital.'* That is the opening line of our next supplier conversation.
>
> The GMROI scatter confirms it visually. See that cluster of bubbles in the bottom right? Low GMROI, high weeks of cover. Those SKUs are sitting on shelves, not turning. Each one of those bubbles is working capital we could redeploy.
>
> I ask the AI Copilot: 'Which 3 Hair Mask SKUs should I delist first and why?' — and in 15 seconds I have a ranked, dollar-backed answer.
>
> Now before I finalise my list, I check one thing the traditional review process misses: Agent Hub → Localization. Is the delist decision the same for every store cluster? Here I can see that one of my proposed delistings actually performs measurably better in Affluent Suburban stores — its cluster delist score is 0.24 compared to a global score of 0.71. That's a 0.47 divergence. If I delist it everywhere, I am destroying a product that is genuinely working for a segment of my estate. Instead, I approve a targeted override: Keep in Affluent Suburban, Delist everywhere else.
>
> I've freed up shelf space. Now what do I fill it with? I open New SKU Intelligence and run a similarity search for a product our supplier is pitching. The system finds three analog SKUs in our own range, forecasts 6-week demand by store, and shows that it would cannibalize approximately 8% of our current category revenue — manageable. I note the forecast for the negotiation.
>
> Finally, Agent Hub → Brief. I select Vendor Negotiation, scope it to Hair Mask, and the brief writes itself: executive overview, cross-sell pairs, the delist rationale for the 7 global exits, the cluster-specific override, and a suggested ask around the new listing. I hit Polish Tone, export as Markdown, and I'm ready for the meeting."

---

### 7. Best Practices

- **Open with the health strip and say nothing else for 10 seconds.** Let the audience read the colours. Someone will always point at the lowest score and ask why — you've just made them curious without saying a word.
- **The Delist Hub insight sentence is your anchor quote.** Write it on a whiteboard or slide as you read it — "X SKUs, Y% of revenue" is the kind of memorable, shareable stat that travels beyond the room.
- **Run the AI Copilot question live.** For executive audiences, seeing the system generate a ranked recommendation in real time is more impressive than any feature explanation.
- **Show the Localization override as a moment of nuance.** The business value is not just efficiency — it's that the platform prevents *bad* decisions as much as it enables *good* ones. A blanket delist reversed for one cluster is a compelling proof of sophistication.
- **End with the Brief.** Never let the walkthrough end on an analytical output. End on a communication output — a brief that can be taken into a meeting — because that is where the business value becomes tangible to non-technical stakeholders.
- **Time budget:** 25–30 minutes for the full flow; 20 minutes if you skip New SKU Intelligence.

---
---

## Comparison Summary

| Criterion | Walkthrough 1: Morning Briefing | Walkthrough 2: Following the Evidence | Walkthrough 3: Category Review |
|-----------|--------------------------------|--------------------------------------|-------------------------------|
| **Best audience** | Daily CM users; team change-management | Sceptical buyers; auditors; training | Category Directors; range review meetings |
| **Starting point** | Agent Hub — Watchdog | Decision Hub — Exception Alerts | Decision Hub — Health Strip |
| **Narrative arc** | Daily workflow | Single SKU accountability chain | Portfolio → SKU drill-down |
| **Time required** | 15–20 min | 20–25 min | 25–30 min |
| **Pages visited** | 3 (Hub, DH, CI) + Brief | 4 (DH, CI, Hub, Hub) | All 4 pages |
| **Strongest proof point** | Financial impact of ranked alerts | Auditability and evidence trail | Portfolio breadth + nuanced localization |
| **Risk if data is thin** | Low — only needs top alerts and one brief | Medium — needs a compelling protagonist SKU | Higher — needs a visibly weak sub-category |

---

## Recommended Walkthrough for a First-Time Demo

### ★ Walkthrough 1 — "The Morning Briefing"

**Recommendation:** For a first demo with a retail category manager who has never seen the platform, use Walkthrough 1.

**Why:**

1. **It starts with a result, not an explanation.** The Watchdog opens with "$482K at risk, 5 critical items." The CM sees immediate relevance before you've explained anything.

2. **It mirrors their actual job.** Category managers already have a morning routine — checking emails, spreadsheets, and alerts from multiple systems. This walkthrough replaces that routine with a single screen, making the value proposition obvious rather than argued.

3. **The Brief creates a satisfying ending.** The walkthrough closes with a tangible deliverable — a completed vendor brief — rather than a chart. First-time audiences need to leave with something concrete to justify the platform.

4. **It is the shortest (15–20 minutes)** and the least dependent on having a "perfect" dataset. Even if cluster divergence data is thin or a new SKU hasn't been set up, the Watchdog + Decision Hub + Brief flow works on any real assortment data.

5. **It is recoverable if something goes wrong.** If the AI Copilot doesn't generate a great response, or a filter produces fewer results than expected, the narrative ("here's what matters today") doesn't collapse — you simply narrate around it. Walkthrough 2 depends on a single protagonist SKU behaving as expected, which is riskier.

**Opening line for the demo:**
> *"Before I show you any feature, let me ask: on a typical Monday, how long does it take you to figure out what you need to act on this week? This walkthrough answers that question in under two minutes — and then shows you everything the system can do to help you act on it."*

---

*Document prepared 2026-07-02 | Retail Category Growth · Genpact*
