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


def generate_healthcare_data():
    out_dir = DEMOS_DIR / "healthcare" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    departments   = ["Cardiology", "Orthopaedics", "Oncology", "Neurology", "General Medicine", "Emergency", "Paediatrics"]
    admission_types = ["Emergency", "Elective", "Transfer", "Outpatient"]
    insurance_types = ["NHS", "Private", "International"]
    age_groups    = ["0-17", "18-34", "35-54", "55-74", "75+"]
    roles         = ["Doctor", "Nurse", "Consultant", "Technician", "Physiotherapist"]
    shifts        = ["Morning", "Afternoon", "Night"]
    vital_types   = ["Heart Rate", "Blood Pressure Systolic", "Temperature", "O2 Saturation"]
    dx_codes      = [f"I{i:02d}" for i in range(10, 30)] + [f"M{i:02d}" for i in range(10, 25)]

    # staff_catalog — 200 rows
    staff = []
    for i in range(1, 201):
        dept = random.choice(departments)
        staff.append({
            "staff_id":   f"ST-{i:04d}",
            "role":       random.choice(roles),
            "department": dept,
            "shift":      random.choice(shifts),
            "hire_date":  (datetime(2015, 1, 1) + timedelta(days=random.randint(0, 3000))).strftime("%Y-%m-%d"),
        })
    _write_csv(out_dir / "staff_catalog.csv", staff)

    # patient_admissions — 20 000 rows
    admissions = []
    base = datetime(2025, 1, 1)
    for i in range(1, 20001):
        adm_date = base + timedelta(days=random.randint(0, 89), hours=random.randint(0, 23))
        los = random.randint(1, 21)
        dis_date = adm_date + timedelta(days=los)
        dept = random.choice(departments)
        admissions.append({
            "patient_id":        f"P-{random.randint(1, 8000):05d}",
            "admission_id":      f"ADM-{i:06d}",
            "department":        dept,
            "admission_type":    random.choice(admission_types),
            "admission_date":    adm_date.strftime("%Y-%m-%d %H:%M:%S"),
            "discharge_date":    dis_date.strftime("%Y-%m-%d %H:%M:%S"),
            "length_of_stay_days": los,
            "primary_dx_code":   random.choice(dx_codes),
            "insurance_type":    random.choice(insurance_types),
            "is_readmission":    random.random() < 0.12,
            "age_group":         random.choice(age_groups),
            "assigned_staff_id": random.choice(staff)["staff_id"],
        })
    _write_csv(out_dir / "patient_admissions.csv", admissions)

    # clinical_records — 80 000 rows (4 vitals per admission on average)
    records = []
    for i in range(1, 80001):
        adm = random.choice(admissions)
        vt = random.choice(vital_types)
        if vt == "Heart Rate":
            val = round(random.gauss(78, 14), 1)
        elif vt == "Blood Pressure Systolic":
            val = round(random.gauss(125, 18), 1)
        elif vt == "Temperature":
            val = round(random.gauss(37.0, 0.6), 2)
        else:
            val = round(random.gauss(96, 2.5), 1)
        ts = datetime.strptime(adm["admission_date"], "%Y-%m-%d %H:%M:%S") + timedelta(hours=random.randint(0, 72))
        records.append({
            "record_id":    f"REC-{i:07d}",
            "admission_id": adm["admission_id"],
            "patient_id":   adm["patient_id"],
            "department":   adm["department"],
            "recorded_at":  ts.strftime("%Y-%m-%d %H:%M:%S"),
            "vital_type":   vt,
            "value":        val,
            "recorded_by":  random.choice(staff)["staff_id"],
        })
    _write_csv(out_dir / "clinical_records.csv", records)
    print(f"Healthcare data generated: {len(admissions)} admissions, {len(records)} clinical records, {len(staff)} staff")


