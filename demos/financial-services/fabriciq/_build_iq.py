"""Build the financial-services Fabric IQ ontology package.

Entities (4; Transaction spans Lakehouse + Eventhouse):
  Customer         PK customer_id
  Account          PK account_id;      FK customer_id
  MerchantCategory PK category_id      (derived from distinct merchant_category)
  Transaction      PK transaction_id;  FK account_id, customer_id, merchant_category  (dual)
"""

from __future__ import annotations

import csv
import os
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_scenarios"))
from fabriciq_common import Entity, Prop, write_iq  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "financial_services_ontology_package.iq")
EVENT_CAP = 20000

ENTITIES = [
    Entity("Customer", "customers", [
        Prop("CustomerId", "customer_id", "String", ident=True, display=True),
        Prop("AgeGroup", "age_group"),
        Prop("Segment", "segment"),
        Prop("Region", "region"),
        Prop("RiskTier", "risk_tier"),
        Prop("SinceYear", "since_year", "BigInt"),
    ]),
    Entity("Account", "accounts", [
        Prop("AccountId", "account_id", "String", ident=True, display=True),
        Prop("CustomerId", "customer_id"),
        Prop("AccountType", "account_type"),
        Prop("Balance", "balance", "Double"),
        Prop("CreditLimit", "credit_limit", "Double"),
        Prop("CreditUtilisationPct", "credit_utilisation_pct", "Double"),
        Prop("Status", "status"),
    ]),
    Entity("MerchantCategory", "merchant_categories", [
        Prop("CategoryId", "category_id", "String", ident=True, display=True),
    ]),
    Entity("Transaction", "transactions", [
        Prop("TransactionId", "transaction_id", "String", ident=True, display=True),
        Prop("AccountId", "account_id"),
        Prop("CustomerId", "customer_id"),
        Prop("MerchantCategory", "merchant_category"),
        Prop("TransactionType", "transaction_type"),
        Prop("Channel", "channel"),
        Prop("Country", "country"),
        Prop("IsFlaggedFraud", "is_flagged_fraud", "Boolean"),
        Prop("Amount", "amount", "Double", ts=True),
    ]),
]

RELATIONSHIP_TYPES = [
    ("AccountOwnedByCustomer", "Account", "Customer"),
    ("TransactionOnAccount", "Transaction", "Account"),
    ("TransactionByCustomer", "Transaction", "Customer"),
    ("TransactionInCategory", "Transaction", "MerchantCategory"),
]
BINDING_RELATIONSHIP = [
    ("AccountOwnedByCustomer", "Account", "Customer", "account_id", "customer_id", "accounts"),
    ("TransactionOnAccount", "Transaction", "Account", "transaction_id", "account_id", "transactions"),
    ("TransactionByCustomer", "Transaction", "Customer", "transaction_id", "customer_id", "transactions"),
    ("TransactionInCategory", "Transaction", "MerchantCategory", "transaction_id", "merchant_category", "transactions"),
]


def _read(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build():
    customers = _read("customers.csv")
    accounts = _read("accounts.csv")
    txns = _read("transactions.csv")

    cats = OrderedDict()
    for t in txns:
        if t.get("merchant_category"):
            cats.setdefault(t["merchant_category"], None)

    txns_c = txns[:EVENT_CAP]

    instance_tables = {
        "customers": (["customer_id", "age_group", "segment", "region", "risk_tier", "since_year"],
                      [[r["customer_id"], r["age_group"], r["segment"], r["region"], r["risk_tier"], r["since_year"]] for r in customers]),
        "accounts": (["account_id", "customer_id", "account_type", "balance", "credit_limit", "credit_utilisation_pct", "status"],
                     [[r["account_id"], r["customer_id"], r["account_type"], r["balance"], r["credit_limit"], r["credit_utilisation_pct"], r["status"]] for r in accounts]),
        "merchant_categories": (["category_id"], [[k] for k in cats]),
        "transactions": (["transaction_id", "account_id", "customer_id", "merchant_category", "transaction_type", "channel", "country", "is_flagged_fraud"],
                         [[r["transaction_id"], r["account_id"], r["customer_id"], r["merchant_category"], r["transaction_type"], r["channel"], r["country"], r["is_flagged_fraud"]] for r in txns_c]),
    }
    events_tables = {
        "transactions": (["transaction_id", "timestamp_utc", "amount"],
                         [[r["transaction_id"], r["transaction_date"], r["amount"]] for r in txns_c]),
    }

    write_iq(OUT, ENTITIES, RELATIONSHIP_TYPES, BINDING_RELATIONSHIP, instance_tables, events_tables)
    print(f"  Customers: {len(customers)}  Accounts: {len(accounts)}  Categories: {len(cats)}  Transactions: {len(txns_c)}")


if __name__ == "__main__":
    build()
