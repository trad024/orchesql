CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE suppliers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT NOT NULL
);

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL
);

CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    manager_id INTEGER REFERENCES employees(id)
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    price NUMERIC NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    supplier_id INTEGER REFERENCES suppliers(id)
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    employee_id INTEGER REFERENCES employees(id),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    total NUMERIC NOT NULL
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL
);

CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    amount NUMERIC NOT NULL,
    method TEXT NOT NULL,
    paid_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE reviews (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    rating INTEGER NOT NULL,
    comment TEXT
);

INSERT INTO categories (name) VALUES
    ('Tools'),
    ('Electronics'),
    ('Office');

INSERT INTO suppliers (name, country) VALUES
    ('Acme Supply Co', 'USA'),
    ('Nordic Parts', 'Sweden'),
    ('Pacific Trading', 'Japan');

INSERT INTO customers (name, email) VALUES
    ('Alice Smith', 'alice@example.com'),
    ('Bob Jones', 'bob@example.com'),
    ('Carla Diaz', 'carla@example.com'),
    ('David Chen', 'david@example.com');

INSERT INTO employees (name, role, manager_id) VALUES
    ('Elena Rossi', 'Sales Director', NULL),
    ('Frank Lee', 'Sales Rep', 1),
    ('Grace Kim', 'Sales Rep', 1);

INSERT INTO products (name, price, category_id, supplier_id) VALUES
    ('Widget', 9.99, 1, 1),
    ('Gadget', 19.99, 2, 1),
    ('Hammer', 14.50, 1, 2),
    ('Notebook', 4.25, 3, 3),
    ('Wireless Mouse', 24.99, 2, 2),
    ('Stapler', 6.75, 3, NULL);

INSERT INTO orders (customer_id, employee_id, total) VALUES
    (1, 2, 29.98),
    (1, 2, 9.99),
    (2, 3, 19.99),
    (3, 2, 39.24),
    (4, 3, 24.99),
    (3, NULL, 6.75);

INSERT INTO order_items (order_id, product_id, quantity) VALUES
    (1, 1, 1),
    (1, 2, 1),
    (2, 1, 1),
    (3, 2, 1),
    (4, 3, 1),
    (4, 4, 2),
    (5, 5, 1),
    (6, 6, 1);

INSERT INTO payments (order_id, amount, method) VALUES
    (1, 29.98, 'card'),
    (2, 9.99, 'card'),
    (3, 19.99, 'paypal'),
    (4, 39.24, 'card'),
    (5, 24.99, 'paypal'),
    (6, 6.75, 'cash');

INSERT INTO reviews (customer_id, product_id, rating, comment) VALUES
    (1, 1, 5, 'Great widget, works as expected.'),
    (2, 1, 4, 'Solid, would buy again.'),
    (1, 2, 3, 'Decent gadget but pricey.'),
    (NULL, 3, 5, 'Best hammer I have used.'),
    (3, 5, 2, 'Mouse stopped working after a week.');
