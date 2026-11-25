# TindahanIQ — Live Demonstration Guide & Submission Checklist

Prepared for **CS365-F1 — Applied AI** final presentation.

---

## 1. Pre-Demonstration Checklist

- [ ] Virtual environment (`.venv`) activated and dependencies installed (`pip install -e ".[dev]"`).
- [ ] `.env` created from `.env.example` with a valid `GEMINI_API_KEY` (verify `.env` is ignored by `git status`).
- [ ] Run `pytest` to confirm all automated tests pass locally (`0` failures).
- [ ] Start the application:
  ```powershell
  streamlit run src/tindahaniq/app.py
  ```
- [ ] Verify the **Settings & Help** page shows `PASS` across all System Health checks and `AI Provider Key`.

---

## 2. Recommended 7-Minute Live Demo Script

### Step 1: First-Run Onboarding & CSV Data Ingestion (~1.5 mins)
1. Open **Upload Data** from the left sidebar.
2. Point out downloadable **Inventory** and **Sales** CSV templates (and support for local spreadsheet column headers like `pangalan`, `puhunan`, `presyo`, `petsa`).
3. Check **Validate only (Dry-Run Preview)** and upload `data/samples/demo_sari_sari_inventory.csv` (18 products across 6 sari-sari categories) to demonstrate non-mutating validation, then uncheck Dry-Run and click **Import Inventory CSV**.
4. Switch to **2. Upload Sales CSV** and import `data/samples/demo_sari_sari_sales_14d.csv` (37 transactions across 14 days, including intra-day timestamps and deliberate zero-sale slow movers like *Safeguard White Bar Soap* and *Alaska Condensed Milk*).
5. Briefly re-upload the same file once to show **SHA-256 duplicate batch protection** preventing accidental double-counting.

### Step 2: Store Overview Dashboard & Sales/Profitability Analytics (~1.5 mins)
1. Click **Dashboard** in the sidebar to highlight the 4 executive KPI cards (`TOTAL PRODUCTS`, `GROSS PROFIT` with 7-day comparison delta, `LOW STOCK ITEMS` with critical alert count, and `LATEST DAY SALES`), interactive Revenue vs. Gross Profit charts, and the right-hand **Business Insights (`Live Data`)** rail.
2. Open **Sales Analytics** to show:
   - Daily, Weekly, and Monthly time groupings + Peak Sales Window detection.
   - **Top-Selling Products** (*Coca-Cola Mismo*, *Lucky Me! Pancit Canton*) vs. **Slow-Moving / Zero-Sale Products** (*Safeguard*, *Alaska Condensed Milk*) tying up shelf capital.
   - Side-by-side **Gross Profit Margin (%)** vs. **Markup (%)** comparison table.

### Step 3: Inventory Intelligence, Budget Planner & Live Walk-In Sale (~1.5 mins)
1. Open **Inventory** → **Stock & Restock Intelligence** to show deterministic urgency badges (`CRITICAL`, `HIGH`, `LOW`, `HEALTHY`), daily sales velocity, estimated days left, and suggested restock quantities.
2. Switch to **Budget Restock Planner**, enter `₱2,000.00`, and show how TindahanIQ allocates whole supplier units across critical high-velocity staples for a wholesaler/Divisoria trip (plus downloadable `.csv` shopping list).
3. Switch to **Record Sale / Adjust Stock**, record a live walk-in sale of `2` bottles of *Coca-Cola Mismo*, and confirm stock deducts atomically while **Settings & Help** confirms `0` ledger discrepancies.

### Step 4: Interactive Pricing Simulator (~1 min)
1. Open **Pricing Simulator**, select *Lucky Me! Pancit Canton Calamansi 80g* (`₱16.00`), and simulate a `+₱2.00` increase (`₱18.00`).
2. Highlight the **Hypothetical Simulation** framing, projected gross profit gain, and the **Volume Cushion (Breakeven Volume Change %)** showing how much unit demand could dip before total profit drops below baseline.

### Step 5: Conversational AI Business Consultant (~1.5 mins)
1. Open **AI Assistant** (matching the Proposal Page 7 split view).
2. Click quick-action chips or ask the Proposal's core questions live:
   - *"Which of my products generates the highest profit?"*
   - *"How many packs of instant noodles should I restock?"*
   - *"What happens to my profit if I increase the price of Lucky Me! Pancit Canton by ₱2?"*
   - *"Which products have been selling poorly?"*
   - *"I have ₱2,000 available for restocking. Which products should I prioritize?"*
3. Point out the `Calculated via deterministic tools: ...` caption beneath each AI answer proving zero LLM mental math, then click **Export Chat** to download the consultation transcript as Markdown.
