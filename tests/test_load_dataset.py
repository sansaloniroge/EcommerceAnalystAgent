import csv
from pathlib import Path

from scripts.load_dataset import TABLES, _rows_for_copy


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def test_rows_for_copy_converts_missing_values_to_none(tmp_path: Path):
    csv_path = tmp_path / "customers.csv"
    _write_csv(
        csv_path,
        header=["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"],
        rows=[["c1", "u1", "12345", "", "SP"]],
    )

    rows = _rows_for_copy(
        csv_path, ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"]
    )

    assert len(rows) == 1
    assert rows[0][0] == "c1"
    assert rows[0][3] is None  # empty customer_city -> None, not ""


def test_rows_for_copy_enforces_requested_column_order(tmp_path: Path):
    csv_path = tmp_path / "sellers.csv"
    # CSV header order deliberately differs from the requested column order.
    _write_csv(
        csv_path,
        header=["seller_state", "seller_id", "seller_city", "seller_zip_code_prefix"],
        rows=[["SP", "s1", "Sao Paulo", "1000"]],
    )

    rows = _rows_for_copy(csv_path, ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"])

    assert rows[0] == ("s1", 1000, "Sao Paulo", "SP")


def test_rows_for_copy_keeps_integer_columns_as_int_despite_missing_values(tmp_path: Path):
    """
    Regression test: pandas silently upgrades an integer column with any
    missing values to float64, so a clean value like 40 comes out as the
    Python float 40.0 -- which Postgres COPY rejects for an INTEGER column
    ("invalid input syntax for type integer: 40.0"). int_columns must use
    pandas' nullable Int64 dtype to avoid this.
    """
    csv_path = tmp_path / "products.csv"
    _write_csv(
        csv_path,
        header=["product_id", "product_weight_g"],
        rows=[["p1", "500"], ["p2", ""]],  # p2's weight is missing
    )

    rows = _rows_for_copy(csv_path, ["product_id", "product_weight_g"], int_columns=["product_weight_g"])

    assert rows[0] == ("p1", 500)
    assert isinstance(rows[0][1], int)
    assert rows[1] == ("p2", None)


def test_table_load_order_puts_parents_before_children():
    table_names = [t for _, t, _, _ in TABLES]
    # product_category_name_translation, customers, sellers, products are
    # all referenced by later tables (products, orders, order_items) and
    # must load first for the FKs in db/schema.sql to succeed.
    assert table_names.index("product_category_name_translation") < table_names.index("products")
    assert table_names.index("customers") < table_names.index("orders")
    assert table_names.index("sellers") < table_names.index("order_items")
    assert table_names.index("products") < table_names.index("order_items")
    assert table_names.index("orders") < table_names.index("order_items")
    assert table_names.index("orders") < table_names.index("order_payments")
    assert table_names.index("orders") < table_names.index("order_reviews")