def generate_financial_services_data():
    out_dir = DEMOS_DIR / "financial-services" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    segments     = ["Retail", "SME", "Corporate", "Private Banking"]
    regions      = ["London", "South East", "North West", "Midlands", "Scotland", "Wales"]
    risk_tiers   = ["Low", "Medium", "High", "Very High"]
    account_types = ["Current", "Savings", "Credit Card", "Mortgage", "Business Current"]
    tx_types     = ["Purchase", "Transfer", "ATM Withdrawal", "Online Payment", "Direct Debit"]
    categories   = ["Retail", "Groceries", "Travel", "Hospitality", "Technology", "Healthcare", "Education", "Utilities"]
    channels     = ["Online", "Mobile", "Branch", "ATM", "POS"]
    countries    = ["UK"] * 7 + ["US", "FR", "DE", "ES", "AE", "SG", "AU"]

    # customers — 2 000 rows
    customers = []
    for i in range(1, 2001):
        customers.append({
            "customer_id": f"C-{i:05d}",
            "age_group":   random.choice(["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]),
            "segment":     random.choice(segments),
            "region":      random.choice(regions),
            "risk_tier":   random.choice(risk_tiers),
            "since_year":  random.randint(2000, 2024),
        })
    _write_csv(out_dir / "customers.csv", customers)

    # accounts — 5 000 rows
    accounts = []
    for i in range(1, 5001):
        cust = random.choice(customers)
        balance = round(random.uniform(100, 50000), 2)
        limit   = round(random.choice([0, 2000, 5000, 10000, 25000]), 2)
        util    = round(random.uniform(0, 100), 2) if limit > 0 else 0.0
        accounts.append({
            "account_id":             f"A-{i:06d}",
            "customer_id":            cust["customer_id"],
            "account_type":           random.choice(account_types),
            "balance":                balance,
            "credit_limit":           limit,
            "credit_utilisation_pct": util,
            "open_date":              (datetime(2005, 1, 1) + timedelta(days=random.randint(0, 7000))).strftime("%Y-%m-%d"),
            "status":                 random.choices(["Active", "Dormant", "Closed"], weights=[80, 15, 5])[0],
        })
    _write_csv(out_dir / "accounts.csv", accounts)

    # transactions — 100 000 rows
    transactions = []
    base = datetime(2025, 1, 1)
    for i in range(1, 100001):
        acct = random.choice(accounts)
        cust_ids = {a["account_id"]: a["customer_id"] for a in accounts}
        ts = base + timedelta(days=random.randint(0, 89), hours=random.randint(0, 23), minutes=random.randint(0, 59))
        is_fraud = random.random() < 0.025
        transactions.append({
            "transaction_id":   f"T-{i:08d}",
            "account_id":       acct["account_id"],
            "customer_id":      cust_ids[acct["account_id"]],
            "transaction_date": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "transaction_type": random.choice(tx_types),
            "merchant_category": random.choice(categories),
            "amount":           round(random.lognormvariate(4.5, 1.5), 2),
            "is_flagged_fraud": is_fraud,
            "channel":          random.choice(channels),
            "country":          random.choice(countries),
        })
    _write_csv(out_dir / "transactions.csv", transactions)
    print(f"Financial-services data generated: {len(customers)} customers, {len(accounts)} accounts, {len(transactions)} transactions")


def generate_hospitality_data():
    out_dir = DEMOS_DIR / "hospitality" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Properties — 50 hotels
    cities = [
        ("New York", "US"), ("London", "UK"), ("Paris", "FR"), ("Dubai", "AE"),
        ("Singapore", "SG"), ("Tokyo", "JP"), ("Sydney", "AU"), ("Barcelona", "ES"),
        ("Miami", "US"), ("Las Vegas", "US"),
    ]
    property_types = ["Hotel", "Resort", "Boutique", "Airport", "Business"]
    properties = []
    for i in range(1, 51):
        city, country = random.choice(cities)
        prop_type = random.choice(property_types)
        star = random.choices([3, 4, 5], weights=[20, 50, 30])[0]
        rooms = random.choice([80, 120, 150, 200, 250, 350, 500])
        properties.append({
            "property_id": f"PROP-{i:03d}",
            "property_name": f"{city} {prop_type} {i}",
            "city": city,
            "country": country,
            "property_type": prop_type,
            "star_rating": star,
            "room_count": rooms,
        })
    _write_csv(out_dir / "properties.csv", properties)

    # Guests — 5 000
    loyalty_tiers = ["Bronze", "Silver", "Gold", "Platinum"]
    regions = ["North America", "Europe", "Asia Pacific", "Middle East", "Latin America"]
    age_groups = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
    channels = ["Direct", "OTA", "Corporate", "Group"]
    guests = []
    for i in range(1, 5001):
        total_stays = random.randint(1, 50)
        tier_idx = min(3, total_stays // 10)
        guests.append({
            "guest_id": f"GST-{i:05d}",
            "loyalty_tier": loyalty_tiers[tier_idx],
            "region": random.choice(regions),
            "age_group": random.choice(age_groups),
            "nationality": random.choice(["US", "UK", "DE", "FR", "JP", "AU", "AE", "SG", "CA", "CN"]),
            "total_stays": total_stays,
            "total_spend": round(total_stays * random.uniform(150, 800), 2),
            "preferred_channel": random.choice(channels),
            "signup_date": (datetime(2018, 1, 1) + timedelta(days=random.randint(0, 2000))).strftime("%Y-%m-%d"),
        })
    _write_csv(out_dir / "guests.csv", guests)

    # Bookings — 50 000
    room_types = ["Standard", "Deluxe", "Suite", "Junior Suite", "Executive"]
    meal_plans = ["Room Only", "Bed & Breakfast", "Half Board", "Full Board"]
    statuses = ["completed", "completed", "completed", "completed", "cancelled", "no_show"]
    base_date = datetime(2025, 1, 1)
    bookings = []
    for i in range(1, 50001):
        prop = random.choice(properties)
        guest = random.choice(guests)
        nights = random.choices([1, 2, 3, 4, 5, 7, 10, 14], weights=[20, 25, 20, 10, 8, 8, 5, 4])[0]
        check_in = base_date + timedelta(days=random.randint(0, 89))
        check_out = check_in + timedelta(days=nights)
        rate = prop["star_rating"] * random.uniform(40, 80) + random.uniform(-20, 60)
        rate = round(max(50, rate), 2)
        status = random.choice(statuses)
        total = round(rate * nights, 2) if status == "completed" else 0.0
        bookings.append({
            "booking_id": f"BK-{i:07d}",
            "property_id": prop["property_id"],
            "guest_id": guest["guest_id"],
            "check_in_date": check_in.strftime("%Y-%m-%d"),
            "check_out_date": check_out.strftime("%Y-%m-%d"),
            "nights": nights,
            "room_type": random.choice(room_types),
            "channel": random.choice(channels),
            "meal_plan": random.choice(meal_plans),
            "room_rate": rate,
            "total_amount": total,
            "status": status,
            "is_repeat_guest": 1 if guest["total_stays"] > 1 else 0,
        })
    _write_csv(out_dir / "bookings.csv", bookings)

    # Reviews — 20 000
    sentiments = ["Positive", "Positive", "Positive", "Neutral", "Negative"]
    platforms = ["TripAdvisor", "Google", "Booking.com", "Expedia", "Direct"]
    completed_bookings = [b for b in bookings if b["status"] == "completed"]
    reviews = []
    review_sample = random.sample(completed_bookings, min(20000, len(completed_bookings)))
    for i, bk in enumerate(review_sample):
        sentiment = random.choice(sentiments)
        base_score = {"Positive": 8, "Neutral": 6, "Negative": 4}[sentiment]
        reviews.append({
            "review_id": f"REV-{i+1:06d}",
            "booking_id": bk["booking_id"],
            "property_id": bk["property_id"],
            "guest_id": bk["guest_id"],
            "review_date": (datetime.strptime(bk["check_out_date"], "%Y-%m-%d") + timedelta(days=random.randint(1, 14))).strftime("%Y-%m-%d"),
            "overall_score": min(10, max(1, base_score + random.randint(-2, 2))),
            "cleanliness_score": min(10, max(1, base_score + random.randint(-1, 2))),
            "service_score": min(10, max(1, base_score + random.randint(-2, 2))),
            "value_score": min(10, max(1, base_score + random.randint(-2, 1))),
            "food_score": min(10, max(1, base_score + random.randint(-2, 2))),
            "sentiment": sentiment,
            "platform": random.choice(platforms),
        })
    _write_csv(out_dir / "reviews.csv", reviews)
    print(f"Hospitality data generated: {len(bookings)} bookings, {len(guests)} guests, {len(properties)} properties, {len(reviews)} reviews")


def generate_media_data():
    out_dir = DEMOS_DIR / "media" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Content catalog — 2 000
    genres = ["Drama", "Comedy", "Action", "Thriller", "Documentary", "Romance", "Sci-Fi", "Sports", "Kids", "News"]
    content_types = ["Movie", "Series", "Live", "Documentary"]
    languages = ["English", "Spanish", "French", "German", "Japanese", "Korean"]
    cost_buckets = ["Low (<$1M)", "Medium ($1M-$10M)", "High ($10M-$50M)", "Blockbuster (>$50M)"]
    content = []
    for i in range(1, 2001):
        ctype = random.choice(content_types)
        content.append({
            "content_id": f"CNT-{i:05d}",
            "title": f"{random.choice(genres)} {ctype} {i}",
            "genre": random.choice(genres),
            "content_type": ctype,
            "release_year": random.randint(2018, 2025),
            "duration_mins": random.randint(20, 180) if ctype != "Series" else random.randint(20, 60),
            "production_cost_bucket": random.choices(cost_buckets, weights=[40, 35, 15, 10])[0],
            "language": random.choice(languages),
        })
    _write_csv(out_dir / "content_catalog.csv", content)

    # Subscribers — 10 000
    plans = ["Basic", "Standard", "Premium"]
    plan_fees = {"Basic": 7.99, "Standard": 13.99, "Premium": 19.99}
    regions = ["North America", "Europe", "Asia Pacific", "Latin America", "Middle East"]
    age_groups = ["18-24", "25-34", "35-44", "45-54", "55+"]
    payment_methods = ["Credit Card", "Debit Card", "PayPal", "Apple Pay", "Google Pay"]
    subscribers = []
    churn_date_map = {}
    base_date = datetime(2025, 1, 1)
    for i in range(1, 10001):
        plan = random.choices(plans, weights=[30, 45, 25])[0]
        signup = datetime(2022, 1, 1) + timedelta(days=random.randint(0, 1095))
        is_churned = random.random() < 0.15  # 15% churn
        churn_date = None
        if is_churned:
            churn_date = (signup + timedelta(days=random.randint(30, 730))).strftime("%Y-%m-%d")
        sub_id = f"SUB-{i:06d}"
        churn_date_map[sub_id] = churn_date
        subscribers.append({
            "subscriber_id": sub_id,
            "plan_type": plan,
            "region": random.choice(regions),
            "age_group": random.choice(age_groups),
            "payment_method": random.choice(payment_methods),
            "monthly_fee": plan_fees[plan],
            "signup_date": signup.strftime("%Y-%m-%d"),
            "churn_date": churn_date if churn_date else "",
            "is_churned": 1 if is_churned else 0,
        })
    _write_csv(out_dir / "subscribers.csv", subscribers)

    # Viewing history — 200 000
    device_types = ["TV", "Mobile", "Tablet", "Web", "Gaming Console"]
    active_subs = [s for s in subscribers if not s["is_churned"]]
    views = []
    for i in range(200000):
        sub = random.choice(active_subs)
        item = random.choice(content)
        view_date = base_date + timedelta(days=random.randint(0, 89))
        max_watch = item["duration_mins"]
        watch_mins = round(random.uniform(1, max_watch), 1)
        is_completed = 1 if watch_mins >= max_watch * 0.85 else 0
        rating = random.choices([None, 1, 2, 3, 4, 5], weights=[60, 2, 3, 10, 20, 5])[0]
        views.append({
            "view_id": f"VW-{i+1:08d}",
            "subscriber_id": sub["subscriber_id"],
            "content_id": item["content_id"],
            "view_date": view_date.strftime("%Y-%m-%d"),
            "watch_duration_mins": watch_mins,
            "is_completed": is_completed,
            "device_type": random.choice(device_types),
            "rating": rating if rating else "",
        })
    _write_csv(out_dir / "viewing_history.csv", views)

    # Ad impressions — 100 000
    ad_types = ["Pre-roll", "Mid-roll", "Display", "Sponsored"]
    ad_rows = []
    for i in range(100000):
        item = random.choice(content)
        ad_date = base_date + timedelta(days=random.randint(0, 89))
        ad_type = random.choice(ad_types)
        imps = random.randint(100, 10000)
        ctr = random.uniform(0.005, 0.05)
        clicks = int(imps * ctr)
        cpm = round(random.uniform(3.0, 15.0), 2)
        revenue = round(imps * cpm / 1000, 4)
        ad_rows.append({
            "impression_id": f"AD-{i+1:08d}",
            "content_id": item["content_id"],
            "ad_date": ad_date.strftime("%Y-%m-%d"),
            "ad_type": ad_type,
            "impressions": imps,
            "clicks": clicks,
            "revenue_usd": revenue,
            "cpm": cpm,
        })
    _write_csv(out_dir / "ad_impressions.csv", ad_rows)
    print(f"Media data generated: {len(subscribers)} subscribers, {len(content)} content items, {len(views)} views, {len(ad_rows)} ad impressions")


def generate_construction_data():
    out_dir = DEMOS_DIR / "construction" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    regions = ["London", "South East", "North West", "Midlands", "Scotland", "Wales", "South West"]
    project_types = ["Residential", "Commercial", "Infrastructure", "Industrial", "Renovation"]
    statuses = ["Planning", "In Progress", "Completed", "On Hold", "Cancelled"]
    trades = ["Civil Engineering", "Structural Steel", "MEP", "Roofing", "Glazing",
              "Groundworks", "Fit-Out", "Landscaping", "Electrical", "Plumbing"]

    # subcontractors — 100 rows
    subcontractors = []
    for i in range(1, 101):
        subcontractors.append({
            "subcontractor_id": f"SUB-{i:04d}",
            "company_name": f"Sub-Contractor {i} Ltd",
            "trade": random.choice(trades),
            "region": random.choice(regions),
            "rating": round(random.uniform(2.5, 5.0), 1),
            "years_active": random.randint(1, 30),
            "accredited": random.choice(["Y", "N"]),
        })
    _write_csv(out_dir / "subcontractors.csv", subcontractors)

    # projects — 200 rows
    base_date = datetime(2024, 1, 1)
    projects = []
    for i in range(1, 201):
        planned_start = base_date + timedelta(days=random.randint(0, 365))
        planned_dur = random.randint(90, 730)
        planned_end = planned_start + timedelta(days=planned_dur)
        slip_days = random.randint(-10, 120)
        actual_start = planned_start + timedelta(days=random.randint(-5, 30))
        status = random.choice(statuses)
        budget = round(random.uniform(500_000, 50_000_000), 2)
        cost_var_pct = round(random.uniform(-5, 30), 2)
        projects.append({
            "project_id": f"PRJ-{i:04d}",
            "project_name": f"Project {i} - {random.choice(project_types)}",
            "project_type": random.choice(project_types),
            "region": random.choice(regions),
            "status": status,
            "budget": budget,
            "planned_start_date": planned_start.strftime("%Y-%m-%d"),
            "planned_end_date": planned_end.strftime("%Y-%m-%d"),
            "actual_start_date": actual_start.strftime("%Y-%m-%d"),
            "forecast_end_date": (planned_end + timedelta(days=slip_days)).strftime("%Y-%m-%d"),
            "schedule_variance_days": slip_days,
            "cost_variance_pct": cost_var_pct,
            "lead_subcontractor_id": random.choice(subcontractors)["subcontractor_id"],
        })
    _write_csv(out_dir / "projects.csv", projects)

    # tasks — 10 000 rows
    task_names = ["Site Preparation", "Foundation", "Framing", "Roofing", "MEP Rough-In",
                  "Insulation", "Drywall", "Electrical Fit-Out", "Plumbing Fit-Out",
                  "Finishing", "Inspection", "Commissioning", "Handover"]
    task_statuses = ["Not Started", "In Progress", "Completed", "Delayed", "Blocked"]
    tasks = []
    for i in range(1, 10001):
        prj = random.choice(projects)
        planned_start = datetime.strptime(prj["planned_start_date"], "%Y-%m-%d") + timedelta(days=random.randint(0, 200))
        dur = random.randint(3, 60)
        planned_end = planned_start + timedelta(days=dur)
        slip = random.randint(-2, 30)
        pct = round(random.uniform(0, 100), 1)
        tasks.append({
            "task_id": f"TSK-{i:06d}",
            "project_id": prj["project_id"],
            "task_name": random.choice(task_names),
            "assigned_subcontractor_id": random.choice(subcontractors)["subcontractor_id"],
            "planned_start_date": planned_start.strftime("%Y-%m-%d"),
            "planned_end_date": planned_end.strftime("%Y-%m-%d"),
            "actual_start_date": (planned_start + timedelta(days=random.randint(0, 5))).strftime("%Y-%m-%d"),
            "forecast_end_date": (planned_end + timedelta(days=slip)).strftime("%Y-%m-%d"),
            "schedule_variance_days": slip,
            "status": random.choice(task_statuses),
            "pct_complete": pct,
        })
    _write_csv(out_dir / "tasks.csv", tasks)

    # cost_ledger — 50 000 rows
    cost_categories = ["Labour", "Materials", "Equipment", "Subcontractor", "Overheads", "Permits & Fees"]
    cost_rows = []
    for i in range(1, 50001):
        prj = random.choice(projects)
        planned = round(random.uniform(1_000, 500_000), 2)
        variance_pct = round(random.uniform(-10, 40), 2)
        actual = round(planned * (1 + variance_pct / 100), 2)
        entry_date = datetime.strptime(prj["actual_start_date"], "%Y-%m-%d") + timedelta(days=random.randint(0, 300))
        cost_rows.append({
            "cost_id": f"CST-{i:07d}",
            "project_id": prj["project_id"],
            "entry_date": entry_date.strftime("%Y-%m-%d"),
            "cost_category": random.choice(cost_categories),
            "supplier": f"Supplier-{random.randint(1, 200):03d}",
            "planned_cost": planned,
            "actual_cost": actual,
            "cost_variance": round(actual - planned, 2),
            "cost_variance_pct": variance_pct,
            "approved": random.choice(["Y", "Y", "Y", "N"]),
        })
    _write_csv(out_dir / "cost_ledger.csv", cost_rows)
    print(f"Construction data generated: {len(projects)} projects, {len(tasks)} tasks, {len(cost_rows)} cost entries, {len(subcontractors)} subcontractors")


def generate_education_data():
    out_dir = DEMOS_DIR / "education" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    programmes = ["Computer Science", "Business Administration", "Engineering", "Medicine",
                  "Arts & Humanities", "Law", "Education", "Social Sciences"]
    departments = ["Computing", "Business", "Engineering", "Medical School",
                   "Arts", "Law School", "Education Dept", "Social Sciences"]
    prog_dept = dict(zip(programmes, departments))
    course_levels = ["Undergraduate", "Postgraduate", "PhD"]
    genders = ["Male", "Female", "Non-binary", "Prefer not to say"]
    regions = ["London", "South East", "North West", "Midlands", "Scotland", "Wales", "International"]
    statuses = ["Active", "Graduated", "Withdrawn", "Deferred"]
    enrol_statuses = ["Enrolled", "Completed", "Withdrawn", "Failed"]
    assessment_types = ["Exam", "Coursework", "Dissertation", "Lab Report", "Presentation", "Group Project"]
    faculty_roles = ["Professor", "Associate Professor", "Lecturer", "Senior Lecturer", "Research Fellow"]

    # faculty — 200 rows
    faculty = []
    for i in range(1, 201):
        dept = random.choice(departments)
        faculty.append({
            "faculty_id": f"FAC-{i:04d}",
            "department": dept,
            "role": random.choice(faculty_roles),
            "years_at_institution": random.randint(1, 35),
            "courses_assigned": random.randint(1, 6),
            "research_active": random.choice(["Y", "Y", "N"]),
            "hire_date": (datetime(2000, 1, 1) + timedelta(days=random.randint(0, 9000))).strftime("%Y-%m-%d"),
        })
    _write_csv(out_dir / "faculty.csv", faculty)

    # students — 5 000 rows
    base_date = datetime(2022, 9, 1)
    students = []
    for i in range(1, 5001):
        prog = random.choice(programmes)
        cohort_year = random.choice([2022, 2023, 2024, 2025])
        enrol_date = datetime(cohort_year, 9, 1) + timedelta(days=random.randint(0, 14))
        students.append({
            "student_id": f"STU-{i:05d}",
            "programme": prog,
            "department": prog_dept[prog],
            "level": random.choice(course_levels),
            "cohort_year": cohort_year,
            "enrolment_date": enrol_date.strftime("%Y-%m-%d"),
            "status": random.choices(statuses, weights=[70, 20, 7, 3])[0],
            "gender": random.choice(genders),
            "region": random.choice(regions),
            "age_at_enrolment": random.randint(18, 45),
        })
    _write_csv(out_dir / "students.csv", students)

    # courses pool
    course_pool = []
    cid = 1
    for dept in departments:
        for lvl in course_levels:
            for j in range(1, 6):
                fac = random.choice([f["faculty_id"] for f in faculty if f["department"] == dept] or [faculty[0]["faculty_id"]])
                course_pool.append({
                    "course_id": f"CRS-{cid:04d}",
                    "course_name": f"{dept} {lvl} Module {j}",
                    "department": dept,
                    "level": lvl,
                    "credits": random.choice([10, 15, 20, 30]),
                    "lead_faculty_id": fac,
                })
                cid += 1

    # enrolments — 20 000 rows
    enrolments = []
    for i in range(1, 20001):
        stu = random.choice(students)
        dept_courses = [c for c in course_pool if c["department"] == prog_dept[stu["programme"]]]
        course = random.choice(dept_courses if dept_courses else course_pool)
        enrol_date = datetime.strptime(stu["enrolment_date"], "%Y-%m-%d") + timedelta(days=random.randint(0, 30))
        est = random.choices(enrol_statuses, weights=[30, 50, 10, 10])[0]
        enrolments.append({
            "enrolment_id": f"ENR-{i:06d}",
            "student_id": stu["student_id"],
            "course_id": course["course_id"],
            "department": course["department"],
            "level": course["level"],
            "credits": course["credits"],
            "enrolment_date": enrol_date.strftime("%Y-%m-%d"),
            "status": est,
            "is_completed": 1 if est == "Completed" else 0,
            "is_withdrawn": 1 if est == "Withdrawn" else 0,
        })
    _write_csv(out_dir / "enrolments.csv", enrolments)

    # assessments — 80 000 rows
    grade_bands = ["A", "B", "C", "D", "F"]
    assessments = []
    for i in range(1, 80001):
        enr = random.choice(enrolments)
        score = round(random.gauss(62, 16), 1)
        score = max(0, min(100, score))
        grade = "A" if score >= 70 else "B" if score >= 60 else "C" if score >= 50 else "D" if score >= 40 else "F"
        submitted_date = datetime.strptime(enr["enrolment_date"], "%Y-%m-%d") + timedelta(days=random.randint(30, 200))
        assessments.append({
            "assessment_id": f"ASM-{i:07d}",
            "enrolment_id": enr["enrolment_id"],
            "student_id": enr["student_id"],
            "course_id": enr["course_id"],
            "department": enr["department"],
            "assessment_type": random.choice(assessment_types),
            "attempt_number": random.choices([1, 2, 3], weights=[80, 15, 5])[0],
            "submitted_date": submitted_date.strftime("%Y-%m-%d"),
            "score": score,
            "grade": grade,
            "is_pass": 1 if score >= 40 else 0,
            "word_count": random.randint(500, 5000) if random.random() > 0.4 else None,
        })
    _write_csv(out_dir / "assessments.csv", assessments)
    print(f"Education data generated: {len(students)} students, {len(enrolments)} enrolments, {len(assessments)} assessments, {len(faculty)} faculty")


def generate_transportation_data():
    out_dir = DEMOS_DIR / "transportation" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    random.seed(42)

    vehicle_types = ["HGV", "Van", "Refrigerated", "Flatbed", "Tanker"]
    depots = ["London", "Birmingham", "Manchester", "Leeds", "Glasgow", "Bristol", "Liverpool", "Sheffield"]
    statuses = ["Active", "Active", "Active", "Maintenance", "Decommissioned"]

    # Vehicles — 100
    vehicles = []
    for i in range(1, 101):
        vtype = random.choice(vehicle_types)
        capacity = {"HGV": random.randint(20, 44), "Van": random.randint(1, 3),
                    "Refrigerated": random.randint(10, 20), "Flatbed": random.randint(15, 30), "Tanker": random.randint(20, 40)}[vtype]
        vehicles.append({
            "vehicle_id":       f"VEH-{i:04d}",
            "vehicle_type":     vtype,
            "depot":            random.choice(depots),
            "capacity_tonnes":  capacity,
            "year_registered":  random.randint(2015, 2024),
            "status":           random.choice(statuses),
            "driver_id":        f"DRV-{random.randint(1, 150):04d}",
        })
    _write_csv(out_dir / "vehicles.csv", vehicles)

    # Routes — 500
    cities = ["London", "Birmingham", "Manchester", "Leeds", "Glasgow", "Bristol", "Liverpool",
              "Sheffield", "Edinburgh", "Cardiff", "Newcastle", "Nottingham", "Leicester", "Southampton"]
    route_types = ["Long Haul", "Regional", "Last Mile", "Express", "Overnight"]
    routes = []
    for i in range(1, 501):
        orig, dest = random.sample(cities, 2)
        dist = round(random.uniform(20, 600), 1)
        routes.append({
            "route_id":         f"RT-{i:04d}",
            "origin":           orig,
            "destination":      dest,
            "distance_km":      dist,
            "route_type":       random.choice(route_types),
            "sla_hours":        round(dist / random.uniform(60, 90), 1),
            "toll_cost_gbp":    round(random.uniform(0, 50), 2),
        })
    _write_csv(out_dir / "routes.csv", routes)

    # Deliveries — 50k
    base_date = datetime(2025, 1, 1)
    delivery_statuses = ["Delivered", "Delivered", "Delivered", "Delivered", "Late", "Failed", "In Transit"]
    deliveries = []
    for i in range(1, 50001):
        veh = random.choice(vehicles)
        route = random.choice(routes)
        planned_dep = base_date + timedelta(days=random.randint(0, 89), hours=random.randint(5, 22))
        travel_h = route["distance_km"] / random.uniform(55, 85)
        delay_h = random.choices([0, 0, 0, random.uniform(0.5, 4)], weights=[60, 20, 10, 10])[0]
        status = random.choice(delivery_statuses)
        actual_arr = planned_dep + timedelta(hours=travel_h + delay_h) if status not in ("Failed", "In Transit") else None
        deliveries.append({
            "delivery_id":          f"DEL-{i:07d}",
            "vehicle_id":           veh["vehicle_id"],
            "route_id":             route["route_id"],
            "planned_departure":    planned_dep.strftime("%Y-%m-%d %H:%M:%S"),
            "actual_arrival":       actual_arr.strftime("%Y-%m-%d %H:%M:%S") if actual_arr else "",
            "planned_duration_hrs": round(travel_h, 2),
            "actual_duration_hrs":  round(travel_h + delay_h, 2) if actual_arr else "",
            "delay_hrs":            round(delay_h, 2),
            "distance_km":          route["distance_km"],
            "load_tonnes":          round(random.uniform(0.5, veh["capacity_tonnes"]), 1),
            "status":               status,
            "is_late":              1 if delay_h > 0 and status not in ("Failed", "In Transit") else 0,
        })
    _write_csv(out_dir / "deliveries.csv", deliveries)

    # Fuel logs — 20k
    fuel_logs = []
    for i in range(1, 20001):
        veh = random.choice(vehicles)
        log_date = base_date + timedelta(days=random.randint(0, 89))
        odometer = random.randint(50000, 300000)
        litres = round(random.uniform(30, 250), 1)
        fuel_logs.append({
            "log_id":           f"FL-{i:07d}",
            "vehicle_id":       veh["vehicle_id"],
            "log_date":         log_date.strftime("%Y-%m-%d"),
            "depot":            veh["depot"],
            "odometer_km":      odometer,
            "litres_filled":    litres,
            "cost_per_litre":   round(random.uniform(1.45, 1.85), 3),
            "total_cost_gbp":   round(litres * random.uniform(1.45, 1.85), 2),
            "fuel_type":        random.choices(["Diesel", "AdBlue", "HVO"], weights=[75, 20, 5])[0],
        })
    _write_csv(out_dir / "fuel_logs.csv", fuel_logs)
    print(f"Transportation data generated: {len(vehicles)} vehicles, {len(routes)} routes, {len(deliveries)} deliveries, {len(fuel_logs)} fuel logs")


def generate_technology_data():
    out_dir = DEMOS_DIR / "technology" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    random.seed(42)

    plans = ["Starter", "Growth", "Professional", "Enterprise"]
    plan_mrr = {"Starter": 99, "Growth": 499, "Professional": 1499, "Enterprise": 4999}
    industries = ["Finance", "Healthcare", "Retail", "Manufacturing", "Technology", "Education", "Professional Services", "Logistics"]
    regions = ["North America", "Europe", "Asia Pacific", "Latin America", "Middle East"]
    roles = ["Admin", "Manager", "Analyst", "Developer", "Viewer"]
    features = ["Dashboard", "Reports", "API", "Automation", "Integrations", "Data Export", "User Management", "Alerts", "ML Insights", "Mobile App"]
    actions = ["view", "create", "update", "delete", "export", "share", "configure"]
    ticket_categories = ["Bug", "Feature Request", "Billing", "Onboarding", "Performance", "Integration"]
    priorities = ["Low", "Medium", "High", "Critical"]

    base_date = datetime(2025, 1, 1)

    # Accounts — 2 000
    accounts = []
    for i in range(1, 2001):
        plan = random.choices(plans, weights=[30, 35, 25, 10])[0]
        is_churned = random.random() < 0.12
        signup = datetime(2021, 1, 1) + timedelta(days=random.randint(0, 1460))
        churn_date = (signup + timedelta(days=random.randint(60, 900))).strftime("%Y-%m-%d") if is_churned else ""
        accounts.append({
            "account_id":       f"ACC-{i:05d}",
            "plan":             plan,
            "mrr_usd":          plan_mrr[plan],
            "industry":         random.choice(industries),
            "region":           random.choice(regions),
            "signup_date":      signup.strftime("%Y-%m-%d"),
            "churn_date":       churn_date,
            "is_churned":       1 if is_churned else 0,
            "seat_count":       random.randint(1, {"Starter": 5, "Growth": 25, "Professional": 100, "Enterprise": 500}[plan]),
            "health_score":     round(random.uniform(20, 100) if not is_churned else random.uniform(10, 50), 1),
        })
    _write_csv(out_dir / "accounts.csv", accounts)

    # Users — 10 000
    active_accounts = [a for a in accounts if not a["is_churned"]]
    users = []
    for i in range(1, 10001):
        acc = random.choice(active_accounts)
        last_login = base_date + timedelta(days=random.randint(0, 89))
        is_active = random.random() < 0.75
        users.append({
            "user_id":              f"USR-{i:07d}",
            "account_id":           acc["account_id"],
            "role":                 random.choice(roles),
            "is_active":            1 if is_active else 0,
            "last_login_date":      last_login.strftime("%Y-%m-%d") if is_active else "",
            "signup_date":          acc["signup_date"],
            "logins_last_30_days":  random.randint(0, 30) if is_active else 0,
        })
    _write_csv(out_dir / "users.csv", users)

    # Product events — 200 000
    active_users = [u for u in users if u["is_active"]]
    events = []
    for i in range(200000):
        usr = random.choice(active_users)
        evt_date = base_date + timedelta(days=random.randint(0, 89))
        feature = random.choice(features)
        events.append({
            "event_id":     f"EVT-{i+1:08d}",
            "user_id":      usr["user_id"],
            "account_id":   usr["account_id"],
            "event_date":   evt_date.strftime("%Y-%m-%d"),
            "feature":      feature,
            "action":       random.choice(actions),
            "session_id":   f"SES-{random.randint(1, 500000):08d}",
            "duration_secs": random.randint(1, 600),
        })
    _write_csv(out_dir / "events.csv", events)

    # Support tickets — 20 000
    tickets = []
    for i in range(1, 20001):
        acc = random.choice(accounts)
        created = base_date + timedelta(days=random.randint(0, 89), hours=random.randint(0, 23))
        priority = random.choices(priorities, weights=[40, 35, 18, 7])[0]
        sla_h = {"Low": 72, "Medium": 24, "High": 8, "Critical": 2}[priority]
        resolution_h = random.uniform(0.5, sla_h * 2)
        is_breached = 1 if resolution_h > sla_h else 0
        resolved_at = created + timedelta(hours=resolution_h)
        tickets.append({
            "ticket_id":            f"TKT-{i:07d}",
            "account_id":           acc["account_id"],
            "created_at":           created.strftime("%Y-%m-%d %H:%M:%S"),
            "resolved_at":          resolved_at.strftime("%Y-%m-%d %H:%M:%S"),
            "category":             random.choice(ticket_categories),
            "priority":             priority,
            "resolution_hrs":       round(resolution_h, 2),
            "sla_target_hrs":       sla_h,
            "is_sla_breached":      is_breached,
            "csat_score":           random.choices([1, 2, 3, 4, 5], weights=[5, 8, 15, 37, 35])[0],
        })
    _write_csv(out_dir / "support_tickets.csv", tickets)
    print(f"Technology data generated: {len(accounts)} accounts, {len(users)} users, {len(events)} events, {len(tickets)} support tickets")


def generate_professional_services_data():
    out_dir = DEMOS_DIR / "professional-services" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    random.seed(42)

    grades = ["Analyst", "Consultant", "Senior Consultant", "Manager", "Principal", "Director", "Partner"]
    grade_rate = {"Analyst": 400, "Consultant": 650, "Senior Consultant": 900,
                  "Manager": 1200, "Principal": 1600, "Director": 2000, "Partner": 2800}
    practices = ["Strategy", "Technology", "Operations", "Finance", "HR", "Data & Analytics", "Change Management"]
    regions = ["London", "New York", "Singapore", "Dubai", "Sydney", "Frankfurt", "Paris"]
    client_industries = ["Finance", "Healthcare", "Government", "Energy", "Retail", "Manufacturing", "Technology"]
    client_tiers = ["Strategic", "Key", "Standard"]
    task_types = ["Client Work", "Business Development", "Internal", "Training", "Admin"]
    delivery_statuses = ["On Track", "At Risk", "Delayed", "Completed", "Cancelled"]

    base_date = datetime(2025, 1, 1)

    # Consultants — 200
    consultants = []
    for i in range(1, 201):
        grade = random.choices(grades, weights=[20, 25, 20, 15, 10, 6, 4])[0]
        consultants.append({
            "consultant_id":    f"CON-{i:04d}",
            "grade":            grade,
            "practice":         random.choice(practices),
            "region":           random.choice(regions),
            "daily_rate_gbp":   grade_rate[grade] + random.randint(-50, 100),
            "years_experience": random.randint(1, 25),
            "is_billable":      random.choices([1, 0], weights=[85, 15])[0],
            "hire_date":        (datetime(2010, 1, 1) + timedelta(days=random.randint(0, 5000))).strftime("%Y-%m-%d"),
        })
    _write_csv(out_dir / "consultants.csv", consultants)

    # Clients — 100
    clients = []
    for i in range(1, 101):
        tier = random.choices(client_tiers, weights=[15, 30, 55])[0]
        contract_val = {"Strategic": random.uniform(500000, 5000000),
                        "Key": random.uniform(100000, 800000),
                        "Standard": random.uniform(10000, 200000)}[tier]
        clients.append({
            "client_id":        f"CLI-{i:04d}",
            "client_name":      f"Client {i} {random.choice(client_industries)}",
            "industry":         random.choice(client_industries),
            "region":           random.choice(regions),
            "tier":             tier,
            "contract_value_gbp": round(contract_val, 2),
            "relationship_years": random.randint(1, 20),
            "nps_score":        random.randint(-100, 100),
        })
    _write_csv(out_dir / "clients.csv", clients)

    # Engagements — 1 000
    engagements = []
    for i in range(1, 1001):
        client = random.choice(clients)
        lead = random.choice(consultants)
        start = base_date + timedelta(days=random.randint(-180, 60))
        duration = random.randint(30, 365)
        end = start + timedelta(days=duration)
        budget = round(random.uniform(20000, 500000), 2)
        actual = round(budget * random.uniform(0.7, 1.35), 2)
        margin_pct = round((budget - actual) / budget * 100, 2)
        status = random.choice(delivery_statuses)
        engagements.append({
            "engagement_id":        f"ENG-{i:05d}",
            "client_id":            client["client_id"],
            "lead_consultant_id":   lead["consultant_id"],
            "practice":             lead["practice"],
            "start_date":           start.strftime("%Y-%m-%d"),
            "planned_end_date":     end.strftime("%Y-%m-%d"),
            "budget_gbp":           budget,
            "actual_spend_gbp":     actual,
            "margin_pct":           margin_pct,
            "status":               status,
            "headcount":            random.randint(1, 15),
        })
    _write_csv(out_dir / "engagements.csv", engagements)

    # Timesheets — 50 000
    timesheets = []
    weeks = [(base_date + timedelta(weeks=w)).strftime("%Y-%m-%d") for w in range(-26, 14)]
    for i in range(1, 50001):
        con = random.choice(consultants)
        eng = random.choice(engagements)
        week = random.choice(weeks)
        task = random.choices(task_types, weights=[60, 15, 10, 8, 7])[0]
        hours = round(random.uniform(0.5, 10), 2)
        is_billable = 1 if task == "Client Work" and con["is_billable"] else 0
        timesheets.append({
            "timesheet_id":     f"TS-{i:07d}",
            "consultant_id":    con["consultant_id"],
            "engagement_id":    eng["engagement_id"],
            "week_starting":    week,
            "task_type":        task,
            "hours_logged":     hours,
            "is_billable":      is_billable,
            "daily_rate_gbp":   con["daily_rate_gbp"],
            "billed_value_gbp": round(hours / 8 * con["daily_rate_gbp"], 2) if is_billable else 0,
        })
    _write_csv(out_dir / "timesheets.csv", timesheets)
    print(f"Professional services data generated: {len(consultants)} consultants, {len(clients)} clients, {len(engagements)} engagements, {len(timesheets)} timesheets")


if __name__ == "__main__":
    generate_manufacturing_data()
    generate_retail_data()
    generate_energy_data()
    generate_healthcare_data()
    generate_financial_services_data()
    generate_hospitality_data()
    generate_media_data()
    generate_construction_data()
    generate_education_data()
    generate_transportation_data()
    generate_technology_data()
    generate_professional_services_data()
