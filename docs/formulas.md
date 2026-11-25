# TindahanIQ — Authoritative Business Intelligence Formulas

All authoritative numerical figures in TindahanIQ are calculated deterministically by Python application code (`src/tindahaniq/services/bi/formulas.py`) using exact base-10 `decimal.Decimal` arithmetic. The AI Business Consultant never computes financial figures via mental math.

---

## 1. Precision & Rounding Conventions

- **Currency (`₱` / `PHP`):** Stored in SQLite as integer centavos (`1 PHP = 100 centavos`) and quantized to `Decimal("0.01")` using `ROUND_HALF_UP`.
- **Percentages (`%`) & Rates:** Computed at full `Decimal` precision (28 significant digits) during intermediate steps and quantized to `Decimal("0.01")` (`ROUND_HALF_UP`) on output.
- **Zero-Denominator Guards:** Any ratio with a `0` denominator (e.g., margin when revenue is `₱0.00`, markup when unit cost is `₱0.00`, or percentage growth from `0`) returns `None` rather than raising a division error or fabricating a number.

---

## 2. Profitability Analyzer Formulas

For a single product or store aggregation over transactions $i \in \{1, \dots, n\}$:

1. **Gross Revenue (`₱`):**
   $$\text{Gross Revenue} = \sum_{i=1}^{n} \left(Q_i \times P_i\right)$$
   where $Q_i$ is `quantity_sold` and $P_i$ is historical `unit_price_at_sale`.

2. **Cost of Goods Sold — COGS (`₱`):**
   $$\text{COGS} = \sum_{i=1}^{n} \left(Q_i \times C_i\right)$$
   where $C_i$ is historical `unit_cost_at_sale`.

3. **Gross Profit (`₱`):**
   $$\text{Gross Profit} = \text{Gross Revenue} - \text{COGS}$$

4. **Gross Profit Margin (`%`):** *(Share of selling price/revenue retained as gross profit)*
   $$\text{Gross Margin (\%)} = \left(\frac{\text{Gross Profit}}{\text{Gross Revenue}}\right) \times 100$$

5. **Markup (`%`):** *(Percentage added on top of supplier unit cost)*
   $$\text{Markup (\%)} = \left(\frac{\text{Selling Price} - \text{Unit Cost}}{\text{Unit Cost}}\right) \times 100$$

> **Example (*Lucky Me! Pancit Canton*):** Cost = `₱12.25`, Selling Price = `₱16.00`  
> Unit Profit = `₱3.75` | **Gross Margin** = `23.44%` (`3.75 / 16.00`) | **Markup** = `30.61%` (`3.75 / 12.25`).

---

## 3. Sales Analytics Formulas

1. **Effective Window Days ($D_{\text{eff}}$):**
   $$D_{\text{eff}} = \max\left(1, (\text{Window End Date} - \text{Observed Start Date}) + 1\right)$$

2. **Average Daily Revenue (`₱`):**
   $$\text{Average Daily Revenue} = \frac{\text{Total Gross Revenue}}{D_{\text{eff}}}$$

3. **Period-over-Period Percentage Change (`%`):**
   $$\Delta\% = \left(\frac{V_{\text{current}} - V_{\text{previous}}}{|V_{\text{previous}}|}\right) \times 100 \quad (\text{when } V_{\text{previous}} \neq 0)$$

---

## 4. Inventory Intelligence & Budget Allocation Formulas

1. **Daily Sales Velocity ($\text{units/day}$):**
   $$v = \frac{\text{Units Sold in Window}}{D_{\text{eff}}}$$

2. **Estimated Days to Stock Depletion:**
   $$\text{Days to Depletion} = \frac{\text{Current Stock} \times D_{\text{eff}}}{\text{Units Sold in Window}} \quad (\text{when Units Sold} > 0, \text{ else None})$$

3. **Suggested Restock Quantity (Whole Supplier Units):**
   - When historical sales exist in window ($\text{Units Sold} > 0$):
     $$\text{Target Stock} = \max\left(\text{Reorder Point}, \left\lceil \frac{\text{Units Sold} \times (\text{Target Coverage Days} + \text{Lead Time Days})}{D_{\text{eff}}} \right\rceil\right)$$
     $$\text{Suggested Qty} = \max(0, \text{Target Stock} - \text{Current Stock})$$
   - Fallback when $\text{Units Sold} = 0$ and $\text{Current Stock} < \text{Reorder Point}$:
     $$\text{Suggested Qty} = \text{Reorder Point} - \text{Current Stock}$$

4. **Stock Urgency Classification:**
   - `CRITICAL`: `Current Stock <= 0`, OR `Days to Depletion <= Lead Time`, OR `Current Stock <= max(1, Reorder Point // 4)`.
   - `HIGH`: `Days to Depletion <= Lead Time + 2`, OR `Current Stock <= max(1, Reorder Point // 2)`.
   - `LOW`: `Current Stock <= Reorder Point`, OR `Days to Depletion <= Lead Time + 5`.
   - `HEALTHY`: All other items.

5. **Budget-Constrained Restock Allocation (`plan_restock_within_budget`):**
   - Candidates with `Suggested Qty > 0` are ordered deterministically by:
     1. Urgency tier (`CRITICAL` → `HIGH` → `LOW` → `HEALTHY`),
     2. Earliest `Days to Depletion`,
     3. Highest daily gross profit return per peso of supplier cost: $\frac{v \times \text{Unit Profit}}{\text{Unit Cost}}$.
   - Whole units are funded sequentially: $\text{Funded Qty} = \min\left(\text{Suggested Qty}, \lfloor \text{Remaining Budget} / \text{Unit Cost} \rfloor\right)$.

---

## 5. Pricing Simulator Formulas

Given current price $P_0$, proposed price $P_1$, unit cost $C$, baseline units $Q_0$, and expected volume change $e\%$ ($e \ge -100$):

1. **Simulated Volume ($Q_1$):**
   $$Q_1 = \text{round}_{\text{half-up}}\left(Q_0 \times \left(1 + \frac{e}{100}\right)\right)$$

2. **Gross Profit Impact (`₱`):**
   $$\Delta \text{Gross Profit} = Q_1(P_1 - C) - Q_0(P_0 - C)$$

3. **Breakeven Volume Change (`%`):** *(Volume change at which proposed total gross profit equals baseline gross profit, defined when $P_0 > C$ and $P_1 > C$)*
   $$\text{Breakeven Volume Change (\%)} = \left(\frac{P_0 - C}{P_1 - C} - 1\right) \times 100$$
