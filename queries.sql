-- Anzahl Kunden pro Schule
SELECT schools.name AS Schule, COUNT(DISTINCT customers.id) AS Kunden
FROM schools
         JOIN products ON schools.id = products.school_id
         JOIN variants ON products.id = variants.product_id
         JOIN line_items ON variants.id = line_items.variant_id
         JOIN orders ON orders.id = line_items.order_id
         JOIN customers ON customers.id = orders.customer_id
GROUP BY schools.name
ORDER BY schools.name, Kunden DESC;

-- Anzahl bestellte Produkte
SELECT schools.name             AS Schule,
       products.name            AS Produkt,
       products.type_     AS Typ,
       variants.size            AS Groeße,
       variants.color           AS Farbe,
       SUM(line_items.quantity) AS Menge
FROM schools
         JOIN products ON schools.id = products.school_id
         JOIN variants ON products.id = variants.product_id
         JOIN line_items ON variants.id = line_items.variant_id
WHERE schools.id IS NOT NULL
GROUP BY variants.id
ORDER BY schools.name, products.name, variants.size, variants.color;

-- Bestellungen, die noch nicht bezahlt wurden
SELECT schools.name                                                                  AS "Schule",
       products.name                                                                 AS "Produkt",
       variants.color                                                                AS "Farbe",
       variants.size                                                                 AS "Größe",
       orders.nr                                                                     AS "Bestellnummer",
       ((SELECT TOTAL(line_items.amount * line_items.quantity) AS total_1
         FROM line_items
         WHERE line_items.order_id = orders.id) - orders.discount) + orders.shipping AS "Betrag",
       (((SELECT TOTAL(line_items.amount * line_items.quantity) AS total_2
          FROM line_items
          WHERE line_items.order_id = orders.id) - orders.discount) + orders.shipping) -
       ((SELECT TOTAL(order_transactions.amount) AS total_3
         FROM order_transactions
         WHERE order_transactions.order_id = orders.id) + orders.decree)             AS "fällig",
       customers.first_name                                                          AS "Vorname",
       customers.last_name                                                           AS "Nachname",
       customers.email AS Email
FROM schools
         JOIN products ON schools.id = products.school_id
         JOIN variants ON products.id = variants.product_id
         JOIN line_items ON variants.id = line_items.variant_id
         JOIN orders ON orders.id = line_items.order_id
         JOIN customers ON customers.id = orders.customer_id
WHERE ((SELECT TOTAL(order_transactions.amount) AS total_4
        FROM order_transactions
        WHERE order_transactions.order_id = orders.id) + orders.decree >=
       ((SELECT TOTAL(line_items.amount * line_items.quantity) AS total_5
         FROM line_items
         WHERE line_items.order_id = orders.id) - orders.discount) + orders.shipping) = 0;

-- Emails von Kunden, die noch nicht vollst. bezahlt haben
SELECT DISTINCT customers.email AS Email
FROM schools
         JOIN products ON schools.id = products.school_id
         JOIN variants ON products.id = variants.product_id
         JOIN line_items ON variants.id = line_items.variant_id
         JOIN orders ON orders.id = line_items.order_id
         JOIN customers ON customers.id = orders.customer_id
WHERE ((SELECT TOTAL(order_transactions.amount) AS total_4
        FROM order_transactions
        WHERE order_transactions.order_id = orders.id) + orders.decree >=
       ((SELECT TOTAL(line_items.amount * line_items.quantity) AS total_5
         FROM line_items
         WHERE line_items.order_id = orders.id) - orders.discount) + orders.shipping) = 0;


-- alle Bestellungen
SELECT schools.name                                                                  AS "Schule",
       products.name                                                                 AS "Produkt",
       variants.color                                                                AS "Farbe",
       variants.size                                                                 AS "Größe",
              orders.note AS Name,
       orders.nr                                                                     AS "Bestellnummer",
       ((SELECT TOTAL(line_items.amount * line_items.quantity) AS total_1
         FROM line_items
         WHERE line_items.order_id = orders.id) - orders.discount) + orders.shipping AS "Betrag"
FROM schools
         JOIN products ON schools.id = products.school_id
         JOIN variants ON products.id = variants.product_id
         JOIN line_items ON variants.id = line_items.variant_id
         JOIN orders ON orders.id = line_items.order_id
         JOIN customers ON customers.id = orders.customer_id
        ORDER BY schools.name, customers.last_name, customers.first_name, variants.size, variants.color;