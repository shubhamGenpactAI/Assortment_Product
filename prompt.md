# Executive Summary

If I were designing this for Category Managers, I'd make the page answer **4 questions in under 30 seconds**:

1. **Where am I going to lose sales?** (stock-out risk)
2. **Where am I over-invested?** (excess inventory)
3. **Which SKUs deserve more space/investment?** (winners)
4. **Which SKUs should be reduced or delisted?** (losers)

The forecast itself should be only **20% of the screen**. The remaining **80% should be decision support and actions.**

***

# Priority 1: High Business Impact Features

These directly influence sales, inventory productivity, margin, and working capital.

## 1. Forecast Opportunity & Risk Matrix

Instead of showing forecasts in a table, classify every SKU into action buckets.

### Example

| Category           | Criteria                                  | Action            |
| ------------------ | ----------------------------------------- | ----------------- |
| Stock-out Risk     | Forecast > Inventory                      | Replenish         |
| Excess Inventory   | Inventory > 12 weeks cover                | Reduce Orders     |
| Growth Opportunity | High Forecast Growth + High GMROI         | Expand Assortment |
| Delist Candidate   | Low Forecast + Low Health Score           | Review Delisting  |
| Transfer Candidate | High demand in Store A, excess in Store B | Transfer Stock    |

### Why Valuable

Category Managers don't want forecasts.

They want:

> "Tell me which 100 SKUs require action."

***

# 2. AI Copilot Recommendation Center

Combine:

* Forecast
* Inventory
* Health Score
* Delist Score
* Basket Role
* GMROI
* Margin
* Weeks of Cover

Generate actionable insights.

### Example

**SKU: Organic Almond Milk**

Recommendation:

> Increase replenishment by 20%. Forecasted demand is expected to grow 18% over the next 4 weeks. 
Current inventory covers only 1.8 weeks. SKU Health Score = 92. GMROI = 4.8. Top Basket Driver in Beverage category.

***

**SKU: Chocolate Biscuit 100g**

Recommendation:

> Review for delisting. 
Demand has declined 22% over the last 12 weeks. Health Score = 34. Delist Score = 88. GMROI below category average by 41%.

### Why Valuable

Transforms analytics into decisions.

***

# 3. Lost Sales & Revenue-at-Risk

Show:

### Metrics

* Potential Lost Units
* Lost Revenue
* Lost Margin
* Affected Stores

### Formula

```
Lost Sales =
Forecast Demand - Available Inventory
```

### Visualization

Top 20 SKUs at risk.

### Why Valuable

Category Managers care more about lost revenue than forecast accuracy.

***

# 4. Inventory Productivity Dashboard

Forecast + Inventory = Productivity.

Metrics:

* GMROI
* Sell-through
* Inventory Turn
* Weeks of Cover
* Margin Return

### Scatter Plot

X-axis:

Weeks of Cover

Y-axis:

GMROI

Bubble Size:

Revenue

Color:

Health Score

Immediately identifies:

* Overstocked winners
* Overstocked losers
* Understocked winners

***

# 5. Delist & Rationalization Hub

Leverage:

* Delist Score
* Health Score
* Forecast Trend
* Basket Role

### Classification

#### Keep

High demand + high role

#### Grow

High growth + high margin

#### Watch

Declining demand

#### Delist

Low demand + low health

***

### Example Insight

> 17 SKUs contribute only 0.8% of category sales while consuming 12% shelf space.

### Why Valuable

One of the highest ROI decisions in assortment planning.

***

# Priority 2: Strategic Planning Features

***

## 6. Forecast Confidence Layer

LightGBM can provide uncertainty ranges.

Show:

```
Expected Demand
Best Case
Worst Case
Confidence Interval
```

Visualization:

Forecast fan chart.

### Why Valuable

Helps buyers avoid over-ordering.

***

## 7. Forecast vs Capacity View

Compare:

* Forecast Demand
* Shelf Capacity
* Backroom Capacity
* Supplier Capacity

### Example

> Energy Drinks forecast exceeds shelf capacity by 23%.

Useful for assortment reviews.

***

