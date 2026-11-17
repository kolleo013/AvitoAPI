CREATE TABLE IF NOT EXISTS restaurants (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dishes (
    id INTEGER PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
    name TEXT NOT NULL,
    price_kopecks INTEGER NOT NULL CHECK(price_kopecks > 0),
    available INTEGER NOT NULL DEFAULT 1 CHECK(available IN (0, 1))
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
    customer_id TEXT NOT NULL,
    address TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'accepted')),
    total_kopecks INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
    order_id TEXT NOT NULL REFERENCES orders(id),
    dish_id INTEGER NOT NULL REFERENCES dishes(id),
    name TEXT NOT NULL,
    price_kopecks INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    PRIMARY KEY(order_id, dish_id)
);
CREATE INDEX IF NOT EXISTS orders_restaurant_status ON orders(restaurant_id, status);
INSERT OR IGNORE INTO restaurants VALUES (1, 'Демо-кафе');
INSERT OR IGNORE INTO dishes VALUES (1, 1, 'Паста с томатами', 35000, 1);
INSERT OR IGNORE INTO dishes VALUES (2, 1, 'Овощной салат', 22000, 1);
INSERT OR IGNORE INTO dishes VALUES (3, 1, 'Суп дня', 18000, 0);
