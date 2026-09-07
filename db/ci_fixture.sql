-- Small, hand-built synthetic fixture used ONLY by the CI eval gate
-- (.github/workflows/eval-gate.yml). Not the real Olist dataset: CI has no
-- access to the Kaggle CSVs (see db/schema.sql / README "How to run it"),
-- so this exists purely to exercise the agent end-to-end on every PR against
-- a small set of hand-computed answers. The full 15-question eval against
-- the real dataset (eval/dataset.json) stays a manual/local step.
--
-- Ground truth for eval/ci_dataset.json is computed directly from these rows
-- -- see that file for the exact numbers and how they were derived.

INSERT INTO product_category_name_translation (product_category_name, product_category_name_english) VALUES
    ('moveis_decoracao', 'furniture_decor'),
    ('cama_mesa_banho', 'bed_bath_table');

INSERT INTO customers (customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state) VALUES
    ('cust_1', 'cust_1_unique', 10000, 'sao paulo', 'SP'),
    ('cust_2', 'cust_2_unique', 20000, 'rio de janeiro', 'RJ');

INSERT INTO sellers (seller_id, seller_zip_code_prefix, seller_city, seller_state) VALUES
    ('seller_1', 30000, 'belo horizonte', 'MG'),
    ('seller_2', 40000, 'curitiba', 'PR');

INSERT INTO products (product_id, product_category_name, product_name_lenght, product_description_lenght, product_photos_qty, product_weight_g, product_length_cm, product_height_cm, product_width_cm) VALUES
    ('prod_1', 'moveis_decoracao', 40, 200, 1, 500, 20, 10, 15),
    ('prod_2', 'moveis_decoracao', 45, 220, 2, 700, 25, 12, 18),
    ('prod_3', 'cama_mesa_banho', 30, 150, 1, 300, 15, 8, 10);

-- order_1, order_2 delivered; order_3 shipped (not delivered) -- questions
-- that filter on "delivered" must exclude it.
INSERT INTO orders (order_id, customer_id, order_status, order_purchase_timestamp, order_approved_at, order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date) VALUES
    ('order_1', 'cust_1', 'delivered', '2024-01-10 10:00:00', '2024-01-10 11:00:00', '2024-01-11 09:00:00', '2024-01-14 15:00:00', '2024-01-20 00:00:00'),
    ('order_2', 'cust_2', 'delivered', '2024-01-15 10:00:00', '2024-01-15 11:00:00', '2024-01-16 09:00:00', '2024-01-19 15:00:00', '2024-01-25 00:00:00'),
    ('order_3', 'cust_1', 'shipped',   '2024-02-01 10:00:00', '2024-02-01 11:00:00', '2024-02-02 09:00:00', NULL,                  '2024-02-10 00:00:00');

INSERT INTO order_items (order_id, order_item_id, product_id, seller_id, shipping_limit_date, price, freight_value) VALUES
    ('order_1', 1, 'prod_1', 'seller_1', '2024-01-11 00:00:00', 100.00, 10.00),
    ('order_2', 1, 'prod_2', 'seller_2', '2024-01-16 00:00:00', 200.00, 20.00),
    ('order_3', 1, 'prod_3', 'seller_1', '2024-02-02 00:00:00', 50.00, 5.00);

INSERT INTO order_payments (order_id, payment_sequential, payment_type, payment_installments, payment_value) VALUES
    ('order_1', 1, 'credit_card', 1, 110.00),
    ('order_2', 1, 'boleto', 1, 220.00),
    ('order_3', 1, 'credit_card', 2, 55.00);

INSERT INTO order_reviews (review_id, order_id, review_score, review_comment_title, review_comment_message, review_creation_date, review_answer_timestamp) VALUES
    ('review_1', 'order_1', 5, NULL, 'Great!', '2024-01-15 00:00:00', '2024-01-15 12:00:00'),
    ('review_2', 'order_2', 3, NULL, 'Ok.', '2024-01-20 00:00:00', '2024-01-20 12:00:00');
