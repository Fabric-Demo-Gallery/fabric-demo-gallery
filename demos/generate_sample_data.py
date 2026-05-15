"""Generate synthetic sample data for all demos."""

import csv
import random
import os
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

DEMOS_DIR = Path(__file__).parent


def generate_manufacturing_data():
    out_dir = DEMOS_DIR / "manufacturing-qc" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Equipment catalog
    machines = []
    lines = ["Line-A", "Line-B", "Line-C", "Line-D"]
    machine_types = ["CNC Mill", "Injection Molder", "Press", "Laser Cutter", "Assembly Robot"]
    for i in range(1, 51):
        machines.append({
            "machine_id": f"MCH-{i:04d}",
            "machine_name": f"Machine {i}",
            "machine_type": random.choice(machine_types),
            "production_line": random.choice(lines),
            "install_date": (datetime(2020, 1, 1) + timedelta(days=random.randint(0, 1500))).strftime("%Y-%m-%d"),
        })
    _write_csv(out_dir / "equipment_catalog.csv", machines)

    # Sensor readings — 50k rows
    sensors = []
    base_date = datetime(2025, 1, 1)
    for i in range(50000):
        m = random.choice(machines)
        ts = base_date + timedelta(
            days=random.randint(0, 89),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        sensors.append({
            "reading_id": f"R-{i+1:06d}",
            "machine_id": m["machine_id"],
            "production_line": m["production_line"],
            "reading_timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "temperature": round(random.gauss(75, 12), 2),
            "pressure": round(random.gauss(150, 20), 2),
            "vibration": round(random.gauss(3.5, 0.8), 3),
            "humidity": round(random.gauss(45, 8), 1),
        })
    _write_csv(out_dir / "sensor_readings.csv", sensors)

    # Production batches — 2k rows
    products = ["Widget-A", "Widget-B", "Gear-X", "Plate-Y", "Assembly-Z"]
    batches = []
    for i in range(2000):
        day = base_date + timedelta(days=random.randint(0, 89))
        shift_start_hour = random.choice([0, 8, 16])
        start = day.replace(hour=shift_start_hour, minute=0)
        end = start + timedelta(hours=8)
        planned = random.randint(200, 1000)
        produced = max(0, planned - random.randint(0, 100))
        defects = random.randint(0, max(1, produced // 20))
        batches.append({
            "batch_id": f"B-{i+1:05d}",
            "production_line": random.choice(lines),
            "product": random.choice(products),
            "batch_start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "batch_end": end.strftime("%Y-%m-%d %H:%M:%S"),
            "planned_units": planned,
            "units_produced": produced,
            "defect_count": defects,
            "downtime_minutes": round(random.uniform(0, 60), 1),
        })
    _write_csv(out_dir / "production_batches.csv", batches)
    print(f"Manufacturing data generated: {len(sensors)} sensor readings, {len(batches)} batches, {len(machines)} machines")


def generate_retail_data():
    out_dir = DEMOS_DIR / "retail-sales" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Stores
    cities = [
        ("New York", "NY", "Northeast"), ("Los Angeles", "CA", "West"),
        ("Chicago", "IL", "Midwest"), ("Houston", "TX", "South"),
        ("Phoenix", "AZ", "West"), ("Philadelphia", "PA", "Northeast"),
        ("San Antonio", "TX", "South"), ("San Diego", "CA", "West"),
        ("Dallas", "TX", "South"), ("Seattle", "WA", "West"),
    ]
    formats = ["Mall", "Street", "Outlet"]
    stores = []
    for i in range(1, 31):
        city, state, region = random.choice(cities)
        stores.append({
            "store_id": f"STR-{i:03d}",
            "store_name": f"Store {city} #{i}",
            "city": city,
            "state": state,
            "region": region,
            "store_format": random.choice(formats),
        })
    _write_csv(out_dir / "stores.csv", stores)

    # Products
    categories = {
        "Electronics": ["Phones", "Tablets", "Accessories", "Audio"],
        "Clothing": ["Men", "Women", "Kids", "Sportswear"],
        "Home": ["Kitchen", "Furniture", "Decor", "Garden"],
        "Food": ["Snacks", "Beverages", "Dairy", "Bakery"],
    }
    brands = ["BrandA", "BrandB", "BrandC", "BrandD", "BrandE"]
    products = []
    sku_counter = 1
    for cat, subcats in categories.items():
        for sub in subcats:
            for _ in range(random.randint(25, 40)):
                sku = f"SKU-{sku_counter:04d}"
                products.append({
                    "sku": sku,
                    "product_name": f"{sub} Item {sku_counter}",
                    "category": cat,
                    "subcategory": sub,
                    "brand": random.choice(brands),
                    "unit_cost": round(random.uniform(2, 200), 2),
                })
                sku_counter += 1
    _write_csv(out_dir / "products.csv", products)

    # POS transactions — 100k line items
    base_date = datetime(2025, 1, 1)
    txn_counter = 1
    transactions = []
    while len(transactions) < 100000:
        txn_id = f"TXN-{txn_counter:07d}"
        store = random.choice(stores)
        ts = base_date + timedelta(
            days=random.randint(0, 89),
            hours=random.randint(8, 21),
            minutes=random.randint(0, 59),
        )
        basket_size = random.randint(1, 8)
        basket_products = random.sample(products, min(basket_size, len(products)))
        for p in basket_products:
            markup = random.uniform(1.3, 3.0)
            transactions.append({
                "transaction_id": txn_id,
                "store_id": store["store_id"],
                "product_id": p["sku"],
                "transaction_timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "quantity": random.randint(1, 5),
                "unit_price": round(p["unit_cost"] * markup, 2),
                "discount_pct": random.choice([0, 0, 0, 5, 10, 15, 20]),
            })
        txn_counter += 1
    transactions = transactions[:100000]
    _write_csv(out_dir / "pos_transactions.csv", transactions)

    # Inventory snapshots — 15k rows
    inventory = []
    for day_offset in range(0, 90, 6):  # every 6 days
        snap_date = (base_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        for store in stores:
            for p in random.sample(products, min(35, len(products))):
                inventory.append({
                    "snapshot_date": snap_date,
                    "store_id": store["store_id"],
                    "product_id": p["sku"],
                    "quantity_on_hand": random.randint(0, 200),
                    "quantity_on_order": random.randint(0, 50),
                    "reorder_point": random.randint(10, 30),
                })
    _write_csv(out_dir / "inventory_snapshots.csv", inventory)
    print(f"Retail data generated: {len(transactions)} transactions, {len(products)} products, {len(stores)} stores, {len(inventory)} inventory snapshots")


def _write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def generate_energy_data():
    out_dir = DEMOS_DIR / "energy-grid" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    substations = [f"SUB-{i:03d}" for i in range(1, 26)]
    regions = ["North", "South", "East", "West", "Central"]
    sub_region = {s: random.choice(regions) for s in substations}
    base_date = datetime(2025, 3, 1)

    # Grid sensor readings — 100k rows
    sensors = []
    for i in range(100000):
        sub = random.choice(substations)
        ts = base_date + timedelta(
            days=random.randint(0, 59),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59),
        )
        hour = ts.hour
        # Voltage: ~230V nominal, slight dip during peak hours
        base_v = 230.0 if random.random() > 0.02 else random.choice([210, 245, 250])
        voltage = round(random.gauss(base_v - (2 if 17 <= hour <= 21 else 0), 3.5), 2)
        # Frequency: ~50Hz nominal
        freq = round(random.gauss(50.0, 0.05), 3)
        # Load varies by time of day
        base_load = 15 + 10 * (1 if 8 <= hour <= 20 else 0) + 5 * (1 if 17 <= hour <= 21 else 0)
        sensors.append({
            "reading_id": f"GS-{i+1:07d}",
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "substation_id": sub,
            "region": sub_region[sub],
            "voltage_v": voltage,
            "frequency_hz": freq,
            "power_factor": round(random.uniform(0.85, 0.99), 3),
            "load_mw": round(random.gauss(base_load, 4), 2),
            "temperature_c": round(random.gauss(35 + 10 * (1 if 10 <= hour <= 16 else 0), 5), 1),
        })
    _write_csv(out_dir / "grid_sensors.csv", sensors)

    # Power events — 5k rows
    event_types = ["outage", "surge", "voltage_sag", "restoration", "equipment_fault", "overload"]
    severities = ["low", "medium", "high", "critical"]
    events = []
    for i in range(5000):
        sub = random.choice(substations)
        etype = random.choice(event_types)
        ts = base_date + timedelta(
            days=random.randint(0, 59),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        dur = random.randint(1, 7200) if etype in ("outage", "equipment_fault") else random.randint(1, 300)
        affected = random.randint(0, 5000) if etype == "outage" else random.randint(0, 500)
        events.append({
            "event_id": f"EVT-{i+1:06d}",
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "substation_id": sub,
            "region": sub_region[sub],
            "event_type": etype,
            "severity": random.choice(severities),
            "duration_sec": dur,
            "affected_customers": affected,
            "resolved": random.choice(["true", "false"]) if etype != "restoration" else "true",
        })
    _write_csv(out_dir / "power_events.csv", events)

    # Renewable generation — 20k rows
    plants = []
    plant_types = ["solar", "wind", "hydro"]
    for pt in plant_types:
        count = {"solar": 8, "wind": 6, "hydro": 3}[pt]
        for j in range(1, count + 1):
            cap = {"solar": random.uniform(20, 80), "wind": random.uniform(30, 120), "hydro": random.uniform(50, 200)}[pt]
            plants.append({"plant_id": f"{pt.upper()}-{j:02d}", "plant_type": pt, "capacity_mw": round(cap, 1)})

    weather_conditions = ["clear", "cloudy", "overcast", "rainy", "windy", "stormy"]
    gen_rows = []
    for i in range(20000):
        plant = random.choice(plants)
        ts = base_date + timedelta(
            days=random.randint(0, 59),
            hours=random.randint(0, 23),
            minutes=random.choice([0, 15, 30, 45]),
        )
        weather = random.choice(weather_conditions)
        hour = ts.hour
        # Generation depends on plant type, hour, and weather
        if plant["plant_type"] == "solar":
            factor = max(0, (1 - abs(hour - 12) / 8)) * (0.3 if weather in ("cloudy", "overcast", "rainy") else 0.9)
        elif plant["plant_type"] == "wind":
            factor = random.uniform(0.2, 0.8) * (1.3 if weather in ("windy", "stormy") else 0.7)
        else:  # hydro
            factor = random.uniform(0.5, 0.95)
        gen = round(plant["capacity_mw"] * factor * random.uniform(0.8, 1.1), 2)
        gen_rows.append({
            "reading_id": f"RG-{i+1:06d}",
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "plant_id": plant["plant_id"],
            "plant_type": plant["plant_type"],
            "generation_mw": max(0, gen),
            "capacity_mw": plant["capacity_mw"],
            "capacity_factor": round(max(0, gen) / plant["capacity_mw"], 3),
            "weather": weather,
        })
    _write_csv(out_dir / "renewable_generation.csv", gen_rows)
    print(f"Energy data generated: {len(sensors)} sensor readings, {len(events)} events, {len(gen_rows)} renewable readings")


if __name__ == "__main__":
    generate_manufacturing_data()
    generate_retail_data()
    generate_energy_data()
