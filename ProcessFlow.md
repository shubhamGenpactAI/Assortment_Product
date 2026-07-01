** Step 1: Raw Files **

- All Raw files are in one database.
- We need to convert these raw files to be used for our application.
- e.g.: sales files are at SKU, store, transaction level. We aggregate to SKU + Store + Week for forecasting.
- inventory is at daily level; we aggregate to week level (using END-OF-WEEK on-hand, not sum) to   improve assortment forecasting.
- Other raw files are:
    SKU Master (SKU details) - used for SKU clustering, New SKU similarity matching
    Store Master (store details) - used for store clustering
    SKU Level Sentiment - raw sentiment from Brandwatch/other sources
    SKU Level Market analysis data (syndicated) - used to compare our growth vs market growth

 Need to check the refresh frequency.

** Step 2: ETL **

Once raw files are finalised and processed via ETL, we have:
1. Weekly SKU + Store Sales
2. Weekly SKU + Store Inventory
3. SKU Master
4. Store Master
5. SKU Level Sentiment
6. SKU Level Market analysis data

  Data Quality gate before load: 
  - Referential integrity (every Sales/Inventory SKU exists in SKU Master; every Store exists in Store Master)
  - grain/duplicate check, null + negative-value check, calendar continuity (fill zero-sales weeks so demand is not censored).
  - To Derive, stockout flag from inventory, weeks-of-supply, promo flag alignment, net sales/margin reconciliation.
  - Build a Calendar/Time dimension (week-ending date, period, season) so all tables join on a consistent week key.

** Step 3: Tables in Database **

Create relationships among these tables in a star schema:
- Facts: Weekly_Sales, Weekly_Inventory, Sentiment, Market.
- Dimensions: SKU (keep small), Store (keep small), Calendar.
- Conformed keys: SKU_ID, Store_ID, Week_Ending. Sentiment + Market join at SKU/Brand + Sub_Category + Geography + Period (coarser grain — handle mapping explicitly).

** Step 4: Build components separately **

  ** Step 4.1: Demand Forecasting (existing + new SKU/store) **
  - Weekly forecast at SKU + Store level.
  - Build the ML feature set first (you already have these columns in ML_Dataset_Final): Units_Last_4W, Sales_Growth_4W, Promo_Frequency, Stockout_Rate, Price_Index, Sentiment_Score/Trend, Market_Growth, Weeks_Since_Launch, Category_Growth.
  - Handle censored demand: when Stockout_Flag=1, model true demand, not observed sales.
  - Hierarchical reconciliation (SKU+Store → Sub_Category → Category) so store forecasts roll up consistently.
  - Code in Backend\Forecasting. Outputs to Output folder.

  
  ** Step 4.2: New SKU Similarity & Cold-Start **
  - Build SKU similarity (cosine over SKU attributes: Sub_Category, Attribute_Claim, Pack_Size, Price_Band, ingredient/benefit flags).
  - Generate new SKU demand from nearest existing analogues, scaled per store.
  - Store-level transfer: new SKU demand must respect store cluster (don't seed a premium SKU's demand into a value store).
  - Code in Backend\NewSKU. Outputs: (1) SKU Similarity Matrix, (2) New SKU demand per store.

  ** Step 4.3: Association & Transference Analysis **
  - Market Basket / ABC analysis: SKU association, lift, halo, cannibalization, delist candidates.
  - Build the Demand Transference Matrix + recapture rate — this is what makes delist decisions safe (how much volume is recaptured vs lost when a SKU is cut).
  - Code in Backend\Association. Output: Transference Matrix, ABC class, lift/halo pairs.

  ** Step 4.4: Sentiment & Market Signals **
  - SKU/Brand sentiment score, NPS-style scale, sentiment trend; map sub-category market growth and our-vs-market fair-share gap.
  - Feeds both forecasting features and SKU Health.

  ** Step 4.5: SKU Health & Decision Scoring **
  - SKU Health Score (sales, margin, velocity, sentiment, inventory efficiency) + ABC/Pareto.
  - Output the Keep / Expand / Replace / Delist decision per SKU+store, each backed by transference recapture and forecast.

  ** Step 4.6: White Space / Opportunity **
  - Fair-share gap + white-space score by attribute/claim to recommend additions (pairs with delist candidates to keep assortment size balanced).

  ** Step 4.7: Assortment Optimization (MILP) **
  - OR-Tools MILP: maximize forecast sales/margin subject to assortment-size, localization, and must-keep constraints; objective uses transference-adjusted demand.
  - Run LAST — only after forecast + transference are trustworthy.
  - Output: optimized assortment per store cluster.

** Step 5: Output & Serving Layer **
- Standardized output contracts (one schema per component) so the app/agents consume them plug-and-play.
- xplainability payload with every recommendation (the "why": drivers, recapture, confidence/error bound).
- Localization by store cluster carried end-to-end (avoid one-size-fits-all assortment).


The four items most worth not skipping: 
the **data quality gate** (step 2), 
**censored-demand handling** (4.1), 
the **transference matrix** (4.3) which is the backbone of safe delisting, and 
**explainability + localization** in the serving layer. Want me to turn any single step into a runnable script grounded in these exact schemas?