"""Reproducible generator for the Retail Sales demo source data.

Produces ``stores.csv``, ``products.csv``, ``pos_transactions.csv`` and
``inventory_snapshots.csv`` with a *physically plausible, learnable* relationship
between observable drivers (price, discount, day-of-week, seasonality, store
format, product category) and the daily demand per store-product, so the
demand-forecasting model trains to a credible R^2 (~0.6-0.8) instead of behaving
like noise on uncorrelated random data.

Signal model (per store-product-day):
  * Each store has a latent traffic level driven by its format (Mall > Street >
    Outlet) + region + a small per-store latent term.
  * Each product has a latent popularity driven by its category + a small
    per-product latent term, and a stable base price tied to category.
  * Daily demand is Poisson(lambda) where ``log(lambda)`` is a linear combo of:
      base + store_traffic + product_popularity
      - price_elasticity * z(unit_price)         (higher price -> less demand)
      + discount_effect * (discount_pct / 100)   (deeper discount -> more demand)
      + weekend_uplift + seasonal_term + small noise
  * Because lambda is stable per (store, product), the 1-day and 7-day demand
    lags are naturally strong predictors (the model learns autocorrelation),
    while price / discount / calendar add independent signal. Poisson noise keeps
    R^2 < 1.

The ML feature-engineering notebook derives the regression target
``daily_quantity`` by summing transaction quantities per store-product-day, and
EXCLUDES same-day leakage columns (``daily_revenue``, ``transaction_count``) from
the model — only lagged demand, price, discount, calendar and dimension
attributes are used as predictors.

Run:  python demos/retail-sales/data/_generate_data.py
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

SEED = 42
N_STORES = 30
N_PRODUCTS = 540
N_DAYS = 90
PRODUCTS_PER_STORE = 40
START_DATE = datetime(2025, 1, 1)

OUT_DIR = Path(__file__).resolve().parent

# ── Dimension vocabularies ──────────────────────────────────────────────────
CITIES = [
    ("San Antonio", "TX", "South"), ("Houston", "TX", "South"),
    ("Dallas", "TX", "South"), ("Phoenix", "AZ", "West"),
    ("Los Angeles", "CA", "West"), ("San Diego", "CA", "West"),
    ("Chicago", "IL", "Midwest"), ("Columbus", "OH", "Midwest"),
    ("New York", "NY", "Northeast"), ("Boston", "MA", "Northeast"),
]
STORE_FORMATS = ["Mall", "Street", "Outlet"]
# Format -> latent traffic offset (Mall busiest, Outlet quietest).
FORMAT_TRAFFIC = {"Mall": 0.45, "Street": 0.10, "Outlet": -0.20}
REGION_TRAFFIC = {"South": 0.05, "West": 0.15, "Midwest": -0.05, "Northeast": 0.20}

# Category -> (subcategories, base price mean, base demand offset).
# High-price categories sell fewer units; grocery-style sell many.
CATEGORIES = {
    "Electronics": (["Phones", "Laptops", "Audio"], 320.0, -0.55),
    "Apparel":     (["Tops", "Bottoms", "Footwear"], 55.0, 0.25),
    "Home":        (["Kitchen", "Decor", "Bedding"], 90.0, 0.05),
    "Grocery":     (["Snacks", "Beverages", "Pantry"], 12.0, 0.85),
    "Toys":        (["Games", "Outdoor", "Educational"], 28.0, 0.10),
}
BRANDS = ["BrandA", "BrandB", "BrandC", "BrandD", "BrandE"]


def main() -> None:
    rng = np.random.default_rng(SEED)

    # ── Stores ──────────────────────────────────────────────────────────────
    stores = []
    for i in range(1, N_STORES + 1):
        city, state, region = CITIES[i % len(CITIES)]
        fmt = STORE_FORMATS[i % len(STORE_FORMATS)]
        stores.append({
            "store_id": f"STR-{i:03d}",
            "store_name": f"Store {city} #{i}",
            "city": city, "state": state, "region": region,
            "store_format": fmt,
            "traffic": (
                FORMAT_TRAFFIC[fmt] + REGION_TRAFFIC[region]
                + float(rng.normal(0, 0.12))
            ),
        })

    with (OUT_DIR / "stores.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["store_id", "store_name", "city", "state", "region", "store_format"])
        for s in stores:
            w.writerow([s["store_id"], s["store_name"], s["city"], s["state"],
                        s["region"], s["store_format"]])
    print(f"Wrote {len(stores)} stores -> stores.csv")

    # ── Products ────────────────────────────────────────────────────────────
    cat_names = list(CATEGORIES.keys())
    products = []
    for i in range(1, N_PRODUCTS + 1):
        cat = cat_names[i % len(cat_names)]
        subs, price_mean, demand_offset = CATEGORIES[cat]
        sub = subs[i % len(subs)]
        brand = BRANDS[i % len(BRANDS)]
        base_price = float(np.clip(rng.normal(price_mean, price_mean * 0.30),
                                   price_mean * 0.4, price_mean * 2.2))
        unit_cost = round(base_price * float(rng.uniform(0.45, 0.7)), 2)
        products.append({
            "sku": f"SKU-{i:04d}",
            "product_name": f"{sub} Item {i}",
            "category": cat, "subcategory": sub, "brand": brand,
            "unit_cost": unit_cost,
            "base_price": round(base_price, 2),
            "demand_offset": demand_offset,
            "popularity": float(rng.normal(0, 0.45)),
        })

    with (OUT_DIR / "products.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku", "product_name", "category", "subcategory", "brand", "unit_cost"])
        for p in products:
            w.writerow([p["sku"], p["product_name"], p["category"],
                        p["subcategory"], p["brand"], p["unit_cost"]])
    print(f"Wrote {len(products)} products -> products.csv")

    # Price normalisation stats for elasticity (z-score of price within category).
    cat_prices: dict[str, list[float]] = {c: [] for c in cat_names}
    for p in products:
        cat_prices[p["category"]].append(p["base_price"])
    cat_price_stats = {
        c: (float(np.mean(v)), float(np.std(v)) or 1.0) for c, v in cat_prices.items()
    }

    # ── Assign a stocked product set to each store ──────────────────────────
    store_products: dict[str, list[dict]] = {}
    for s in stores:
        idx = rng.choice(len(products), size=PRODUCTS_PER_STORE, replace=False)
        store_products[s["store_id"]] = [products[j] for j in idx]

    # ── POS transactions + inventory snapshots ──────────────────────────────
    PRICE_ELASTICITY = 0.45
    DISCOUNT_EFFECT = 1.10
    WEEKEND_UPLIFT = 0.30

    txn_rows = []
    inv_rows = []
    tid = 0
    for s in stores:
        for p in store_products[s["store_id"]]:
            mean_price, std_price = cat_price_stats[p["category"]]
            price_z = (p["base_price"] - mean_price) / std_price
            base_lambda_log = (
                1.05
                + s["traffic"]
                + p["demand_offset"]
                + 0.55 * p["popularity"]
                - PRICE_ELASTICITY * price_z
            )
            on_hand = int(rng.integers(80, 220))
            reorder_point = int(rng.integers(10, 30))
            for d in range(N_DAYS):
                day = START_DATE + timedelta(days=d)
                weekday = day.weekday()
                weekend = WEEKEND_UPLIFT if weekday >= 5 else 0.0
                # Mild yearly seasonality across the 90-day window.
                seasonal = 0.20 * math.sin(2 * math.pi * (day.timetuple().tm_yday / 365.0))
                # Daily promo: ~22% of store-product-days carry a discount.
                if rng.random() < 0.22:
                    discount = float(rng.choice([5, 10, 15, 20, 25]))
                else:
                    discount = 0.0
                day_price = round(p["base_price"] * float(rng.uniform(0.97, 1.03)), 2)

                lam_log = (
                    base_lambda_log
                    + weekend
                    + seasonal
                    + DISCOUNT_EFFECT * (discount / 100.0)
                    + float(rng.normal(0, 0.22))
                )
                lam = math.exp(lam_log)
                qty = int(rng.poisson(lam))
                if qty <= 0:
                    continue

                # Split the day's units across 1-2 POS line items.
                n_txn = 1 if qty <= 3 or rng.random() < 0.6 else 2
                splits = [qty] if n_txn == 1 else [qty - qty // 2, qty // 2]
                for q in splits:
                    if q <= 0:
                        continue
                    tid += 1
                    secs = int(rng.integers(9 * 3600, 21 * 3600))
                    ts = (day + timedelta(seconds=secs)).strftime("%Y-%m-%d %H:%M:%S")
                    txn_rows.append([
                        f"TXN-{tid:07d}", s["store_id"], p["sku"], ts,
                        q, day_price, int(discount),
                    ])

                # Weekly inventory snapshot (Mondays).
                if weekday == 0:
                    on_hand = int(max(0, on_hand - rng.integers(20, 70) + rng.integers(10, 60)))
                    inv_rows.append([
                        day.strftime("%Y-%m-%d"), s["store_id"], p["sku"],
                        on_hand, int(rng.integers(0, 15)), reorder_point,
                    ])

    rng.shuffle(txn_rows)
    with (OUT_DIR / "pos_transactions.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["transaction_id", "store_id", "product_id", "transaction_timestamp",
                    "quantity", "unit_price", "discount_pct"])
        w.writerows(txn_rows)
    print(f"Wrote {len(txn_rows):,} transactions -> pos_transactions.csv")

    with (OUT_DIR / "inventory_snapshots.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["snapshot_date", "store_id", "product_id",
                    "quantity_on_hand", "quantity_on_order", "reorder_point"])
        w.writerows(inv_rows)
    print(f"Wrote {len(inv_rows):,} inventory snapshots -> inventory_snapshots.csv")


if __name__ == "__main__":
    main()
