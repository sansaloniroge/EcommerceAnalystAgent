#!/usr/bin/env python3
"""
Loads the Olist Brazilian e-commerce CSVs (downloaded manually from Kaggle,
see README) into Postgres. Truncates and reloads every scoped table each run
-- idempotent, safe to re-run.

Usage: poetry run load-dataset [--data-dir data/raw]
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]

# (csv filename, table name, columns in schema.sql order, columns that are
# INTEGER in schema.sql). Order matters: parents before children, for both
# TRUNCATE ... CASCADE and the FK-safe insert order below.
#
# int_columns must use pandas' nullable "Int64" dtype at read time -- plain
# int64 can't hold NaN, so pandas silently upgrades any integer column with
# missing values to float64, and COPY then rejects "40.0" for an INTEGER
# column. NUMERIC columns (price, freight_value, payment_value) are meant to
# stay float and are deliberately not listed here.
TABLES: list[tuple[str, str, list[str], list[str]]] = [
    (
        "product_category_name_translation.csv",
        "product_category_name_translation",
        ["product_category_name", "product_category_name_english"],
        [],
    ),
    (
        "olist_customers_dataset.csv",
        "customers",
        ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"],
        ["customer_zip_code_prefix"],
    ),
    (
        "olist_sellers_dataset.csv",
        "sellers",
        ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"],
        ["seller_zip_code_prefix"],
    ),
    (
        "olist_products_dataset.csv",
        "products",
        [
            "product_id",
            "product_category_name",
            "product_name_lenght",
            "product_description_lenght",
            "product_photos_qty",
            "product_weight_g",
            "product_length_cm",
            "product_height_cm",
            "product_width_cm",
        ],
        [
            "product_name_lenght",
            "product_description_lenght",
            "product_photos_qty",
            "product_weight_g",
            "product_length_cm",
            "product_height_cm",
            "product_width_cm",
        ],
    ),
    (
        "olist_orders_dataset.csv",
        "orders",
        [
            "order_id",
            "customer_id",
            "order_status",
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
        [],
    ),
    (
        "olist_order_items_dataset.csv",
        "order_items",
        ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"],
        ["order_item_id"],
    ),
    (
        "olist_order_payments_dataset.csv",
        "order_payments",
        ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"],
        ["payment_sequential", "payment_installments"],
    ),
    (
        "olist_order_reviews_dataset.csv",
        "order_reviews",
        [
            "review_id",
            "order_id",
            "review_score",
            "review_comment_title",
            "review_comment_message",
            "review_creation_date",
            "review_answer_timestamp",
        ],
        ["review_score"],
    ),
]


def _rows_for_copy(csv_path: Path, columns: list[str], int_columns: list[str] | None = None) -> list[tuple[Any, ...]]:
    dtype = {col: "Int64" for col in (int_columns or [])}
    df = pd.read_csv(csv_path, usecols=columns, dtype=dtype)
    df = df[columns]  # enforce column order regardless of CSV header order
    df = df.astype(object).where(pd.notnull(df), None)
    return [tuple(row) for row in df.values.tolist()]


def load_all(data_dir: Path, database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            table_names = [t for _, t, _, _ in TABLES]
            # Reverse order for TRUNCATE so children are cleared before parents
            # even matters little with CASCADE, but keeps intent explicit.
            cur.execute(f"TRUNCATE {', '.join(reversed(table_names))} RESTART IDENTITY CASCADE;")

            for csv_name, table, columns, int_columns in TABLES:
                csv_path = data_dir / csv_name
                if not csv_path.exists():
                    raise FileNotFoundError(
                        f"Missing {csv_path}. Download the dataset from "
                        "kaggle.com/datasets/olistbr/brazilian-ecommerce and unzip it into "
                        f"{data_dir}/ (see README)."
                    )
                rows = _rows_for_copy(csv_path, columns, int_columns)
                col_list = ", ".join(columns)
                with cur.copy(f"COPY {table} ({col_list}) FROM STDIN") as copy:
                    for row in rows:
                        copy.write_row(row)
                print(f"loaded {len(rows):>7} rows -> {table}")
        conn.commit()


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default="data/raw", help="Directory containing the unzipped Kaggle CSVs")
    args = ap.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required (see .env.example)")

    data_dir = (REPO_ROOT / args.data_dir) if not Path(args.data_dir).is_absolute() else Path(args.data_dir)
    load_all(data_dir, database_url)
    print("done.")


if __name__ == "__main__":
    main()
