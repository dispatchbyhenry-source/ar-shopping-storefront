# AR Shopping World — Python Backend

Red-themed Flask + **PostgreSQL** e-commerce application with hashed admin auth, customer profiles, category management, colour/size stock tables, and marketplace links.

## Setup

### 1. Start PostgreSQL

With Docker (recommended):

```bash
docker compose up -d
```

Or use any PostgreSQL 14+ server and set `DATABASE_URL` in `.env`.

Default local URL from `docker-compose.yml`:

```text
postgresql://arshop:arshop@127.0.0.1:5432/ar_shopping_world
```

### 2. Install and run the app

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env        # then edit values if needed
python app.py
```

Open `http://127.0.0.1:5000`. Tables are created and seeded automatically on first launch.

## Environment (`.env`)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | Flask session secret |
| `ADMIN_USERNAME` | Admin login username |
| `ADMIN_PASSWORD_HASH` | Werkzeug password hash (not plain text) |

Generate a new admin hash:

```bash
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('YourStrongPassword'))"
```

Default local admin (change before deployment): username `admin`, password `ChangeMe123!`.

## Accounts

- **Buyers** can browse and checkout as guests.
- **Contact** and **Sell Product** require a customer profile (register / sign in).
- Profile page: `/profile`

## Admin

- Login: `/admin/login`
- Edit categories next to **Add product**
- Products support: name ≤100 chars, description ≤3000, up to 10 colours with stock, sizes table, 10 images, Amazon / Etsy / eBay links

## Sell listings

Sellers must be signed in and can upload up to 3 images per listing.

## Notes

- The old `store.db` SQLite file is no longer used and can be deleted.
- For production, use a managed PostgreSQL service (Neon, Railway, Render, AWS RDS, etc.) and set `DATABASE_URL` accordingly.
