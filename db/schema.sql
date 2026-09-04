-- Core schema for the Olist Brazilian e-commerce dataset.
-- Scope: orders, order_items, products, customers, sellers, order_payments,
-- order_reviews, product_category_name_translation. geolocation intentionally
-- excluded (heaviest table, not needed for the scoped example questions).
--
-- Load order matters for FK constraints: parents before children.
-- See scripts/load_dataset.py for the matching load sequence.

CREATE TABLE IF NOT EXISTS product_category_name_translation (
    product_category_name          TEXT PRIMARY KEY,
    product_category_name_english  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id                TEXT PRIMARY KEY,
    customer_unique_id         TEXT NOT NULL,
    customer_zip_code_prefix   INTEGER,
    customer_city               TEXT,
    customer_state              TEXT
);
CREATE INDEX IF NOT EXISTS idx_customers_unique_id ON customers (customer_unique_id);

CREATE TABLE IF NOT EXISTS sellers (
    seller_id                TEXT PRIMARY KEY,
    seller_zip_code_prefix   INTEGER,
    seller_city               TEXT,
    seller_state              TEXT
);

-- product_category_name is NOT a FK to product_category_name_translation:
-- two real category names in the raw dataset ("pc_gamer",
-- "portateis_cozinha_e_preparadores_de_alimentos") have no corresponding
-- translation row. A real data-quality gap in the source, not backfilled
-- with an invented translation -- queries joining to the translation table
-- should expect some products to have no English name.
CREATE TABLE IF NOT EXISTS products (
    product_id                    TEXT PRIMARY KEY,
    product_category_name         TEXT,
    product_name_lenght            INTEGER,
    product_description_lenght     INTEGER,
    product_photos_qty             INTEGER,
    product_weight_g               INTEGER,
    product_length_cm              INTEGER,
    product_height_cm              INTEGER,
    product_width_cm               INTEGER
);
CREATE INDEX IF NOT EXISTS idx_products_category ON products (product_category_name);

CREATE TABLE IF NOT EXISTS orders (
    order_id                        TEXT PRIMARY KEY,
    customer_id                     TEXT NOT NULL REFERENCES customers (customer_id),
    order_status                    TEXT NOT NULL,
    order_purchase_timestamp        TIMESTAMP NOT NULL,
    order_approved_at               TIMESTAMP,
    order_delivered_carrier_date    TIMESTAMP,
    order_delivered_customer_date   TIMESTAMP,
    order_estimated_delivery_date   TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_purchase_timestamp ON orders (order_purchase_timestamp);

CREATE TABLE IF NOT EXISTS order_items (
    order_id             TEXT NOT NULL REFERENCES orders (order_id),
    order_item_id        INTEGER NOT NULL,
    product_id           TEXT NOT NULL REFERENCES products (product_id),
    seller_id            TEXT NOT NULL REFERENCES sellers (seller_id),
    shipping_limit_date  TIMESTAMP,
    price                NUMERIC(12, 2) NOT NULL,
    freight_value        NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (order_id, order_item_id)
);
CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items (product_id);
CREATE INDEX IF NOT EXISTS idx_order_items_seller_id ON order_items (seller_id);

CREATE TABLE IF NOT EXISTS order_payments (
    order_id             TEXT NOT NULL REFERENCES orders (order_id),
    payment_sequential   INTEGER NOT NULL,
    payment_type         TEXT NOT NULL,
    payment_installments INTEGER NOT NULL,
    payment_value        NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

-- review_id is NOT reliably unique across the raw CSV (a small number of
-- values repeat for different orders) -- a serial surrogate key avoids a
-- failed load on that constraint violation while still indexing review_id.
CREATE TABLE IF NOT EXISTS order_reviews (
    id                        SERIAL PRIMARY KEY,
    review_id                 TEXT NOT NULL,
    order_id                  TEXT NOT NULL REFERENCES orders (order_id),
    review_score              INTEGER NOT NULL,
    review_comment_title      TEXT,
    review_comment_message    TEXT,
    review_creation_date      TIMESTAMP NOT NULL,
    review_answer_timestamp   TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_order_reviews_order_id ON order_reviews (order_id);
CREATE INDEX IF NOT EXISTS idx_order_reviews_review_id ON order_reviews (review_id);

-- Least-privilege role for the sql_query tool: the LLM's generated SQL runs
-- as this role, never as the admin role that owns/loads the schema. Defense
-- in depth alongside the query-level guardrails (SELECT-only parsing,
-- keyword blacklist, LIMIT, timeout) implemented in app/tools/sql_query.py.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_readonly') THEN
        CREATE ROLE agent_readonly LOGIN PASSWORD 'agent_readonly_local_dev';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE ecommerce_agent TO agent_readonly;
GRANT USAGE ON SCHEMA public TO agent_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO agent_readonly;
