import ast
import json
import os
import shutil
import urllib.error
import urllib.request
from datetime import datetime
from functools import wraps

import psycopg
from dotenv import load_dotenv
from flask import Flask, abort, flash, g, has_request_context, jsonify, redirect, render_template, request, session, url_for
from psycopg import IntegrityError
from psycopg.rows import dict_row
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://arshop:arshop@127.0.0.1:5432/ar_shopping_world",
)
UPLOAD_ROOT = os.path.join(BASE_DIR, "static", "images")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
DEFAULT_CATEGORIES = ["Shoes", "Pants", "Shirts", "Jackets", "Wallets", "Purses", "Belts"]

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "change-this-secret-before-production"),
    MAX_CONTENT_LENGTH=12 * 1024 * 1024,
    DB_INITIALIZED=False,
    TEMPLATES_AUTO_RELOAD=True,
)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")

CURRENCIES = {"EUR": (1 / 302, "EUR"), "USD": (1 / 278, "USD"), "PKR": (1, "PKR")}
CLOTHES_SIZES = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL", "5XL", "6XL", "7XL"]
SHOE_SIZES = [str(number) for number in range(24, 48)]
ACCESSORY_SIZES = [f"{number}cm" for number in range(10, 51)]
SIZE_MAP = {
    "Clothes": CLOTHES_SIZES,
    "Shoes": SHOE_SIZES,
    "Accessories": ACCESSORY_SIZES,
}
ALL_CATALOG_SIZES = CLOTHES_SIZES + SHOE_SIZES + ACCESSORY_SIZES
PRESET_SIZES = CLOTHES_SIZES
PRODUCT_TYPES = ["Clothes", "Shoes", "Accessories"]
SIZE_GROUPS = ["Male", "Female", "Unisex", "Child"]
MAIN_CATEGORIES = ["Men", "Women", "Kids", "Unisex"]
SUB_CATEGORIES = {
    "Clothes": ["Shirts", "Pants", "Jackets", "Hoodies", "Dresses", "Coats", "Tops"],
    "Shoes": ["Sneakers", "Boots", "Formal", "Sandals", "Sports"],
    "Accessories": ["Wallets", "Purses", "Belts", "Bags", "Hats", "Scarves"],
}
CONDITIONS = [
    ("new_with_tag", "New with tag"),
    ("new_without_tag", "New without tag"),
    ("used", "Used"),
]
CONDITION_LABELS = dict(CONDITIONS)
REGION_OPTIONS = [
    ("europe_america", "Show only in Europe and America"),
    ("pakistan", "Show in Pakistan"),
    ("all", "Show in all regions"),
]
EUR_TO_STORE = 302
WEIGHT_LIMIT_KG = 5
DEFAULT_SHIPPING_ZONES = [
    {"name": "Germany", "key": "germany", "unit": "EUR", "under": 10, "over": 10, "express_under": 20, "express_over": 20},
    {"name": "Europe", "key": "europe", "unit": "EUR", "under": 20, "over": 30, "express_under": 35, "express_over": 50},
    {"name": "Canada/USA", "key": "canada_usa", "unit": "EUR", "under": 30, "over": 60, "express_under": 55, "express_over": 90},
    {"name": "Pakistan", "key": "pakistan", "unit": "PKR", "under": 600, "over": 1000, "express_under": 1200, "express_over": 1800},
]
ZONE_NAMES = [zone["name"] for zone in DEFAULT_SHIPPING_ZONES]
ZONE_CURRENCY = {"Germany": "EUR", "Europe": "EUR", "Canada/USA": "USD", "Pakistan": "PKR"}
COUNTRY_CODE_TO_ZONE = {
    "PK": "Pakistan",
    "DE": "Germany",
    "US": "Canada/USA",
    "CA": "Canada/USA",
    "AT": "Europe",
    "BE": "Europe",
    "BG": "Europe",
    "CH": "Europe",
    "CY": "Europe",
    "CZ": "Europe",
    "DK": "Europe",
    "EE": "Europe",
    "ES": "Europe",
    "FI": "Europe",
    "FR": "Europe",
    "GB": "Europe",
    "GR": "Europe",
    "HR": "Europe",
    "HU": "Europe",
    "IE": "Europe",
    "IT": "Europe",
    "LT": "Europe",
    "LU": "Europe",
    "LV": "Europe",
    "MT": "Europe",
    "NL": "Europe",
    "NO": "Europe",
    "PL": "Europe",
    "PT": "Europe",
    "RO": "Europe",
    "SE": "Europe",
    "SI": "Europe",
    "SK": "Europe",
    "UK": "Europe",
}
LANGUAGE_TO_ZONE = {
    "ur": "Pakistan",
    "de": "Germany",
    "fr": "Europe",
    "es": "Europe",
    "it": "Europe",
    "pt": "Europe",
    "tr": "Europe",
}
CURRENCY_TO_ZONE = {"PKR": "Pakistan", "EUR": "Europe", "USD": "Canada/USA"}
ADDRESS_ZONE_HINTS = (
    ("pakistan", "Pakistan"),
    ("islamabad", "Pakistan"),
    ("karachi", "Pakistan"),
    ("lahore", "Pakistan"),
    ("deutschland", "Germany"),
    ("germany", "Germany"),
    ("berlin", "Germany"),
    ("munich", "Germany"),
    ("united states", "Canada/USA"),
    ("u.s.a", "Canada/USA"),
    ("u.s.", "Canada/USA"),
    ("usa", "Canada/USA"),
    ("canada", "Canada/USA"),
    ("united kingdom", "Europe"),
    ("england", "Europe"),
    ("scotland", "Europe"),
    ("france", "Europe"),
    ("italy", "Europe"),
    ("spain", "Europe"),
    ("netherlands", "Europe"),
    ("belgium", "Europe"),
    ("austria", "Europe"),
    ("sweden", "Europe"),
    ("norway", "Europe"),
    ("poland", "Europe"),
    ("portugal", "Europe"),
    ("ireland", "Europe"),
    ("switzerland", "Europe"),
)
LANGUAGES = {
    "en": "English",
    "ur": "اردو",
    "ar": "العربية",
    "de": "Deutsch",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "tr": "Turkish",
    "pt": "Portuguese",
    "zh": "Chinese",
    "ja": "Japanese",
}
DEFAULT_FAQS = [
    ("How do I choose the right size?", "Each product shows available colours and sizes with remaining stock. Choose a colour first, then a size."),
    ("Which currencies can I use?", "Prices can be viewed in EUR, USD, or PKR. Choose your preferred currency in the header."),
    ("Can I check a market price first?", "Yes. Product pages include Check price on other platforms when Amazon, Etsy or eBay links are available."),
    ("How can I contact support?", "Use the Contact page and our team will receive your message through the secure backend."),
]

PRODUCTS = [
    ("Slim-Fit Stretch Denim Jeans", "Pants", 3499, 4200, "-17% OFF", 4.8, 32, "AR-PNT-01", "https://images.unsplash.com/photo-1542272604-780c36856842?w=800", "30,32,34,36", "Dark Indigo,Washed Black", "Premium cotton denim with comfortable stretch and reinforced stitching.", 20),
    ("Tailored Cotton Chino Trousers", "Pants", 2899, 3500, "HOT", 4.7, 19, "AR-PNT-02", "https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=800", "30,32,34", "Olive Green,Khaki Tan", "Modern tapered chinos made from combed cotton twill.", 20),
    ("Royal Oxford Formal Cotton Shirt", "Shirts", 2299, 2800, "NEW", 4.9, 54, "AR-SHR-01", "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=800", "Small,Medium,Large,Extra Large", "Pure White,Sky Blue", "Luxury long-staple cotton oxford shirt with an executive collar.", 20),
    ("Modern Stretch Pique Polo Shirt", "Shirts", 1899, 2200, "POPULAR", 4.5, 21, "AR-SHR-02", "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=800", "Medium,Large,Extra Large", "Navy Blue,Maroon", "Breathable knit polo with active stretch and moisture control.", 20),
    ("Genuine Cowhide Biker Leather Jacket", "Jackets", 8999, 11500, "-22% OFF", 5.0, 88, "AR-JKT-01", "https://images.unsplash.com/photo-1551028719-00167b16eac5?w=800", "Medium,Large,Extra Large,Double Extra Large", "Obsidian Black,Antique Brown", "Full-grain cowhide jacket with YKK zips and quilted lining.", 20),
    ("Tactical Windproof Bomber Jacket", "Jackets", 5499, 6500, "FEATURED", 4.6, 14, "AR-JKT-02", "https://images.unsplash.com/photo-1548883354-7622d03aca27?w=800", "Small,Medium,Large", "Army Green,Matte Black", "Water-repellent shell with thermal insulation and storm cuffs.", 20),
    ("Minimalist RFID Leather Bifold Wallet", "Wallets", 1499, 1999, "BESTSELLER", 4.8, 43, "AR-WLT-01", "https://images.unsplash.com/photo-1627123424574-724758594e93?w=800", "Standard Pocket", "Tan Brown,Classic Black", "Handcrafted leather wallet with RFID protection.", 20),
    ("Luxury Structured Designer Purse", "Purses", 4999, 6200, "-19% OFF", 4.9, 37, "AR-PRS-01", "https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=800", "Medium Tote", "Burgundy Red,Nude Beige", "Genuine leather handbag with gold-tone hardware.", 20),
    ("Reversible Full-Grain Leather Belt", "Belts", 1299, 1650, "2-IN-1", 4.7, 29, "AR-BLT-01", "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=800", "32-34 Waist,36-38 Waist", "Black/Brown Reversible", "Dual-sided leather belt with rotatable alloy buckle.", 20),
    ("Velocity Knit Running Shoes", "Shoes", 5999, 7200, "NEW", 4.9, 61, "AR-SHO-01", "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=800", "40,41,42,43,44", "Crimson Red,Midnight Black", "Responsive knit running shoes with cushioned grip sole.", 20),
    ("Classic Leather Court Sneakers", "Shoes", 6799, 7900, "TOP RATED", 4.8, 47, "AR-SHO-02", "https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77?w=800", "39,40,41,42,43", "White/Red,Black/Red", "Premium everyday court sneakers with soft leather upper.", 20),
]

GALLERY_IMAGES = {
    "Shoes": [
        "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=1000",
        "https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77?w=1000",
        "https://images.unsplash.com/photo-1460353581641-37baddab0fa2?w=1000",
    ],
    "Pants": [
        "https://images.unsplash.com/photo-1542272604-780c36856842?w=1000",
        "https://images.unsplash.com/photo-1473966968600-fa801b869a1a?w=1000",
    ],
    "Shirts": [
        "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=1000",
        "https://images.unsplash.com/photo-1603252109303-2751441dd157?w=1000",
    ],
    "Jackets": [
        "https://images.unsplash.com/photo-1551028719-00167b16eac5?w=1000",
        "https://images.unsplash.com/photo-1548883354-7622d03aca27?w=1000",
    ],
}


class CursorResult:
    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)


