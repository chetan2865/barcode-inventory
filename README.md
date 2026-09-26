# Barcode Inventory

A Django inventory and invoicing application for stock held as product variants:
each intake is tracked separately, carries its own barcode, and can be scanned
straight onto a GST tax invoice.

## What it does

**Dynamic schema.** The Item Registration form is not hardcoded. Field Master
defines every field — name, type, size, whether it is mandatory, hidden, part of
the SKU code, or printed in an invoice description — and the form, the tables and
the SKU builder all follow from it. The schema is stored as a single Master JSON
document in the database.

**SKU codes.** Fields marked *Include in SKU* are combined, in order, into a code
such as `LYC-HAL-BLA-001`. The trailing number is decided globally by the
combination of non-prefix variant values, so the same combination always resolves
to the same number regardless of product or prefix.

**Entries, not stock levels.** A product holds entries; each entry is one intake
with its own quantity and cost, and carries one SKU. Quantities of separate
entries are never merged — two intakes of the same variant share a code but stay
distinct rows.

**Barcodes per entry.** Every entry gets its own Code128 barcode
(`SKU code - entry id`), so scanning resolves to that exact intake. A barcode the
material arrived with can be stored alongside; scanning either finds the entry.

**Invoicing.** Products are added to an invoice by scanning. Tax splits into
CGST/SGST, IGST or UGST from the seller's and buyer's state codes, and the
invoice preview updates live as the form is filled.

## Layout

| Path | What lives there |
|---|---|
| `config/` | Settings, URLs, WSGI. `settings_desktop.py` is the packaged build. |
| `core/` | Shared object-type constants. |
| `field_master/` | The dynamic schema: Master JSON, field designer. |
| `items/` | Products, entries, SKU generation, quantities, barcodes. |
| `invoicing/` | Enterprises, invoices, GST calculation, invoice settings. |
| `templates/` | The shared application shell (`base.html`). |
| `static/css/app.css` | The whole design system, driven by CSS variables. |

## Running it

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

Then open <http://127.0.0.1:8000/>.

## Frontend notes

Django templates with Bootstrap 5.3 vendored locally — no build step, no npm, no
frontend framework. `static/css/app.css` loads after Bootstrap and re-skins it
through CSS variables; Bootstrap is kept as a substrate because `d-none` is the
application's show/hide mechanism in JavaScript, `items/forms.py` emits
`col-md-*` grid classes from Python, and collapse/dropdown behaviour comes from
the Bootstrap bundle.

Two things to know before restyling:

- `_sku_section_js.html` clones the first `.sku-block` to create new ones, and
  its click handler tests `e.target.classList.contains(...)`. Keep those action
  buttons text-only — an icon inside one becomes the event target and the
  handler stops firing.
- The invoice preview is driven by roughly fifty `pv-*` element IDs. Restyle the
  frame around it, not the markup inside.

## Desktop build

`barcode_inventory.spec` packages the application with PyInstaller as an offline
desktop executable, served by Waitress with WhiteNoise. New template directories
or static files must be added to its `datas` list or they will be missing from
the packaged build.

## Deploying to Railway

The application ships a production settings module separate from development
and from the desktop build, so deploying changes neither of those.

**1. Create the service.** Point Railway at this repository. Nixpacks detects
Python, installs `requirements.txt`, and runs the `buildCommand` in
`railway.json` (`collectstatic`).

**2. Add Postgres.** *New → Database → PostgreSQL* in the same project. Railway
injects `DATABASE_URL` automatically. Without it the app falls back to SQLite on
a container disk that is wiped on every deploy.

**3. Attach a Volume.** *Service → Settings → Volumes*, mounted anywhere (for
example `/data`). This is not optional: the application writes a barcode PNG for
every entry, plus uploaded signatures, logos and payment QRs. `MEDIA_ROOT`
follows `RAILWAY_VOLUME_MOUNT_PATH`, so without a volume every generated barcode
disappears on the next deploy.

**4. Set the variables.** See `.env.example`. The two that matter:

```
DJANGO_SETTINGS_MODULE = config.settings_production
BARCODE_SECRET_KEY     = <a generated key>
```

Generate the key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

The app refuses to start in production without it, deliberately.

**5. Deploy.** The `release` command in `Procfile` runs `migrate` before each
new version goes live. Railway generates the public domain and the settings
module trusts it automatically for `ALLOWED_HOSTS` and CSRF.

### Notes

- **Static files** are served by WhiteNoise with hashed filenames, gzip and
  brotli. No CDN or bucket needed.
- **Media files** are served by WhiteNoise from the volume, with
  `WHITENOISE_AUTOREFRESH` on so barcodes generated after boot are found.
- **HSTS** is off until you set `DJANGO_HSTS_SECONDS`. Turn it on only once a
  custom domain is confirmed on HTTPS — browsers cache it and it is hard to undo.
- **There is no authentication.** Every view in this application is open to
  anyone who has the URL. On a public Railway domain that means anyone can read
  and modify inventory, parties and invoices. Put the service behind
  authentication before exposing it to the internet.
