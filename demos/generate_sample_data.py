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


if __name__ == "__main__":
    generate_manufacturing_data()
    generate_retail_data()
    generate_energy_data()
    generate_healthcare_data()
    generate_financial_services_data()
    generate_hospitality_data()
    generate_media_data()