class Database:
    """Thin PostgreSQL wrapper that keeps SQLite-style ? placeholders."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        cursor = self._conn.execute(sql.replace("?", "%s"), params or ())
        lastrowid = None
        stripped = sql.lstrip().upper()
        if stripped.startswith("INSERT") and "RETURNING" not in stripped and "ON CONFLICT" not in stripped:
            self._conn.execute("SAVEPOINT lastval_lookup")
            try:
                lastrowid = self._conn.execute("SELECT lastval() AS id").fetchone()["id"]
                self._conn.execute("RELEASE SAVEPOINT lastval_lookup")
            except Exception:
                self._conn.execute("ROLLBACK TO SAVEPOINT lastval_lookup")
                lastrowid = None
        return CursorResult(cursor, lastrowid)

    def executemany(self, sql, seq_of_params):
        with self._conn.cursor() as cursor:
            cursor.executemany(sql.replace("?", "%s"), seq_of_params)
        return self

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_db():
    if "db" not in g:
        try:
            conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        except psycopg.OperationalError as error:
            raise RuntimeError(
                "Could not connect to PostgreSQL. Start the database "
                "(docker compose up -d) and check DATABASE_URL in .env."
            ) from error
        g.db = Database(conn)
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def table_exists(table):
    row = get_db().execute(
        """
        SELECT 1 AS ok
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = ?
        """,
        (table,),
    ).fetchone()
    return bool(row)


def ensure_columns(table, columns):
    if not table_exists(table):
        return
    db = get_db()
    existing = {
        row["column_name"]
        for row in db.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            """,
            (table,),
        ).fetchall()
    }
    for column, definition in columns.items():
        if column not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def colors_from_legacy(colors_text, stock):
    names = [part.strip() for part in (colors_text or "").split(",") if part.strip()]
    if not names:
        return [{"name": "Default", "quantity": int(stock or 0)}]
    per = max(int(stock or 0) // len(names), 0)
    remainder = max(int(stock or 0) - per * len(names), 0)
    colors = [{"name": name, "quantity": per} for name in names[:10]]
    if colors:
        colors[0]["quantity"] += remainder
    return colors


def sizes_from_legacy(sizes_text):
    return [part.strip() for part in (sizes_text or "").split(",") if part.strip()]


def catalog_sizes_for(product_type):
    return SIZE_MAP.get(product_type, CLOTHES_SIZES)


def clean_size_name(raw):
    extra = (raw or "").strip()[:12]
    if not extra:
        return ""
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789./+-")
    if any(char not in allowed for char in extra):
        return ""
    return extra


def parse_size_form():
    product_type = request.form.get("product_type", "Clothes")
    allowed = catalog_sizes_for(product_type)
    sizes = [size for size in allowed if request.form.get(f"size_{size}")]
    extras = list(request.form.getlist("extra_size"))
    extras.extend((request.form.get("custom_sizes") or "").split(","))
    extras.extend((request.form.get("custom_shoe_sizes") or "").split(","))
    for extra in extras:
        extra = clean_size_name(extra)
        if extra and extra not in sizes:
            sizes.append(extra)
    return sizes


def parse_color_form():
    selected_sizes = parse_size_form()
    colors = []
    for index in range(1, 11):
        name = request.form.get(f"color_name_{index}", "").strip()[:40]
        if not name:
            continue
        size_stock = {}
        for size in selected_sizes:
            try:
                size_stock[size] = max(int(request.form.get(f"color_stock_{index}_{size}", 0) or 0), 0)
            except ValueError:
                size_stock[size] = 0
        colors.append({"name": name, "quantity": sum(size_stock.values()), "sizes": size_stock})
    return colors


def parse_keyword_list(raw, limit=10, hashtag=False):
    items = []
    seen = set()
    for part in (raw or "").split(","):
        word = part.strip()[:40]
        if not word:
            continue
        if hashtag:
            word = word.lstrip("#").replace(" ", "")
            if not word:
                continue
            word = f"#{word}"
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(word)
        if len(items) >= limit:
            break
    return items


def keywords_from_stored(raw):
    if isinstance(raw, (list, tuple)):
        return [str(part).strip() for part in raw if str(part).strip()]
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def parse_marketplace_urls():
    return {
        "amazon_url": request.form.get("amazon_url", "").strip()[:500],
        "etsy_url": request.form.get("etsy_url", "").strip()[:500],
        "ebay_url": request.form.get("ebay_url", "").strip()[:500],
    }


def save_product_images(sku, slots=10):
    folder = os.path.join(UPLOAD_ROOT, sku)
    os.makedirs(folder, exist_ok=True)
    for index in range(1, slots + 1):
        field = "main_image" if index == 1 else f"image_{index}"
        target = "main.jpg" if index == 1 else f"{index}.jpg"
        uploaded = request.files.get(field)
        if not uploaded or not uploaded.filename:
            continue
        extension = secure_filename(uploaded.filename).rsplit(".", 1)[-1].lower() if "." in uploaded.filename else ""
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("Images must be JPG, JPEG, PNG, or WEBP files.")
        uploaded.save(os.path.join(folder, target))


def save_listing_images(listing_id):
    folder = os.path.join(UPLOAD_ROOT, f"listing-{listing_id}")
    os.makedirs(folder, exist_ok=True)
    saved = []
    for index in range(1, 4):
        uploaded = request.files.get(f"image_{index}")
        if not uploaded or not uploaded.filename:
            continue
        extension = secure_filename(uploaded.filename).rsplit(".", 1)[-1].lower() if "." in uploaded.filename else ""
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("Images must be JPG, JPEG, PNG, or WEBP files.")
        filename = f"{index}.jpg"
        uploaded.save(os.path.join(folder, filename))
        saved.append(f"/static/images/listing-{listing_id}/{filename}")
    return saved


def init_db():
    db = get_db()
    statements = [
        """
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price DOUBLE PRECISION NOT NULL,
            old_price DOUBLE PRECISION,
            badge TEXT,
            rating DOUBLE PRECISION DEFAULT 0,
            reviews_count INTEGER DEFAULT 0,
            sku TEXT UNIQUE,
            image TEXT,
            sizes TEXT,
            colors TEXT,
            description TEXT,
            stock INTEGER NOT NULL DEFAULT 20,
            active INTEGER DEFAULT 1,
            colors_json TEXT,
            sizes_json TEXT,
            amazon_url TEXT,
            etsy_url TEXT,
            ebay_url TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id),
            name TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS listings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            seller_name TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            price DOUBLE PRECISION NOT NULL,
            description TEXT NOT NULL,
            images_json TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            customer_name TEXT NOT NULL,
            email TEXT NOT NULL,
            address TEXT NOT NULL,
            country TEXT NOT NULL DEFAULT 'Germany',
            payment_method TEXT NOT NULL DEFAULT 'pay_on_delivery',
            currency TEXT NOT NULL,
            total DOUBLE PRECISION NOT NULL,
            shipping DOUBLE PRECISION NOT NULL DEFAULT 0,
            items TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS shipping_rates (
            zone TEXT PRIMARY KEY,
            unit TEXT NOT NULL,
            under_value DOUBLE PRECISION NOT NULL,
            over_value DOUBLE PRECISION NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS main_categories (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sub_categories (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            product_type TEXT NOT NULL,
            UNIQUE (name, product_type)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS pl_users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS faqs (
            id SERIAL PRIMARY KEY,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """,
    ]
    for statement in statements:
        db.execute(statement)
    db.commit()

    ensure_columns(
        "orders",
        {
            "country": "TEXT NOT NULL DEFAULT 'Germany'",
            "payment_method": "TEXT NOT NULL DEFAULT 'pay_on_delivery'",
            "shipping": "DOUBLE PRECISION NOT NULL DEFAULT 0",
        },
    )
    ensure_columns(
        "products",
        {
            "stock": "INTEGER NOT NULL DEFAULT 20",
            "colors_json": "TEXT",
            "sizes_json": "TEXT",
            "amazon_url": "TEXT",
            "etsy_url": "TEXT",
            "ebay_url": "TEXT",
            "discount_percent": "DOUBLE PRECISION NOT NULL DEFAULT 0",
            "weight": "DOUBLE PRECISION NOT NULL DEFAULT 0",
            "shipping_json": "TEXT",
            "pakistan_price": "DOUBLE PRECISION NOT NULL DEFAULT 0",
            "pakistan_discount_percent": "DOUBLE PRECISION NOT NULL DEFAULT 0",
            "condition": "TEXT NOT NULL DEFAULT 'new_with_tag'",
            "main_category": "TEXT NOT NULL DEFAULT 'Unisex'",
            "sub_category": "TEXT",
            "product_type": "TEXT NOT NULL DEFAULT 'Clothes'",
            "size_group": "TEXT NOT NULL DEFAULT 'Unisex'",
            "packing_weight": "DOUBLE PRECISION NOT NULL DEFAULT 0",
            "region_visibility": "TEXT NOT NULL DEFAULT 'all'",
            "product_tags": "TEXT",
            "product_hashtags": "TEXT",
            "likes": "INTEGER NOT NULL DEFAULT 0",
            "featured": "INTEGER NOT NULL DEFAULT 0",
            "deal_of_week": "INTEGER NOT NULL DEFAULT 0",
            "listed_by": "TEXT NOT NULL DEFAULT 'admin'",
        },
    )
    ensure_columns("users", {"country": "TEXT"})
    ensure_columns("contacts", {"user_id": "INTEGER"})
    ensure_columns(
        "listings",
        {
            "user_id": "INTEGER",
            "images_json": "TEXT",
            "status": "TEXT NOT NULL DEFAULT 'pending'",
            "reviewed_at": "TEXT",
            "product_id": "INTEGER",
        },
    )
    ensure_columns(
        "product_listings",
        {
            "picture_main": "TEXT",
            "picture_2": "TEXT",
            "picture_3": "TEXT",
            "pictures_extra": "TEXT[]",
        },
    )

    if not db.execute("SELECT 1 AS ok FROM categories LIMIT 1").fetchone():
        db.executemany("INSERT INTO categories (name) VALUES (?)", [(name,) for name in DEFAULT_CATEGORIES])
    if not db.execute("SELECT 1 AS ok FROM main_categories LIMIT 1").fetchone():
        db.executemany("INSERT INTO main_categories (name) VALUES (?)", [(name,) for name in MAIN_CATEGORIES])
    if not db.execute("SELECT 1 AS ok FROM sub_categories LIMIT 1").fetchone():
        db.executemany(
            "INSERT INTO sub_categories (name, product_type) VALUES (?,?)",
            [(name, product_type) for product_type, names in SUB_CATEGORIES.items() for name in names],
        )
    if not db.execute("SELECT 1 AS ok FROM faqs LIMIT 1").fetchone():
        db.executemany(
            "INSERT INTO faqs (question, answer, sort_order) VALUES (?,?,?)",
            [(question, answer, index) for index, (question, answer) in enumerate(DEFAULT_FAQS)],
        )

    for zone in DEFAULT_SHIPPING_ZONES:
        db.execute(
            """
            INSERT INTO shipping_rates (zone, unit, under_value, over_value)
            VALUES (?,?,?,?)
            ON CONFLICT (zone) DO NOTHING
            """,
            (zone["name"], zone["unit"], zone["under"], zone["over"]),
        )

    if not db.execute("SELECT 1 AS ok FROM products LIMIT 1").fetchone():
        for row in PRODUCTS:
            name, category, price, old_price, badge, rating, reviews_count, sku, image, sizes, colors, description, stock = row
            color_rows = colors_from_legacy(colors, stock)
            size_rows = sizes_from_legacy(sizes)
            db.execute(
                """
                INSERT INTO products (
                    name, category, price, old_price, badge, rating, reviews_count, sku, image,
                    sizes, colors, description, stock, colors_json, sizes_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    name,
                    category,
                    price,
                    old_price,
                    badge,
                    rating,
                    reviews_count,
                    sku,
                    image,
                    sizes,
                    colors,
                    description,
                    stock,
                    json.dumps(color_rows),
                    json.dumps(size_rows),
                ),
            )
        db.executemany(
            "INSERT INTO reviews (product_id,name,rating,body,created_at) VALUES (?,?,?,?,?)",
            [
                (10, "Sarah Williams", 5, "The fit is spot-on and the red colour looks even better in person.", "2026-08-10"),
                (10, "Daniel Cooper", 5, "Light, comfortable and genuinely supportive for daily runs.", "2026-08-12"),
                (5, "Ahmed Hassan", 5, "Excellent stitching and a premium leather finish.", "2026-08-08"),
            ],
        )

    for row in db.execute("SELECT id, sizes, colors, stock, colors_json, sizes_json FROM products").fetchall():
        updates = {}
        if not row["colors_json"]:
            updates["colors_json"] = json.dumps(colors_from_legacy(row["colors"], row["stock"]))
        if not row["sizes_json"]:
            updates["sizes_json"] = json.dumps(sizes_from_legacy(row["sizes"]))
        if updates:
            db.execute(
                f"UPDATE products SET {', '.join(f'{key}=?' for key in updates)} WHERE id=?",
                (*updates.values(), row["id"]),
            )
    db.commit()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in or create a profile to continue.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Please sign in to access the admin dashboard.", "error")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def setup():
    if not app.config["DB_INITIALIZED"]:
        init_db()
        app.config["DB_INITIALIZED"] = True
    session.setdefault("currency", "EUR")
    session.setdefault("language", "en")
    session.setdefault("cart", {})
    session.setdefault("liked", [])


@app.context_processor
def helpers():
    user = current_user()
    return {
        "currencies": CURRENCIES,
        "languages": LANGUAGES,
        "currency": session["currency"],
        "language": session["language"],
        "pakistan_customer": pakistan_customer(),
        "customer_region": customer_zone_name(),
        "customer_location_source": customer_location()["source"],
        "shipping_regions": ZONE_NAMES,
        "cart_count": sum(session["cart"].values()),
        "is_admin": session.get("is_admin", False),
        "is_pl": session.get("is_pl", False),
        "pl_display_name": session.get("pl_display_name", ""),
        "current_user": user,
        "liked_ids": liked_product_ids(),
        "shop_nav": shop_category_tree(),
        "selected_main": request.args.get("main", ""),
        "selected_sub": request.args.get("sub", ""),
    }


def product(row):
    item = dict(row) if not isinstance(row, dict) else dict(row)
    try:
        item["color_rows"] = json.loads(item.get("colors_json") or "[]")
    except json.JSONDecodeError:
        item["color_rows"] = colors_from_legacy(item.get("colors"), item.get("stock"))
    if not isinstance(item.get("color_rows"), list):
        item["color_rows"] = colors_from_legacy(item.get("colors"), item.get("stock"))
    item["color_rows"] = [entry for entry in item["color_rows"] if isinstance(entry, dict)]
    try:
        item["size_rows"] = json.loads(item.get("sizes_json") or "[]")
    except json.JSONDecodeError:
        item["size_rows"] = sizes_from_legacy(item.get("sizes"))
    if not isinstance(item.get("size_rows"), list):
        item["size_rows"] = sizes_from_legacy(item.get("sizes"))
    for entry in item["color_rows"]:
        if not isinstance(entry.get("sizes"), dict):
            sizes = item["size_rows"] or ["Standard"]
            quantity = max(int(entry.get("quantity", 0)), 0)
            per_size, remainder = divmod(quantity, len(sizes))
            entry["sizes"] = {
                size: per_size + (1 if index < remainder else 0)
                for index, size in enumerate(sizes)
            }
        entry["quantity"] = sum(max(int(value or 0), 0) for value in entry["sizes"].values())
    item["sizes"] = [str(size) for size in item["size_rows"] if str(size).strip()]
    item["size_rows"] = item["sizes"]
    item["colors"] = [entry.get("name") or "Default" for entry in item["color_rows"]]
    item["stock"] = sum(int(entry.get("quantity", 0) or 0) for entry in item["color_rows"])
    sku = item.get("sku") or ""
    image_folder = os.path.join(UPLOAD_ROOT, sku) if sku else ""
    local_gallery = []
    if image_folder:
        for filename in ["main.jpg"] + [f"{index}.jpg" for index in range(2, 11)]:
            if os.path.exists(os.path.join(image_folder, filename)):
                local_gallery.append(f"/static/images/{sku}/{filename}")
    fallback_image = item.get("image") or ""
    item["gallery"] = [url for url in (local_gallery or ([fallback_image] + [image for image in GALLERY_IMAGES.get(item["category"], []) if image != fallback_image][:2])) if url]
    item["image"] = item["gallery"][0] if item["gallery"] else fallback_image
    item["amazon_url"] = item.get("amazon_url") or ""
    item["etsy_url"] = item.get("etsy_url") or ""
    item["ebay_url"] = item.get("ebay_url") or ""
    try:
        discount = max(0.0, min(100.0, float(item.get("discount_percent") or 0)))
    except (TypeError, ValueError):
        discount = 0.0
    try:
        weight = max(0.0, float(item.get("weight") or 0))
    except (TypeError, ValueError):
        weight = 0.0
    try:
        pakistan_discount = max(0.0, min(100.0, float(item.get("pakistan_discount_percent") or 0)))
    except (TypeError, ValueError):
        pakistan_discount = 0.0
    original_price = float(item.get("price") or 0)
    try:
        pakistan_original = max(0.0, float(item.get("pakistan_price") or 0))
    except (TypeError, ValueError):
        pakistan_original = 0.0
    item["discount_percent"] = discount
    item["pakistan_discount_percent"] = pakistan_discount
    item["weight"] = weight
    item["original_price"] = original_price
    item["price"] = round(original_price * (100 - discount) / 100, 2)
    item["pakistan_original_price"] = pakistan_original
    item["pakistan_price"] = round(pakistan_original * (100 - pakistan_discount) / 100, 2)
    if pakistan_customer() and pakistan_original > 0:
        item["display_original_price"] = pakistan_original
        item["display_price"] = item["pakistan_price"]
        item["display_discount_percent"] = pakistan_discount
    else:
        item["display_original_price"] = original_price
        item["display_price"] = item["price"]
        item["display_discount_percent"] = discount
    item["shipping"] = normalize_product_shipping(item.get("shipping_json"))
    try:
        packing_weight = max(0.0, float(item.get("packing_weight") or 0))
    except (TypeError, ValueError):
        packing_weight = 0.0
    item["packing_weight"] = packing_weight
    item["ship_weight"] = weight + packing_weight
    item["product_type"] = item.get("product_type") or inferred_product_type(item.get("category"))
    item["main_category"] = item.get("main_category") or "Unisex"
    item["sub_category"] = item.get("sub_category") or item.get("category") or ""
    item["size_group"] = item.get("size_group") or "Unisex"
    item["condition"] = item.get("condition") or "new_with_tag"
    item["condition_label"] = CONDITION_LABELS.get(item["condition"], "New with tag")
    item["region_visibility"] = item.get("region_visibility") or "all"
    item["has_marketplace_links"] = bool(item["amazon_url"] or item["etsy_url"] or item["ebay_url"])
    item["product_tags"] = keywords_from_stored(item.get("product_tags"))
    item["product_hashtags"] = keywords_from_stored(item.get("product_hashtags"))
    item["tags_text"] = ", ".join(item["product_tags"])
    item["hashtags_text"] = ", ".join(item["product_hashtags"])
    try:
        item["likes"] = max(0, int(item.get("likes") or 0))
    except (TypeError, ValueError):
        item["likes"] = 0
    try:
        item["rating"] = max(0.0, min(5.0, float(item.get("rating") or 0)))
    except (TypeError, ValueError):
        item["rating"] = 0.0
    item["price_eur"] = round(original_price / EUR_TO_STORE, 2) if original_price else 0
    try:
        item["featured"] = 1 if int(item.get("featured") or 0) else 0
    except (TypeError, ValueError):
        item["featured"] = 0
    try:
        item["deal_of_week"] = 1 if int(item.get("deal_of_week") or 0) else 0
    except (TypeError, ValueError):
        item["deal_of_week"] = 0
    item["stars"] = star_display(item["rating"])
    item["listed_by"] = (item.get("listed_by") or "admin").strip() or "admin"
    return item


def star_display(rating):
    try:
        filled = int(round(float(rating or 0)))
    except (TypeError, ValueError):
        filled = 0
    filled = max(0, min(5, filled))
    return "★" * filled + "☆" * (5 - filled)


def liked_product_ids():
    ids = []
    for value in session.get("liked") or []:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def listing_images(listing):
    try:
        images = json.loads((listing or {}).get("images_json") or "[]")
    except (TypeError, json.JSONDecodeError, AttributeError):
        images = []
    if not isinstance(images, list):
        return []
    return [url for url in images if url]


def listing_view(row):
    item = dict(row) if not isinstance(row, dict) else dict(row)
    item["images"] = listing_images(item)
    item["status"] = item.get("status") or "pending"
    return item


def parse_order_items(raw):
    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    for loader in (json.loads, ast.literal_eval):
        try:
            data = loader(raw)
        except (TypeError, ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(data, list):
            return data
    return []


def listing_category_fields(category):
    name = (category or "").strip()
    subs = load_sub_categories()
    for product_type, names in subs.items():
        if name == product_type:
            return product_type, names[0]
        if name in names:
            return product_type, name
    return "Clothes", name or "Tops"


def approve_seller_listing(listing_id):
    db = get_db()
    listing = db.execute("SELECT * FROM listings WHERE id=?", (listing_id,)).fetchone()
    if not listing:
        raise ValueError("Listing not found.")
    if listing.get("status") == "approved" and listing.get("product_id"):
        return listing["product_id"]
    images = listing_images(listing)
    if not images:
        raise ValueError("This listing has no images to publish.")
    product_type, sub_category = listing_category_fields(listing["category"])
    sku = f"SELL-{listing_id}"
    if db.execute("SELECT id FROM products WHERE sku=?", (sku,)).fetchone():
        sku = f"SELL-{listing_id}-{int(datetime.utcnow().timestamp())}"
    store_price = round(max(0.01, float(listing["price"] or 0)) * 278, 2)
    color_rows = [{"name": "Default", "quantity": 1, "sizes": {"Standard": 1}}]
    size_rows = ["Standard"]
    cursor = db.execute(
        """
        INSERT INTO products (
            name,category,price,rating,reviews_count,likes,sku,image,sizes,colors,
            description,stock,active,colors_json,sizes_json,condition,main_category,
            sub_category,product_type,size_group,region_visibility,featured,deal_of_week,listed_by
        ) VALUES (?,?,?,0,0,0,?,?,?,?,?,1,1,?,?,?,?,?,?,?,?,0,0,?)
        RETURNING id
        """,
        (
            listing["title"][:100],
            sub_category,
            store_price,
            sku,
            images[0],
            "Standard",
            "Default",
            listing["description"][:3000],
            json.dumps(color_rows),
            json.dumps(size_rows),
            "used",
            "Unisex",
            sub_category,
            product_type,
            "Unisex",
            "all",
            "admin",
        ),
    )
    product_id = cursor.fetchone()["id"]
    dest = os.path.join(UPLOAD_ROOT, sku)
    os.makedirs(dest, exist_ok=True)
    for index, url in enumerate(images[:10], start=1):
        src = os.path.join(BASE_DIR, str(url).lstrip("/"))
        if not os.path.exists(src):
            continue
        target = "main.jpg" if index == 1 else f"{index}.jpg"
        shutil.copy2(src, os.path.join(dest, target))
    db.execute(
        "UPDATE listings SET status=?, reviewed_at=?, product_id=? WHERE id=?",
        ("approved", datetime.utcnow().isoformat(), product_id, listing_id),
    )
    db.commit()
    return product_id


def fetch_product(product_id):
    row = get_db().execute("SELECT * FROM products WHERE id=? AND active=1", (product_id,)).fetchone()
    if not row:
        abort(404)
    item = product(row)
    if not item_visible_in_region(item):
        abort(404)
    return item


def inferred_product_type(category):
    name = category or ""
    subs = load_sub_categories()
    for product_type, options in subs.items():
        if name == product_type or name in options:
            return product_type
    if name == "Shoes" or name in SUB_CATEGORIES["Shoes"]:
        return "Shoes"
    if name in SUB_CATEGORIES["Accessories"] or name in {"Wallets", "Purses", "Belts"}:
        return "Accessories"
    return "Clothes"


def item_visible_in_region(item):
    visibility = item.get("region_visibility") or "all"
    if visibility == "all":
        return True
    if pakistan_customer():
        return visibility == "pakistan"
    return visibility == "europe_america"


def visible_catalog(rows):
    return [item for item in (product(row) for row in rows) if item_visible_in_region(item)]


def product_sub_category(item):
    return item.get("sub_category") or item.get("category") or ""


def shop_category_tree(items=None):
    if items is None:
        items = visible_catalog(get_db().execute("SELECT * FROM products WHERE active=1").fetchall())
    mains = load_main_categories()
    grouped = {name: [] for name in mains}
    fallback = mains[0] if mains else "Unisex"
    for item in items:
        main = item.get("main_category") if item.get("main_category") in grouped else fallback
        if main not in grouped:
            continue
        sub = product_sub_category(item)
        if sub and sub not in grouped[main]:
            grouped[main].append(sub)
    return [{"name": name, "subs": sorted(grouped[name])} for name in mains]


def matches_shop_filter(item, main="", sub="", category=""):
    item_main = item.get("main_category") or ""
    item_sub = product_sub_category(item)
    if main and item_main != main:
        return False
    if sub and item_sub != sub:
        return False
    if category and category != "All":
        return category in {item.get("category"), item_sub, item.get("product_type"), item_main}
    return True


def client_ip():
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or request.headers.get("X-Real-IP") or request.remote_addr or ""


def is_local_ip(ip):
    return (
        not ip
        or ip in {"127.0.0.1", "::1", "localhost"}
        or ip.startswith("127.")
        or ip.startswith("192.168.")
        or ip.startswith("10.")
        or ip.startswith("172.16.")
    )


def lookup_ip_country():
    cached = session.get("ip_country")
    if cached is not None:
        return cached
    cf_country = (request.headers.get("CF-IPCountry") or "").upper()
    if cf_country and cf_country not in {"XX", "T1"}:
        session["ip_country"] = cf_country
        return cf_country
    ip = client_ip()
    if is_local_ip(ip):
        session["ip_country"] = ""
        return ""
    try:
        url = f"http://ip-api.com/json/{ip}?fields=status,countryCode"
        with urllib.request.urlopen(url, timeout=1.5) as response:
            data = json.loads(response.read().decode("utf-8"))
        session["ip_country"] = (data.get("countryCode") or "").upper() if data.get("status") == "success" else ""
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
        session["ip_country"] = ""
    return session.get("ip_country") or ""


def zone_from_address(text):
    blob = f" {(text or '').lower()} "
    for hint, zone in ADDRESS_ZONE_HINTS:
        if f" {hint} " in blob or blob.strip().endswith(hint) or blob.strip().startswith(hint):
            return zone
        if hint in blob:
            return zone
    return ""


def zone_from_accept_language():
    header = request.headers.get("Accept-Language") or ""
    for part in header.split(","):
        code = part.split(";")[0].strip().lower()
        if code.startswith("ur") or code.endswith("-pk"):
            return "Pakistan"
        if code.startswith("de") or code.endswith("-de"):
            return "Germany"
        if code.endswith("-us") or code.endswith("-ca"):
            return "Canada/USA"
        lang = code.split("-")[0]
        if lang in LANGUAGE_TO_ZONE:
            return LANGUAGE_TO_ZONE[lang]
    return ""


def apply_region(zone):
    if zone not in ZONE_NAMES:
        return
    session["region"] = zone
    session["currency"] = ZONE_CURRENCY.get(zone, session.get("currency", "EUR"))
    if zone == "Pakistan":
        session["language"] = session.get("language") if session.get("language") == "ur" else session.get("language", "en")


def customer_location():
    if not has_request_context():
        return {"zone": "Europe", "source": "default"}
    if getattr(g, "customer_location", None):
        return g.customer_location
    address_zone = zone_from_address(request.form.get("address", ""))
    profile_zone = ""
    user = current_user()
    if user:
        profile_zone = (user.get("country") or "").strip()
        if profile_zone not in ZONE_NAMES:
            profile_zone = ""
    explicit = (session.get("region") or "").strip()
    if explicit not in ZONE_NAMES:
        explicit = ""
    ip_code = lookup_ip_country()
    ip_zone = COUNTRY_CODE_TO_ZONE.get(ip_code, "")
    language_zone = LANGUAGE_TO_ZONE.get(session.get("language"), "")
    accept_zone = zone_from_accept_language()
    currency_zone = CURRENCY_TO_ZONE.get(session.get("currency"), "")
    if session.get("language") == "de" and session.get("currency") == "EUR":
        currency_zone = "Germany"
    if address_zone:
        result = {"zone": address_zone, "source": "delivery address"}
    elif explicit:
        result = {"zone": explicit, "source": "your selected region"}
    elif profile_zone:
        result = {"zone": profile_zone, "source": "your profile"}
    elif ip_zone:
        result = {"zone": ip_zone, "source": "your IP location"}
    elif accept_zone:
        result = {"zone": accept_zone, "source": "browser language"}
    elif language_zone:
        result = {"zone": language_zone, "source": "site language"}
    elif currency_zone:
        result = {"zone": currency_zone, "source": "currency"}
    else:
        result = {"zone": "Europe", "source": "default"}
    g.customer_location = result
    return result


def customer_zone_name():
    return customer_location()["zone"]


def pakistan_customer():
    return customer_zone_name() == "Pakistan"


def category_names():
    return [row["name"] for row in get_db().execute("SELECT name FROM categories ORDER BY name").fetchall()]


def load_main_categories():
    if "main_categories" not in g:
        try:
            rows = get_db().execute("SELECT name FROM main_categories ORDER BY id").fetchall()
            names = [row["name"] for row in rows]
            g.main_categories = names or list(MAIN_CATEGORIES)
        except Exception:
            get_db().rollback()
            g.main_categories = list(MAIN_CATEGORIES)
    return g.main_categories


def load_sub_categories():
    if "sub_categories" not in g:
        grouped = {product_type: [] for product_type in PRODUCT_TYPES}
        try:
            rows = get_db().execute("SELECT name, product_type FROM sub_categories ORDER BY id").fetchall()
            for row in rows:
                grouped.setdefault(row["product_type"], []).append(row["name"])
        except Exception:
            get_db().rollback()
            rows = []
        if not any(grouped.values()):
            grouped = {key: list(value) for key, value in SUB_CATEGORIES.items()}
        g.sub_categories = grouped
    return g.sub_categories


def staff_home():
    if session.get("is_admin"):
        return url_for("admin_dashboard")
    if session.get("is_pl"):
        return url_for("pl_dashboard")
    return url_for("home")


def product_image_slots(item=None):
    sku = (item or {}).get("sku") or ""
    slots = []
    for index in range(1, 11):
        filename = "main.jpg" if index == 1 else f"{index}.jpg"
        path = os.path.join(UPLOAD_ROOT, sku, filename) if sku else ""
        url = ""
        if sku and os.path.exists(path):
            url = f"/static/images/{sku}/{filename}?v={int(os.path.getmtime(path))}"
        slots.append(
            {
                "index": index,
                "field": "main_image" if index == 1 else f"image_{index}",
                "label": "Image 1 (main)" if index == 1 else f"Image {index}",
                "url": url,
            }
        )
    return slots


def extra_sizes_of(item=None):
    if not item:
        return []
    catalog = set(catalog_sizes_for(item.get("product_type") or "Clothes"))
    extras = []
    for size in item.get("size_rows") or []:
        if size not in catalog and size not in extras:
            extras.append(size)
    return extras


def empty_color_slots(existing=None, extra_sizes=None):
    existing = existing or []
    extra_sizes = extra_sizes or []
    all_sizes = list(ALL_CATALOG_SIZES)
    for size in extra_sizes:
        if size not in all_sizes:
            all_sizes.append(size)
    slots = [{"name": "", "sizes": {size: "" for size in all_sizes}} for _ in range(10)]
    for index, entry in enumerate(existing[:10]):
        slots[index] = {
            "name": entry.get("name", ""),
            "sizes": {size: entry.get("sizes", {}).get(size, "") for size in all_sizes},
        }
    return slots


def empty_size_slots(existing=None, product_type="Clothes"):
    existing = existing or []
    return [{"name": size, "selected": size in existing} for size in catalog_sizes_for(product_type)]


def size_slots_by_type(existing=None):
    existing = existing or []
    return {product_type: empty_size_slots(existing, product_type) for product_type in PRODUCT_TYPES}


def default_product_shipping():
    return {
        zone["key"]: {
            "name": zone["name"],
            "unit": zone["unit"],
            "under": zone["under"],
            "over": zone["over"],
            "express_under": zone["express_under"],
            "express_over": zone["express_over"],
        }
        for zone in DEFAULT_SHIPPING_ZONES
    }


def normalize_product_shipping(raw):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except json.JSONDecodeError:
            raw = {}
    raw = raw or {}
    defaults = default_product_shipping()
    shipping = {}
    for zone in DEFAULT_SHIPPING_ZONES:
        entry = raw.get(zone["key"]) or raw.get(zone["name"]) or {}
        fallback = defaults[zone["key"]]
        values = {}
        for field in ("under", "over", "express_under", "express_over"):
            try:
                values[field] = max(0.0, float(entry.get(field, fallback[field])))
            except (TypeError, ValueError):
                values[field] = fallback[field]
        shipping[zone["key"]] = {
            "name": zone["name"],
            "key": zone["key"],
            "unit": zone["unit"],
            **values,
            "under_label": shipping_label(values["under"], zone["unit"]),
            "over_label": shipping_label(values["over"], zone["unit"]),
            "express_under_label": shipping_label(values["express_under"], zone["unit"]),
            "express_over_label": shipping_label(values["express_over"], zone["unit"]),
            "under_store": store_shipping_amount(values["under"], zone["unit"]),
            "over_store": store_shipping_amount(values["over"], zone["unit"]),
            "express_under_store": store_shipping_amount(values["express_under"], zone["unit"]),
            "express_over_store": store_shipping_amount(values["express_over"], zone["unit"]),
        }
    return shipping


def product_shipping_slots(existing=None):
    return list(normalize_product_shipping(existing).values())


def parse_product_shipping_form():
    shipping = {}
    for zone in DEFAULT_SHIPPING_ZONES:
        values = {}
        for field in ("under", "over", "express_under", "express_over"):
            try:
                values[field] = max(0.0, float(request.form.get(f"ship_{field}_{zone['key']}", 0) or 0))
            except ValueError:
                values[field] = 0
        shipping[zone["key"]] = {"name": zone["name"], "unit": zone["unit"], **values}
    return shipping


@app.route("/")
def home():
    db = get_db()
    products = visible_catalog(db.execute("SELECT * FROM products WHERE active=1 ORDER BY id DESC").fetchall())
    flagged_deals = [item for item in products if item.get("deal_of_week")]
    deal = flagged_deals[0] if flagged_deals else next((item for item in products if item["product_type"] == "Shoes"), products[0] if products else None)
    featured = [item for item in products if item.get("featured")] or products[:8]
    testimonials = db.execute(
        """
        SELECT reviews.name, reviews.rating, reviews.body, products.name AS product_name
        FROM reviews JOIN products ON products.id=reviews.product_id
        ORDER BY reviews.id DESC LIMIT 3
        """
    ).fetchall()
    faqs = db.execute("SELECT * FROM faqs ORDER BY sort_order, id").fetchall()
    return render_template(
        "home.html",
        products=featured,
        deal=deal,
        testimonials=testimonials,
        faqs=faqs,
    )


@app.route("/products")
def products():
    main = request.args.get("main", "").strip()
    sub = request.args.get("sub", "").strip()
    category = request.args.get("category", "All").strip() or "All"
    search = request.args.get("search", "").strip()
    if main not in load_main_categories():
        main = ""
    query, args = "SELECT * FROM products WHERE active=1", []
    if search:
        query += " AND (name ILIKE ? OR category ILIKE ? OR description ILIKE ? OR COALESCE(sub_category,'') ILIKE ? OR COALESCE(main_category,'') ILIKE ? OR COALESCE(product_tags,'') ILIKE ? OR COALESCE(product_hashtags,'') ILIKE ?)"
        args.extend([f"%{search}%"] * 7)
    catalog = visible_catalog(get_db().execute(query + " ORDER BY id DESC", args).fetchall())
    rows = [item for item in catalog if matches_shop_filter(item, main, sub, category)]
    current_group = next((group for group in shop_category_tree(catalog) if group["name"] == main), None)
    title_parts = [part for part in (main, sub if sub else None, category if category != "All" and not main and not sub else None) if part]
    return render_template(
        "products.html",
        products=rows,
        selected_main=main,
        selected_sub=sub,
        selected=category,
        search=search,
        current_subs=(current_group["subs"] if current_group else []),
        catalog_title=" · ".join(title_parts),
    )


@app.route("/product/<int:product_id>")
def product_detail(product_id):
    item = fetch_product(product_id)
    db = get_db()
    reviews = db.execute("SELECT * FROM reviews WHERE product_id=? ORDER BY id DESC", (product_id,)).fetchall()
    others = visible_catalog(
        db.execute(
            "SELECT * FROM products WHERE id!=? AND active=1 ORDER BY id DESC LIMIT 24",
            (product_id,),
        ).fetchall()
    )
    same_sub = [
        other
        for other in others
        if product_sub_category(other) == product_sub_category(item)
    ]
    same_main = [
        other
        for other in others
        if other.get("main_category") == item.get("main_category") and other not in same_sub
    ]
    related = (same_sub + same_main)[:4]
    return render_template("product_detail.html", product=item, reviews=reviews, related=related)


@app.post("/product/<int:product_id>/like")
def like_product(product_id):
    fetch_product(product_id)
    liked = liked_product_ids()
    db = get_db()
    if product_id in liked:
        liked.remove(product_id)
        db.execute("UPDATE products SET likes=GREATEST(likes-1,0) WHERE id=?", (product_id,))
        flash("Like removed.", "success")
    else:
        liked.append(product_id)
        db.execute("UPDATE products SET likes=likes+1 WHERE id=?", (product_id,))
        flash("Thanks for the like.", "success")
    db.commit()
    session["liked"] = liked
    return redirect(request.referrer or url_for("product_detail", product_id=product_id))


@app.post("/product/<int:product_id>/review")
def add_review(product_id):
    fetch_product(product_id)
    name, body = request.form.get("name", "").strip(), request.form.get("body", "").strip()
    try:
        rating = int(request.form.get("rating", 0))
    except ValueError:
        rating = 0
    if not name or not body or rating not in range(1, 6):
        flash("Please enter a name, a 1–5 rating, and your review.", "error")
    else:
        db = get_db()
        db.execute(
            "INSERT INTO reviews (product_id,name,rating,body,created_at) VALUES (?,?,?,?,?)",
            (product_id, name, rating, body, datetime.utcnow().strftime("%Y-%m-%d")),
        )
        db.execute(
            "UPDATE products SET reviews_count=reviews_count+1, rating=ROUND((((rating*reviews_count)+?)::numeric)/(reviews_count+1),1) WHERE id=?",
            (rating, product_id),
        )
        db.commit()
        flash("Thank you — your review is live.", "success")
    return redirect(url_for("product_detail", product_id=product_id) + "#reviews")


@app.post("/cart/add/<int:product_id>")
def add_cart(product_id):
    item = fetch_product(product_id)
    selected_size = request.form.get("size", item["sizes"][0] if item["sizes"] else "Standard")
    selected_color = request.form.get("color", item["colors"][0] if item["colors"] else "Default")
    if item["sizes"] and selected_size not in item["sizes"]:
        flash("Please select a valid size.", "error")
        return redirect(url_for("product_detail", product_id=product_id))
    if item["colors"] and selected_color not in item["colors"]:
        flash("Please select a valid colour.", "error")
        return redirect(url_for("product_detail", product_id=product_id))
    color = next((entry for entry in item["color_rows"] if entry["name"] == selected_color), None)
    variant_stock = int(color["sizes"].get(selected_size, 0)) if color else 0
    try:
        quantity = int(request.form.get("quantity", 1) or 1)
    except ValueError:
        quantity = 1
    quantity = max(1, quantity)
    key = f"{product_id}:{selected_size}:{selected_color}"
    if variant_stock <= 0:
        flash(f"{selected_color} in size {selected_size} is currently out of stock.", "error")
        return redirect(url_for("product_detail", product_id=product_id))
    cart = session["cart"]
    new_quantity = cart.get(key, 0) + quantity
    if new_quantity > variant_stock:
        flash(f"Only {variant_stock} left in {selected_color}, size {selected_size}.", "error")
        return redirect(url_for("product_detail", product_id=product_id))
    cart[key] = new_quantity
    session["cart"] = cart
    flash(f"{item['name']} ({selected_color} / {selected_size}) added to your cart.", "success")
    if request.form.get("intent") == "buy":
        return redirect(url_for("cart"))
    return redirect(request.referrer or url_for("cart"))


@app.post("/cart/remove/<int:product_id>")
def remove_cart(product_id):
    cart = session["cart"]
    cart.pop(request.form.get("cart_key", ""), None)
    session["cart"] = cart
    return redirect(url_for("cart"))


@app.post("/cart/update")
def update_cart():
    cart = session["cart"]
    key = request.form.get("cart_key", "")
    if key not in cart:
        return redirect(url_for("cart"))
    action = request.form.get("action", "")
    try:
        current = int(cart[key])
    except (TypeError, ValueError):
        current = 1
    if action == "inc":
        current += 1
    elif action == "dec":
        current -= 1
    else:
        try:
            current = int(request.form.get("quantity", current) or current)
        except ValueError:
            pass
    if current <= 0:
        cart.pop(key, None)
        session["cart"] = cart
        return redirect(url_for("cart"))
    parts = key.split(":")
    item_id = parts[0]
    selected_size = parts[1] if len(parts) > 1 else "Standard"
    selected_color = parts[2] if len(parts) > 2 else "Default"
    row = get_db().execute("SELECT * FROM products WHERE id=?", (item_id,)).fetchone()
    if row:
        item = product(row)
        color = next((entry for entry in item["color_rows"] if entry["name"] == selected_color), None)
        variant_stock = int(color["sizes"].get(selected_size, 0)) if color else 0
        if current > variant_stock:
            flash(f"Only {variant_stock} left in {selected_color}, size {selected_size}.", "error")
            current = max(1, variant_stock) if variant_stock else 0
        if current <= 0:
            cart.pop(key, None)
            session["cart"] = cart
            return redirect(url_for("cart"))
    cart[key] = current
    session["cart"] = cart
    return redirect(url_for("cart"))


def cart_items():
    items, total = [], 0
    for cart_key, quantity in session["cart"].items():
        parts = cart_key.split(":")
        item_id = parts[0]
        selected_size = parts[1] if len(parts) > 1 else "Standard"
        selected_color = parts[2] if len(parts) > 2 else "Default"
        row = get_db().execute("SELECT * FROM products WHERE id=?", (item_id,)).fetchone()
        if row:
            item = product(row)
            item["quantity"] = quantity
            item["selected_size"] = selected_size
            item["selected_color"] = selected_color
            item["cart_key"] = cart_key
            item["subtotal"] = item["display_price"] * quantity
            item["line_weight"] = float(item.get("ship_weight") or item.get("weight") or 0) * quantity
            total += item["subtotal"]
            items.append(item)
    return items, total


def cart_weight_kg(items):
    return round(sum(float(item.get("line_weight") or 0) for item in items), 2)


def shipping_label(value, unit):
    if unit == "EUR":
        return f"€{value:g}"
    return f"Rs {value:,.0f}"


def store_shipping_amount(value, unit):
    amount = float(value)
    return amount * EUR_TO_STORE if unit == "EUR" else amount


def load_shipping_zones():
    rows = get_db().execute("SELECT zone, unit, under_value, over_value FROM shipping_rates").fetchall()
    by_name = {row["zone"]: row for row in rows}
    zones = []
    for default in DEFAULT_SHIPPING_ZONES:
        row = by_name.get(default["name"], default)
        unit = row["unit"] if "unit" in row else default["unit"]
        under = float(row["under_value"] if "under_value" in row else default["under"])
        over = float(row["over_value"] if "over_value" in row else default["over"])
        zones.append(
            {
                "name": default["name"],
                "key": default["key"],
                "unit": unit,
                "under": under,
                "over": over,
                "under_label": shipping_label(under, unit),
                "over_label": shipping_label(over, unit),
                "under_store": store_shipping_amount(under, unit),
                "over_store": store_shipping_amount(over, unit),
            }
        )
    return zones


def shipping_zone_map():
    return {zone["name"]: zone for zone in load_shipping_zones()}


def shipping_options(items, weight_kg, method="standard"):
    heavy = weight_kg > WEIGHT_LIMIT_KG
    express = method == "express"
    options = []
    sources = items or [None]
    for zone in DEFAULT_SHIPPING_ZONES:
        standard_amount = None
        express_amount = None
        labels = None
        for item in sources:
            rate = ((item or {}).get("shipping") or normalize_product_shipping(None))[zone["key"]]
            standard = rate["over_store"] if heavy else rate["under_store"]
            express_price = rate["express_over_store"] if heavy else rate["express_under_store"]
            if standard_amount is None or standard > standard_amount:
                standard_amount = standard
                labels = rate
            if express_amount is None or express_price > express_amount:
                express_amount = express_price
                if labels is None:
                    labels = rate
        amount = express_amount if express else standard_amount
        current_label = (
            labels["express_over_label"] if express and heavy
            else labels["express_under_label"] if express
            else labels["over_label"] if heavy
            else labels["under_label"]
        )
        options.append(
            {
                "name": zone["name"],
                "key": zone["key"],
                "unit": zone["unit"],
                "under_label": labels["under_label"],
                "over_label": labels["over_label"],
                "express_under_label": labels["express_under_label"],
                "express_over_label": labels["express_over_label"],
                "standard_amount": standard_amount,
                "express_amount": express_amount,
                "current_label": current_label,
                "amount": amount,
            }
        )
    region = customer_zone_name()
    matched = [option for option in options if option["name"] == region]
    return matched or options[:1]


def shipping_quote(items, subtotal, country, method="standard"):
    weight_kg = cart_weight_kg(items)
    options = shipping_options(items, weight_kg, method)
    zone = next((entry for entry in options if entry["name"] == country), options[0])
    band = "over 5 kg" if weight_kg > WEIGHT_LIMIT_KG else "under 5 kg"
    speed = "Express" if method == "express" else "Standard"
    label = f"{zone['name']} {speed} delivery — {zone['current_label']} ({band}, {weight_kg:g} kg)"
    return zone["amount"], label, weight_kg


def reserve_order_stock(db, items):
    for cart_item in items:
        row = db.execute("SELECT * FROM products WHERE id=? FOR UPDATE", (cart_item["id"],)).fetchone()
        if not row:
            raise ValueError(f"{cart_item['name']} is no longer available.")
        current = product(row)
        color = next(
            (entry for entry in current["color_rows"] if entry["name"] == cart_item["selected_color"]),
            None,
        )
        available = int(color["sizes"].get(cart_item["selected_size"], 0)) if color else 0
        if available < cart_item["quantity"]:
            raise ValueError(
                f"Only {available} of {cart_item['name']} in "
                f"{cart_item['selected_color']} / {cart_item['selected_size']} remain."
            )
        color["sizes"][cart_item["selected_size"]] = available - cart_item["quantity"]
        color["quantity"] = sum(color["sizes"].values())
        total_stock = sum(entry["quantity"] for entry in current["color_rows"])
        db.execute(
            "UPDATE products SET colors_json=?, stock=? WHERE id=?",
            (json.dumps(current["color_rows"]), total_stock, cart_item["id"]),
        )


@app.route("/cart", methods=["GET", "POST"])
def cart():
    items, total = cart_items()
    address_zone = zone_from_address(request.form.get("address", "")) if request.method == "POST" else ""
    if address_zone:
        apply_region(address_zone)
        g.customer_location = None
    country = customer_zone_name()
    shipping_method = request.form.get("shipping_method", "standard") if request.method == "POST" else request.args.get("shipping_method", "standard")
    if shipping_method not in {"standard", "express"}:
        shipping_method = "standard"
    valid_countries = set(ZONE_NAMES)
    if country not in valid_countries:
        country = customer_zone_name()
    shipping, shipping_label, weight_kg = shipping_quote(items, total, country, shipping_method)
    if request.method == "POST":
        name, email, address = (request.form.get(k, "").strip() for k in ("name", "email", "address"))
        payment_method = request.form.get("payment_method", "")
        valid_methods = {"pay_on_delivery", "bank_transfer"}
        if not items or not name or not email or not address or country not in valid_countries or payment_method not in valid_methods:
            flash("Add items and complete all checkout fields, including payment method.", "error")
        else:
            grand_total = total + shipping
            db = get_db()
            try:
                reserve_order_stock(db, items)
                db.execute(
                    """
                    INSERT INTO orders (
                        customer_name,email,address,country,payment_method,currency,total,shipping,items,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        name,
                        email,
                        address,
                        country,
                        payment_method,
                        session["currency"],
                        grand_total,
                        shipping,
                        str(items),
                        datetime.utcnow().isoformat(),
                    ),
                )
                db.commit()
                session["cart"] = {}
                flash("Order placed successfully. We will contact you shortly.", "success")
                return redirect(url_for("home"))
            except ValueError as error:
                db.rollback()
                flash(str(error), "error")
    return render_template(
        "cart.html",
        items=items,
        total=total,
        shipping=shipping,
        grand_total=total + shipping,
        shipping_label=shipping_label,
        selected_country=country,
        shipping_method=shipping_method,
        cart_weight=weight_kg,
        shipping_zones=shipping_options(items, weight_kg, shipping_method),
        heavy_order=weight_kg > WEIGHT_LIMIT_KG,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:100]
        email = request.form.get("email", "").strip().lower()[:120]
        password = request.form.get("password", "")
        if not name or not email or len(password) < 6:
            flash("Enter your name, email, and a password with at least 6 characters.", "error")
        else:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO users (name,email,password_hash,created_at) VALUES (?,?,?,?)",
                    (name, email, generate_password_hash(password), datetime.utcnow().isoformat()),
                )
                db.commit()
                user = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
                session["user_id"] = user["id"]
                flash("Your profile is ready.", "success")
                next_url = request.args.get("next") or url_for("profile")
                return redirect(next_url)
            except IntegrityError:
                flash("An account with that email already exists. Please sign in.", "error")
    return render_template("auth_register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            flash("Welcome back.", "success")
            return redirect(request.args.get("next") or url_for("profile"))
        flash("Incorrect email or password.", "error")
    return render_template("auth_login.html")


@app.post("/logout")
def logout():
    session.pop("user_id", None)
    flash("You have been signed out.", "success")
    return redirect(url_for("home"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user()
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:100]
        email = request.form.get("email", "").strip().lower()[:120]
        password = request.form.get("password", "")
        if not name or not email:
            flash("Name and email are required.", "error")
        else:
            try:
                db = get_db()
                if password and len(password) < 6:
                    flash("New password must be at least 6 characters.", "error")
                else:
                    country = request.form.get("country", "").strip()
                    if country not in ZONE_NAMES:
                        country = user.get("country") or customer_zone_name()
                    apply_region(country)
                    if password:
                        db.execute(
                            "UPDATE users SET name=?, email=?, password_hash=?, country=? WHERE id=?",
                            (name, email, generate_password_hash(password), country, user["id"]),
                        )
                    else:
                        db.execute("UPDATE users SET name=?, email=?, country=? WHERE id=?", (name, email, country, user["id"]))
                    db.commit()
                    flash("Profile updated.", "success")
                    return redirect(url_for("profile"))
            except IntegrityError:
                flash("That email is already in use.", "error")
        user = current_user()
    db = get_db()
    orders = []
    for row in db.execute("SELECT * FROM orders WHERE email=? ORDER BY id DESC", (user["email"],)).fetchall():
        order = dict(row)
        order["items"] = parse_order_items(order.get("items"))
        orders.append(order)
    listings = [listing_view(row) for row in db.execute("SELECT * FROM listings WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchall()]
    return render_template("profile.html", user=user, orders=orders, listings=listings)


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    user = current_user()
    categories = category_names()
    if request.method == "POST":
        title = request.form.get("title", "").strip()[:100]
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()[:3000]
        try:
            price = float(request.form.get("price", 0))
        except ValueError:
            price = 0
        if not title or not category or not description or price <= 0:
            flash("Please complete every listing field with a valid price.", "error")
        elif category not in categories:
            flash("Please choose a valid category.", "error")
        else:
            try:
                db = get_db()
                cursor = db.execute(
                    """
                    INSERT INTO listings (user_id,seller_name,title,category,price,description,images_json,created_at,status)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    RETURNING id
                    """,
                    (
                        user["id"],
                        user["name"],
                        title,
                        category,
                        price,
                        description,
                        "[]",
                        datetime.utcnow().isoformat(),
                        "pending",
                    ),
                )
                listing_id = cursor.fetchone()["id"]
                images = save_listing_images(listing_id)
                if len(images) < 1:
                    db.execute("DELETE FROM listings WHERE id=?", (listing_id,))
                    db.commit()
                    flash("Please upload at least one product image.", "error")
                else:
                    db.execute("UPDATE listings SET images_json=? WHERE id=?", (json.dumps(images), listing_id))
                    db.commit()
                    flash("Your listing has been submitted for review.", "success")
                    return redirect(url_for("sell"))
            except ValueError as error:
                flash(str(error), "error")
    listings = [
        listing_view(row)
        for row in get_db().execute("SELECT * FROM listings WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchall()
    ]
    return render_template("sell.html", categories=categories, user=user, listings=listings)


@app.route("/contact", methods=["GET", "POST"])
@login_required
def contact():
    user = current_user()
    if request.method == "POST":
        message = request.form.get("message", "").strip()
        if not message:
            flash("Please enter your message.", "error")
        else:
            get_db().execute(
                "INSERT INTO contacts (user_id,name,email,message,created_at) VALUES (?,?,?,?,?)",
                (user["id"], user["name"], user["email"], message, datetime.utcnow().isoformat()),
            )
            get_db().commit()
            flash("Your message has been sent to our support team.", "success")
            return redirect(url_for("contact"))
    return render_template("contact.html", user=user)


@app.post("/preferences")
def preferences():
    currency, language = request.form.get("currency"), request.form.get("language")
    region = request.form.get("region", "").strip()
    old_currency = session.get("currency")
    old_language = session.get("language")
    old_region = session.get("region")
    if currency in CURRENCIES:
        session["currency"] = currency
    if language in LANGUAGES:
        session["language"] = language
        if language == "ur":
            session["currency"] = "PKR"
    if region in ZONE_NAMES and region != old_region:
        apply_region(region)
    elif currency in CURRENCIES and currency != old_currency:
        inferred = "Germany" if currency == "EUR" and session.get("language") == "de" else CURRENCY_TO_ZONE.get(currency)
        if inferred:
            session["region"] = inferred
    elif language in LANGUAGES and language != old_language:
        if language == "ur":
            session["region"] = "Pakistan"
        elif language in LANGUAGE_TO_ZONE:
            session["region"] = LANGUAGE_TO_ZONE[language]
    return redirect(request.referrer or url_for("home"))


@app.get("/api/products")
def api_products():
    return jsonify(visible_catalog(get_db().execute("SELECT * FROM products WHERE active=1").fetchall()))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if not ADMIN_PASSWORD_HASH:
            flash("Admin password hash is not configured. Set ADMIN_PASSWORD_HASH in .env.", "error")
        elif username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session["is_admin"] = True
            flash("Welcome to the admin dashboard.", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Incorrect username or password.", "error")
    return render_template("admin_login.html")


@app.post("/admin/logout")
@admin_required
def admin_logout():
    session.pop("is_admin", None)
    flash("You have been signed out.", "success")
    return redirect(url_for("home"))


@app.get("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    return render_template(
        "admin_dashboard.html",
        products=[product(row) for row in db.execute("SELECT * FROM products ORDER BY id DESC").fetchall()],
        orders=db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 20").fetchall(),
        reviews=db.execute(
            """
            SELECT reviews.*, products.name AS product_name
            FROM reviews JOIN products ON products.id=reviews.product_id
            ORDER BY reviews.id DESC LIMIT 20
            """
        ).fetchall(),
        contacts=db.execute("SELECT * FROM contacts ORDER BY id DESC LIMIT 20").fetchall(),
        listings=[listing_view(row) for row in db.execute("SELECT * FROM listings ORDER BY id DESC LIMIT 50").fetchall()],
        categories=db.execute("SELECT * FROM categories ORDER BY name").fetchall(),
        shipping_zones=load_shipping_zones(),
        faqs=db.execute("SELECT * FROM faqs ORDER BY sort_order, id").fetchall(),
    )


@app.post("/admin/listing/<int:listing_id>/approve")
@admin_required
def admin_listing_approve(listing_id):
    try:
        product_id = approve_seller_listing(listing_id)
        flash(f"Listing approved and published to the shop as product #{product_id}.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/listing/<int:listing_id>/reject")
@admin_required
def admin_listing_reject(listing_id):
    get_db().execute(
        "UPDATE listings SET status=?, reviewed_at=? WHERE id=?",
        ("rejected", datetime.utcnow().isoformat(), listing_id),
    )
    get_db().commit()
    flash("Listing rejected.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/faqs", methods=["GET", "POST"])
@admin_required
def admin_faqs():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        question = request.form.get("question", "").strip()[:200]
        answer = request.form.get("answer", "").strip()[:2000]
        try:
            faq_id = int(request.form.get("faq_id", 0) or 0)
        except ValueError:
            faq_id = 0
        if action == "add" and question and answer:
            next_order = db.execute("SELECT COALESCE(MAX(sort_order),0)+1 AS n FROM faqs").fetchone()["n"]
            db.execute("INSERT INTO faqs (question,answer,sort_order) VALUES (?,?,?)", (question, answer, next_order))
            db.commit()
            flash("FAQ added.", "success")
        elif action == "save" and faq_id and question and answer:
            db.execute("UPDATE faqs SET question=?, answer=? WHERE id=?", (question, answer, faq_id))
            db.commit()
            flash("FAQ updated.", "success")
        elif action == "delete" and faq_id:
            db.execute("DELETE FROM faqs WHERE id=?", (faq_id,))
            db.commit()
            flash("FAQ deleted.", "success")
        else:
            flash("Please complete the question and answer.", "error")
        return redirect(url_for("admin_faqs"))
    return render_template(
        "manage_faqs.html",
        faqs=db.execute("SELECT * FROM faqs ORDER BY sort_order, id").fetchall(),
        back_url=url_for("admin_dashboard"),
    )


@app.route("/admin/main-categories", methods=["GET", "POST"])
@admin_required
def admin_main_categories():
    if request.method == "POST":
        handle_main_category_form()
        return redirect(url_for("admin_main_categories"))
    return render_template(
        "manage_main_categories.html",
        categories=get_db().execute("SELECT * FROM main_categories ORDER BY id").fetchall(),
        back_url=url_for("admin_dashboard"),
        save_url=url_for("admin_main_categories"),
    )


@app.route("/admin/sub-categories", methods=["GET", "POST"])
@admin_required
def admin_sub_categories():
    if request.method == "POST":
        handle_sub_category_form()
        return redirect(url_for("admin_sub_categories"))
    return render_template(
        "manage_sub_categories.html",
        categories=get_db().execute("SELECT * FROM sub_categories ORDER BY product_type, id").fetchall(),
        product_types=PRODUCT_TYPES,
        back_url=url_for("admin_dashboard"),
        save_url=url_for("admin_sub_categories"),
    )


@app.post("/admin/shipping")
@admin_required
def admin_shipping():
    db = get_db()
    try:
        for zone in DEFAULT_SHIPPING_ZONES:
            under = float(request.form.get(f"under_{zone['key']}", 0) or 0)
            over = float(request.form.get(f"over_{zone['key']}", 0) or 0)
            if under < 0 or over < 0:
                raise ValueError("Shipping prices cannot be negative.")
            db.execute(
                """
                INSERT INTO shipping_rates (zone, unit, under_value, over_value)
                VALUES (?,?,?,?)
                ON CONFLICT (zone) DO UPDATE SET under_value=EXCLUDED.under_value, over_value=EXCLUDED.over_value
                """,
                (zone["name"], zone["unit"], under, over),
            )
        db.commit()
        flash("Shipping charges updated.", "success")
    except ValueError:
        flash("Enter valid shipping prices for every region.", "error")
    return redirect(url_for("admin_dashboard") + "#shipping")


@app.post("/admin/categories")
@admin_required
def admin_categories():
    action = request.form.get("action")
    db = get_db()
    if action == "add":
        name = request.form.get("name", "").strip()[:40]
        if not name:
            flash("Category name is required.", "error")
        else:
            try:
                db.execute("INSERT INTO categories (name) VALUES (?)", (name,))
                db.commit()
                flash("Category added.", "success")
            except IntegrityError:
                flash("That category already exists.", "error")
    elif action == "rename":
        category_id = request.form.get("category_id")
        name = request.form.get("name", "").strip()[:40]
        row = db.execute("SELECT * FROM categories WHERE id=?", (category_id,)).fetchone()
        if not row or not name:
            flash("Valid category and new name are required.", "error")
        else:
            try:
                db.execute("UPDATE categories SET name=? WHERE id=?", (name, category_id))
                db.execute("UPDATE products SET category=? WHERE category=?", (name, row["name"]))
                db.commit()
                flash("Category updated.", "success")
            except IntegrityError:
                flash("That category name already exists.", "error")
    elif action == "delete":
        category_id = request.form.get("category_id")
        row = db.execute("SELECT * FROM categories WHERE id=?", (category_id,)).fetchone()
        if not row:
            flash("Category not found.", "error")
        else:
            in_use = db.execute("SELECT COUNT(*) AS count FROM products WHERE category=?", (row["name"],)).fetchone()["count"]
            if in_use:
                flash("Cannot delete a category that still has products.", "error")
            else:
                db.execute("DELETE FROM categories WHERE id=?", (category_id,))
                db.commit()
                flash("Category deleted.", "success")
    return redirect(url_for("admin_dashboard") + "#categories")


def save_named_category(table, name, extra=None):
    name = (name or "").strip()[:40]
    if not name:
        raise ValueError("Category name is required.")
    columns = ["name"]
    values = [name]
    if extra:
        columns.extend(extra.keys())
        values.extend(extra.values())
    get_db().execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in values)})",
        tuple(values),
    )


def handle_main_category_form():
    action = request.form.get("action")
    db = get_db()
    if action == "add":
        try:
            save_named_category("main_categories", request.form.get("name"))
            db.commit()
            flash("Main category added.", "success")
        except ValueError as error:
            flash(str(error), "error")
        except IntegrityError:
            db.rollback()
            flash("That main category already exists.", "error")
    elif action == "rename":
        category_id = request.form.get("category_id")
        name = (request.form.get("name") or "").strip()[:40]
        row = db.execute("SELECT * FROM main_categories WHERE id=?", (category_id,)).fetchone()
        if not row or not name:
            flash("Valid main category and new name are required.", "error")
        else:
            try:
                db.execute("UPDATE main_categories SET name=? WHERE id=?", (name, category_id))
                db.execute("UPDATE products SET main_category=? WHERE main_category=?", (name, row["name"]))
                db.commit()
                flash("Main category updated.", "success")
            except IntegrityError:
                db.rollback()
                flash("That main category name already exists.", "error")
    elif action == "delete":
        category_id = request.form.get("category_id")
        row = db.execute("SELECT * FROM main_categories WHERE id=?", (category_id,)).fetchone()
        if not row:
            flash("Main category not found.", "error")
        else:
            in_use = db.execute(
                "SELECT COUNT(*) AS count FROM products WHERE main_category=?",
                (row["name"],),
            ).fetchone()["count"]
            if in_use:
                flash("Cannot delete a main category that still has products.", "error")
            else:
                db.execute("DELETE FROM main_categories WHERE id=?", (category_id,))
                db.commit()
                flash("Main category deleted.", "success")


def handle_sub_category_form():
    action = request.form.get("action")
    db = get_db()
    if action == "add":
        product_type = request.form.get("product_type", "").strip()
        if product_type not in PRODUCT_TYPES:
            flash("Choose Clothes, Shoes, or Accessories for the sub category.", "error")
            return
        try:
            save_named_category("sub_categories", request.form.get("name"), {"product_type": product_type})
            db.commit()
            flash("Sub category added.", "success")
        except ValueError as error:
            flash(str(error), "error")
        except IntegrityError:
            db.rollback()
            flash("That sub category already exists for this product type.", "error")
    elif action == "rename":
        category_id = request.form.get("category_id")
        name = (request.form.get("name") or "").strip()[:40]
        product_type = request.form.get("product_type", "").strip()
        row = db.execute("SELECT * FROM sub_categories WHERE id=?", (category_id,)).fetchone()
        if not row or not name or product_type not in PRODUCT_TYPES:
            flash("Valid sub category, product type, and new name are required.", "error")
        else:
            try:
                db.execute(
                    "UPDATE sub_categories SET name=?, product_type=? WHERE id=?",
                    (name, product_type, category_id),
                )
                db.execute("UPDATE products SET sub_category=?, category=? WHERE sub_category=?", (name, name, row["name"]))
                db.commit()
                flash("Sub category updated.", "success")
            except IntegrityError:
                db.rollback()
                flash("That sub category already exists for this product type.", "error")
    elif action == "delete":
        category_id = request.form.get("category_id")
        row = db.execute("SELECT * FROM sub_categories WHERE id=?", (category_id,)).fetchone()
        if not row:
            flash("Sub category not found.", "error")
        else:
            in_use = db.execute(
                "SELECT COUNT(*) AS count FROM products WHERE sub_category=? OR category=?",
                (row["name"], row["name"]),
            ).fetchone()["count"]
            if in_use:
                flash("Cannot delete a sub category that still has products.", "error")
            else:
                db.execute("DELETE FROM sub_categories WHERE id=?", (category_id,))
                db.commit()
                flash("Sub category deleted.", "success")


def save_product_from_form(product_id=None):
    fields = {
        key: request.form.get(key, "").strip()
        for key in (
            "name",
            "sku",
            "description",
            "condition",
            "main_category",
            "sub_category",
            "product_type",
            "size_group",
            "region_visibility",
        )
    }
    fields["name"] = fields["name"][:100]
    fields["description"] = fields["description"][:3000]
    fields["sku"] = fields["sku"][:50]
    marketplace = parse_marketplace_urls()
    color_rows = parse_color_form()
    size_rows = parse_size_form()
    shipping_rows = parse_product_shipping_form()
    product_tags = parse_keyword_list(request.form.get("product_tags", ""))
    product_hashtags = parse_keyword_list(request.form.get("product_hashtags", ""), hashtag=True)
    tags_stored = ",".join(product_tags)
    hashtags_stored = ",".join(product_hashtags)
    try:
        price_eur = float(request.form.get("price", 0))
    except ValueError:
        price_eur = 0
    price = round(price_eur * EUR_TO_STORE, 2)
    try:
        discount_percent = float(request.form.get("discount_percent", 0) or 0)
    except ValueError:
        discount_percent = 0
    try:
        weight = float(request.form.get("weight", 0) or 0)
    except ValueError:
        weight = 0
    try:
        packing_weight = float(request.form.get("packing_weight", 0) or 0)
    except ValueError:
        packing_weight = 0
    try:
        pakistan_price = float(request.form.get("pakistan_price", 0) or 0)
    except ValueError:
        pakistan_price = 0
    try:
        pakistan_discount_percent = float(request.form.get("pakistan_discount_percent", 0) or 0)
    except ValueError:
        pakistan_discount_percent = 0
    try:
        rating = float(request.form.get("rating", 0) or 0)
    except ValueError:
        rating = 0
    try:
        likes = int(float(request.form.get("likes", 0) or 0))
    except ValueError:
        likes = 0
    discount_percent = max(0.0, min(100.0, discount_percent))
    pakistan_discount_percent = max(0.0, min(100.0, pakistan_discount_percent))
    weight = max(0.0, weight)
    packing_weight = max(0.0, packing_weight)
    pakistan_price = max(0.0, pakistan_price)
    rating = max(0.0, min(5.0, rating))
    likes = max(0, likes)
    featured = 1 if request.form.get("featured") else 0
    deal_of_week = 1 if request.form.get("deal_of_week") else 0
    stock = sum(entry["quantity"] for entry in color_rows)
    allowed_subs = load_sub_categories().get(fields["product_type"], [])
    if (
        not fields["name"]
        or not fields["sku"]
        or not fields["description"]
        or not fields["condition"]
        or not fields["main_category"]
        or not fields["sub_category"]
        or not fields["product_type"]
        or not fields["size_group"]
        or not fields["region_visibility"]
        or price <= 0
        or not color_rows
        or not size_rows
    ):
        raise ValueError("Complete name, SKU, condition, categories, product type, size, description, price, colours, and stock.")
    if fields["product_type"] not in PRODUCT_TYPES:
        raise ValueError("Choose Clothes, Shoes, or Accessories.")
    if fields["main_category"] not in load_main_categories():
        raise ValueError("Choose a valid main category.")
    if fields["sub_category"] not in allowed_subs:
        raise ValueError("Choose a valid sub category for this product type.")
    if fields["size_group"] not in SIZE_GROUPS:
        raise ValueError("Choose Male, Female, Unisex, or Child.")
    if fields["condition"] not in CONDITION_LABELS:
        raise ValueError("Choose a product condition.")
    if fields["region_visibility"] not in {key for key, _ in REGION_OPTIONS}:
        raise ValueError("Choose where this product should be shown.")
    category = fields["sub_category"]
    listed_by = current_listing_owner()
    db = get_db()
    colors_legacy = ",".join(entry["name"] for entry in color_rows)
    sizes_legacy = ",".join(size_rows)
    extra_fields = (
        fields["condition"],
        fields["main_category"],
        fields["sub_category"],
        fields["product_type"],
        fields["size_group"],
        packing_weight,
        fields["region_visibility"],
        tags_stored,
        hashtags_stored,
    )
    if product_id is None:
        cursor = db.execute(
            """
            INSERT INTO products (
                name,category,price,rating,reviews_count,likes,sku,image,sizes,colors,
                description,stock,active,colors_json,sizes_json,amazon_url,etsy_url,ebay_url,
                discount_percent,weight,shipping_json,pakistan_price,pakistan_discount_percent,
                condition,main_category,sub_category,product_type,size_group,packing_weight,region_visibility,
                product_tags,product_hashtags,featured,deal_of_week,listed_by
            ) VALUES (?,?,?,?,0,?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            RETURNING id
            """,
            (
                fields["name"],
                category,
                price,
                rating,
                likes,
                fields["sku"],
                "",
                sizes_legacy,
                colors_legacy,
                fields["description"],
                stock,
                json.dumps(color_rows),
                json.dumps(size_rows),
                marketplace["amazon_url"],
                marketplace["etsy_url"],
                marketplace["ebay_url"],
                discount_percent,
                weight,
                json.dumps(shipping_rows),
                pakistan_price,
                pakistan_discount_percent,
                *extra_fields,
                featured,
                deal_of_week,
                listed_by,
            ),
        )
        product_id = cursor.fetchone()["id"]
    else:
        active = 1 if request.form.get("active") else 0
        db.execute(
            """
            UPDATE products SET
                name=?, category=?, price=?, rating=?, likes=?, sku=?, sizes=?, colors=?,
                description=?, stock=?, active=?, colors_json=?, sizes_json=?,
                amazon_url=?, etsy_url=?, ebay_url=?, discount_percent=?, weight=?, shipping_json=?,
                pakistan_price=?, pakistan_discount_percent=?, condition=?, main_category=?,
                sub_category=?, product_type=?, size_group=?, packing_weight=?, region_visibility=?,
                product_tags=?, product_hashtags=?, featured=?, deal_of_week=?
            WHERE id=?
            """,
            (
                fields["name"],
                category,
                price,
                rating,
                likes,
                fields["sku"],
                sizes_legacy,
                colors_legacy,
                fields["description"],
                stock,
                active,
                json.dumps(color_rows),
                json.dumps(size_rows),
                marketplace["amazon_url"],
                marketplace["etsy_url"],
                marketplace["ebay_url"],
                discount_percent,
                weight,
                json.dumps(shipping_rows),
                pakistan_price,
                pakistan_discount_percent,
                *extra_fields,
                featured,
                deal_of_week,
                product_id,
            ),
        )
    if deal_of_week:
        db.execute("UPDATE products SET deal_of_week=0 WHERE id!=?", (product_id,))
    db.commit()
    save_product_images(fields["sku"], slots=10)


def product_form_context(item=None):
    existing_sizes = item["size_rows"] if item else []
    extra_sizes = extra_sizes_of(item)
    return {
        "product": item,
        "product_types": PRODUCT_TYPES,
        "main_categories": load_main_categories(),
        "sub_categories": load_sub_categories(),
        "size_groups": SIZE_GROUPS,
        "conditions": CONDITIONS,
        "region_options": REGION_OPTIONS,
        "color_slots": empty_color_slots(item["color_rows"] if item else None, extra_sizes),
        "size_slots_by_type": size_slots_by_type(existing_sizes),
        "shipping_slots": product_shipping_slots(item.get("shipping") if item else None),
        "extra_sizes": extra_sizes,
        "custom_sizes": ", ".join(extra_sizes),
        "custom_shoe_sizes": ", ".join(extra_sizes) if item and item.get("product_type") == "Shoes" else "",
        "image_slots": product_image_slots(item),
        "dashboard_url": staff_home(),
        "price_eur": item["price_eur"] if item else "",
    }


@app.route("/admin/product/new", methods=["GET", "POST"])
@admin_required
def admin_product_new():
    if request.method == "POST":
        try:
            save_product_from_form()
            flash("Product created successfully.", "success")
            return redirect(url_for("admin_dashboard"))
        except (IntegrityError, ValueError) as error:
            flash(f"Product was not saved: {error}", "error")
    return render_template("admin_product_form.html", **product_form_context())


@app.route("/admin/product/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_product_edit(product_id):
    db = get_db()
    row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not row:
        abort(404)
    item = product(row)
    if request.method == "POST":
        try:
            save_product_from_form(product_id=product_id)
            flash("Product updated successfully.", "success")
            return redirect(url_for("admin_dashboard"))
        except (IntegrityError, ValueError) as error:
            flash(f"Product was not updated: {error}", "error")
            item = product(db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone())
    return render_template("admin_product_form.html", **product_form_context(item))


@app.post("/admin/product/<int:product_id>/delete")
@admin_required
def admin_product_delete(product_id):
    get_db().execute("DELETE FROM products WHERE id=?", (product_id,))
    get_db().commit()
    flash("Product deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/review/<int:review_id>/delete")
@admin_required
def admin_review_delete(review_id):
    get_db().execute("DELETE FROM reviews WHERE id=?", (review_id,))
    get_db().commit()
    flash("Review deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404



def parse_pg_array(text):
    return [item.strip() for item in (text or "").split(",") if item.strip()]



def save_pl_images(listing_id, existing=None):
    existing = dict(existing) if existing else {}
    folder = os.path.join(UPLOAD_ROOT, f"pl-{listing_id}")
    os.makedirs(folder, exist_ok=True)

    def handle(field, filename_base, existing_value):
        uploaded = request.files.get(field)
        if not uploaded or not uploaded.filename:
            return existing_value
        extension = secure_filename(uploaded.filename).rsplit(".", 1)[-1].lower() if "." in uploaded.filename else ""
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("Images must be JPG, JPEG, PNG, or WEBP files.")
        filename = f"{filename_base}.jpg"
        uploaded.save(os.path.join(folder, filename))
        return f"/static/images/pl-{listing_id}/{filename}"

    picture_main = handle("main_image", "main", existing.get("picture_main"))
    picture_2 = handle("image_2", "2", existing.get("picture_2"))
    picture_3 = handle("image_3", "3", existing.get("picture_3"))

    extra = existing.get("pictures_extra") or []
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except json.JSONDecodeError:
            extra = [part.strip() for part in extra.split(",") if part.strip()]
    pictures_extra = list(extra)
    while len(pictures_extra) < 7:
        pictures_extra.append(None)
    for index in range(4, 11):
        pos = index - 4
        result = handle(f"image_{index}", str(index), pictures_extra[pos])
        pictures_extra[pos] = result
    pictures_extra = [p for p in pictures_extra if p]

    return picture_main, picture_2, picture_3, pictures_extra


def save_listing_from_form(listing_id=None):
    form = request.form
    name = form.get("product_name", "").strip()[:100]
    sku = form.get("sku", "").strip()[:50]
    condition = form.get("condition", "").strip()
    main_category = form.get("main_category", "").strip()[:100]
    sub_category = form.get("sub_category", "").strip()[:100]
    product_type = form.get("product_type", "").strip()
    size_group = form.get("size_group", "").strip()
    size_value = form.get("size_value", "").strip()[:20]
    region_visibility = form.get("region_visibility", "").strip()
    shipping_method = form.get("shipping_method", "").strip()
    description = form.get("description", "").strip()[:3000]

    def to_float(key, default=0):
        try:
            return float(form.get(key, default) or default)
        except ValueError:
            return default

    product_weight_kg = to_float("product_weight_kg")
    packing_weight_kg = to_float("packing_weight_kg")
    price_europe_eur = to_float("price_europe_eur")
    discount_europe_percent = to_float("discount_europe_percent")
    price_pakistan_pkr = to_float("price_pakistan_pkr")
    discount_pakistan_percent = to_float("discount_pakistan_percent")
    shipping_cost_germany = to_float("shipping_cost_germany")
    shipping_cost_europe = to_float("shipping_cost_europe")
    shipping_cost_america = to_float("shipping_cost_america")
    shipping_cost_pakistan = to_float("shipping_cost_pakistan")
    express_shipping_charge = to_float("express_shipping_charge", 10)

    colours = parse_pg_array(form.get("colours", ""))
    product_tags = parse_pg_array(form.get("product_tags", ""))
    product_hashtags = parse_pg_array(form.get("product_hashtags", ""))

    link_ebay = form.get("link_ebay", "").strip()[:500]
    link_etsy = form.get("link_etsy", "").strip()[:500]
    link_amazon = form.get("link_amazon", "").strip()[:500]

    if not name or not sku:
        raise ValueError("Product name and SKU are required.")

    db = get_db()

    if listing_id is None:
        cursor = db.execute(
            """
            INSERT INTO product_listings (
                product_name, sku, condition, main_category, sub_category, product_type,
                product_weight_kg, packing_weight_kg, size_group, size_value, colours,
                price_europe_eur, discount_europe_percent, price_pakistan_pkr, discount_pakistan_percent,
                region_visibility, shipping_cost_germany, shipping_cost_europe, shipping_cost_america,
                shipping_cost_pakistan, express_shipping_charge, shipping_method, description,
                product_tags, product_hashtags, link_ebay, link_etsy, link_amazon
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            RETURNING id
            """,
            (
                name, sku, condition, main_category, sub_category, product_type,
                product_weight_kg, packing_weight_kg, size_group, size_value, colours,
                price_europe_eur, discount_europe_percent, price_pakistan_pkr, discount_pakistan_percent,
                region_visibility, shipping_cost_germany, shipping_cost_europe, shipping_cost_america,
                shipping_cost_pakistan, express_shipping_charge, shipping_method, description,
                product_tags, product_hashtags, link_ebay, link_etsy, link_amazon,
            ),
        )
        new_id = cursor.fetchone()["id"]
        picture_main, picture_2, picture_3, pictures_extra = save_pl_images(new_id)
        db.execute(
            "UPDATE product_listings SET picture_main=?, picture_2=?, picture_3=?, pictures_extra=? WHERE id=?",
            (picture_main, picture_2, picture_3, pictures_extra, new_id),
        )
    else:
        existing_row = db.execute(
            "SELECT picture_main, picture_2, picture_3, pictures_extra FROM product_listings WHERE id=?",
            (listing_id,),
        ).fetchone()
        picture_main, picture_2, picture_3, pictures_extra = save_pl_images(listing_id, existing=existing_row)
        db.execute(
            """
            UPDATE product_listings SET
                product_name=?, sku=?, condition=?, main_category=?, sub_category=?, product_type=?,
                product_weight_kg=?, packing_weight_kg=?, size_group=?, size_value=?, colours=?,
                price_europe_eur=?, discount_europe_percent=?, price_pakistan_pkr=?, discount_pakistan_percent=?,
                region_visibility=?, shipping_cost_germany=?, shipping_cost_europe=?, shipping_cost_america=?,
                shipping_cost_pakistan=?, express_shipping_charge=?, shipping_method=?, description=?,
                product_tags=?, product_hashtags=?, link_ebay=?, link_etsy=?, link_amazon=?,
                picture_main=?, picture_2=?, picture_3=?, pictures_extra=?, updated_at=now()
            WHERE id=?
            """,
            (
                name, sku, condition, main_category, sub_category, product_type,
                product_weight_kg, packing_weight_kg, size_group, size_value, colours,
                price_europe_eur, discount_europe_percent, price_pakistan_pkr, discount_pakistan_percent,
                region_visibility, shipping_cost_germany, shipping_cost_europe, shipping_cost_america,
                shipping_cost_pakistan, express_shipping_charge, shipping_method, description,
                product_tags, product_hashtags, link_ebay, link_etsy, link_amazon,
                picture_main, picture_2, picture_3, pictures_extra,
                listing_id,
            ),
        )
    db.commit()


@app.route("/admin/listings")
@admin_required
def admin_listings():
    db = get_db()
    listings = db.execute("SELECT * FROM product_listings ORDER BY id DESC").fetchall()
    return render_template("admin_listings.html", listings=listings)


@app.route("/admin/listings/new", methods=["GET", "POST"])
@admin_required
def admin_listing_new():
    if request.method == "POST":
        try:
            save_listing_from_form()
            flash("Listing created successfully.", "success")
            return redirect(url_for("admin_listings"))
        except (IntegrityError, ValueError) as error:
            flash(f"Listing was not saved: {error}", "error")
    return render_template("admin_listing_form.html", listing=None)


@app.route("/admin/listings/<int:listing_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_listing_edit(listing_id):
    db = get_db()
    row = db.execute("SELECT * FROM product_listings WHERE id=?", (listing_id,)).fetchone()
    if not row:
        abort(404)
    if request.method == "POST":
        try:
            save_listing_from_form(listing_id=listing_id)
            flash("Listing updated successfully.", "success")
            return redirect(url_for("admin_listings"))
        except (IntegrityError, ValueError) as error:
            flash(f"Listing was not updated: {error}", "error")
            row = db.execute("SELECT * FROM product_listings WHERE id=?", (listing_id,)).fetchone()
    return render_template("admin_listing_form.html", listing=row)


@app.post("/admin/listings/<int:listing_id>/delete")
@admin_required
def admin_listing_delete(listing_id):
    db = get_db()
    db.execute("DELETE FROM product_listings WHERE id=?", (listing_id,))
    db.commit()
    flash("Listing deleted.", "success")
    return redirect(url_for("admin_listings"))



PL_USERNAME = os.environ.get("PL_USERNAME", "")
PL_PASSWORD_HASH = os.environ.get("PL_PASSWORD_HASH", "")


def find_pl_user(username):
    username = (username or "").strip().lower()
    if not username:
        return None
    return get_db().execute("SELECT * FROM pl_users WHERE LOWER(username)=?", (username,)).fetchone()


def authenticate_pl(username, password):
    row = find_pl_user(username)
    if row and check_password_hash(row["password_hash"], password):
        return row
    env_username = (PL_USERNAME or "").strip()
    if env_username and PL_PASSWORD_HASH and username.strip() == env_username and check_password_hash(PL_PASSWORD_HASH, password):
        return {"username": env_username, "display_name": "Listing team"}
    return None


def upsert_pl_user(username, display_name, password):
    username = (username or "").strip().lower()
    display_name = (display_name or "").strip()
    if not username or not display_name or not password:
        raise ValueError("Username, display name, and password are required.")
    db = get_db()
    password_hash = generate_password_hash(password)
    existing = find_pl_user(username)
    if existing:
        db.execute(
            "UPDATE pl_users SET display_name=?, password_hash=? WHERE id=?",
            (display_name, password_hash, existing["id"]),
        )
    else:
        db.execute(
            "INSERT INTO pl_users (username, display_name, password_hash, created_at) VALUES (?,?,?,?)",
            (username, display_name, password_hash, datetime.utcnow().isoformat()),
        )
    db.commit()


def current_listing_owner():
    if session.get("is_pl"):
        return (session.get("pl_username") or "").strip() or "listing-team"
    return "admin"


def product_listed_by(row):
    if not row:
        return "admin"
    owner = (row.get("listed_by") if isinstance(row, dict) else None) or "admin"
    return str(owner).strip() or "admin"


def pl_can_manage(row):
    username = (session.get("pl_username") or "").strip()
    return bool(username) and product_listed_by(row) == username


def fetch_pl_owned_product(product_id):
    row = get_db().execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not row or not pl_can_manage(row):
        abort(404)
    return row


def pl_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_pl"):
            flash("Please sign in to access the listing team dashboard.", "error")
            return redirect(url_for("pl_login"))
        return view(*args, **kwargs)

    return wrapped


@app.route("/pl/login", methods=["GET", "POST"])
def pl_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = authenticate_pl(username, password)
        if user:
            session["is_pl"] = True
            session["pl_username"] = user["username"]
            session["pl_display_name"] = user.get("display_name") or user["username"]
            flash(f"Welcome, {session['pl_display_name']}.", "success")
            return redirect(url_for("pl_dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("pl_login.html")


@app.post("/pl/logout")
@pl_required
def pl_logout():
    session.pop("is_pl", None)
    session.pop("pl_username", None)
    session.pop("pl_display_name", None)
    flash("You have been signed out.", "success")
    return redirect(url_for("pl_login"))


@app.route("/pl")
@pl_required
def pl_dashboard():
    db = get_db()
    username = (session.get("pl_username") or "").strip()
    products = [
        product(row)
        for row in db.execute("SELECT * FROM products WHERE listed_by=? ORDER BY id DESC", (username,)).fetchall()
    ]
    return render_template("pl_dashboard.html", products=products)


@app.route("/pl/main-categories", methods=["GET", "POST"])
@pl_required
def pl_main_categories():
    if request.method == "POST":
        handle_main_category_form()
        return redirect(url_for("pl_main_categories"))
    return render_template(
        "manage_main_categories.html",
        categories=get_db().execute("SELECT * FROM main_categories ORDER BY id").fetchall(),
        back_url=url_for("pl_dashboard"),
        save_url=url_for("pl_main_categories"),
    )


@app.route("/pl/sub-categories", methods=["GET", "POST"])
@pl_required
def pl_sub_categories():
    if request.method == "POST":
        handle_sub_category_form()
        return redirect(url_for("pl_sub_categories"))
    return render_template(
        "manage_sub_categories.html",
        categories=get_db().execute("SELECT * FROM sub_categories ORDER BY product_type, id").fetchall(),
        product_types=PRODUCT_TYPES,
        back_url=url_for("pl_dashboard"),
        save_url=url_for("pl_sub_categories"),
    )


@app.route("/pl/new", methods=["GET", "POST"])
@pl_required
def pl_listing_new():
    if request.method == "POST":
        try:
            save_product_from_form()
            flash("Product created successfully.", "success")
            return redirect(url_for("pl_dashboard"))
        except (IntegrityError, ValueError) as error:
            flash(f"Product was not saved: {error}", "error")
    return render_template("admin_product_form.html", **product_form_context())


@app.route("/pl/<int:product_id>/edit", methods=["GET", "POST"])
@pl_required
def pl_listing_edit(product_id):
    row = fetch_pl_owned_product(product_id)
    item = product(row)
    if request.method == "POST":
        try:
            save_product_from_form(product_id=product_id)
            flash("Product updated successfully.", "success")
            return redirect(url_for("pl_dashboard"))
        except (IntegrityError, ValueError) as error:
            flash(f"Product was not updated: {error}", "error")
            item = product(fetch_pl_owned_product(product_id))
    return render_template("admin_product_form.html", **product_form_context(item))


@app.post("/pl/<int:product_id>/delete")
@pl_required
def pl_listing_delete(product_id):
    fetch_pl_owned_product(product_id)
    get_db().execute("DELETE FROM products WHERE id=? AND listed_by=?", (product_id, session.get("pl_username")))
    get_db().commit()
    flash("Product deleted.", "success")
    return redirect(url_for("pl_dashboard"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