## 8. Demand Surge Detection

Automatically identify:

* Promotion spikes
* Seasonal spikes
* Weather-driven spikes
* Emerging products

### Example

> Demand for Protein Bars expected to increase 37% next month.

***

# 9. What-If Scenario Planning

Potentially the most loved feature.

### Slider Controls

* Price change %
* Promotion depth
* Distribution expansion
* Shelf space
* Inventory investment

### Output

* Forecast impact
* Revenue impact
* Margin impact
* Inventory impact

### Example

> What happens if price drops by 5%?

Revenue:

+8%

Margin:

+3%

Units:

+14%

***

# 10. Open-To-Buy Recommendation

Forecast-driven purchasing recommendations.

Show:

```
Current Stock
Expected Demand
Safety Stock
Recommended Buy Qty
```

### Why Valuable

Directly supports purchasing decisions.

***

# Priority 3: Advanced AI Features

***

## 11. Basket-Aware Insights

Since you have Basket Role.

Classify SKUs:

* Traffic Driver
* Profit Generator
* Attachment Item
* Seasonal Item

### Example

> Do not delist SKU despite low margin. It appears in 42% of baskets containing premium coffee.

Very powerful.

***

## 12. Cannibalization Detection

Identify:

> Which SKU is stealing sales from another SKU?

Example:

```
SKU A +18%
SKU B -15%
```

Potential assortment overlap.

***

## 13. Assortment Gap Detection

AI identifies:

> Missing products in category.

Example:

> Protein Snacks growing rapidly but represented by only 2 SKUs versus peer stores averaging 8.

***

## 14. Similar SKU Benchmarking

For every SKU:

Compare against:

* Category average
* Brand average
* Region average
* Cluster average

### Example

```
GMROI: 2.1
Category Avg: 3.8
Cluster Avg: 4.1
```

Immediate context.

***

## 15. Forecast Driver Breakdown (SHAP)

Current idea is excellent.

Improve it further.

Show:

### Positive Drivers

* Promotion
* Seasonality
* Holiday
* Weather
* Trend

### Negative Drivers

* Inventory shortage
* Competitor activity
* Price increase

Visualization:

Waterfall chart.

***

# Priority 4: Alerts & Monitoring

***

## 16. Exception-Based Management

Instead of viewing all SKUs.

Only surface exceptions.

### Alerts

🔴 Stockout within 2 weeks

🟠 Forecast increase > 30%

🟠 Forecast decrease > 25%

🔴 GMROI below threshold

🔴 Delist candidate

🟢 New growth opportunity

***

# 17. Executive Category Health Score

Create one composite score.

Inputs:

* Forecast Growth
* Health Score
* GMROI
* Inventory Efficiency
* Service Level

### Example

```
Beverages: 86/100
Snacks: 73/100
Dairy: 91/100
```

Allows rapid category comparison.

***

# Recommended Page Layout

## Header

* Forecast Period
* KPI Selector
* Category Selector
* Store Cluster Selector
* Search

***

## Row 1: Executive Summary

Cards:

* Forecast Revenue
* Forecast Margin
* Revenue at Risk
* Excess Inventory Value
* Delist Candidates
* Growth Opportunities

***

## Row 2: Action Center (Most Important)

AI-generated recommendations ranked by financial impact.

Example:

```
1. Replenish SKU A
   Revenue Protected: $120K

2. Transfer SKU B
   Inventory Saved: $40K

3. Delist SKU C
   Shelf Space Released: 8 ft

4. Increase Assortment in Protein Snacks
   Expected Revenue Lift: $75K
```

***

## Row 3: Forecast + Inventory Visualization

* Forecast Trend
* Inventory Projection
* Days of Cover

***

## Row 4: Opportunity Matrix

Quadrants:

```
High Demand + Low Inventory
High Demand + High Inventory
Low Demand + High Inventory
Low Demand + Low Inventory
```

***

## Row 5: SKU Drilldown

Detailed SKU view with:

* Forecast
* SHAP Drivers
* Health Score
* Delist Score
* Basket Role
* GMROI
* Recommended Action

***


