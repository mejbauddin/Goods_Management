# GoodsHub — Goods Management Module

Software Design and Architecture Course Project
Group 2

## Overview

GoodsHub is a Flask and SQLite goods registry for a logistics transit
warehouse. It is the Goods Management module: it manages registered goods
**types** — codes, categories, units, declared weight, photos and the audit
history around them. Record counts are catalogue entries, not stock quantities.

Version 2.0.0 rebuilds the entire interface on a new design system and adds a
live operations console. **No repository contract, validation rule or audit
rule changed** — the rebuild is presentation plus new read-only observability
endpoints.

## Features

Registry

- Register, edit, search and filter goods.
- Create, rename and delete unused categories.
- Archive and restore goods.
- Permanently delete an archived record while keeping its history.
- Before/after audit history per record, retained after deletion.
- Upload a goods photo and show thumbnails in the catalogue.
- Import goods from CSV with validation and duplicate protection.
- Export goods matching the current search and status filters.

Interface and operations console

- Dark/light design system with a single token layer and no CSS framework.
- Live dashboard: hero, KPI cards with sparklines, intake pipeline strip,
  monthly intake area chart, status donut, category bars, 14-day activity
  heatmap, category atlas, recent registrations and a live event stream.
- `/flow` operations console: three animated SVG diagrams — goods lifecycle
  state machine, intake pipeline, and the audit write path — driven by the
  same SQL snapshot as the catalogue, with moving particles along each path
  and a Pause control.
- Dependency-free SVG chart engine (`static/js/charts.js`) for area, donut,
  bars and sparklines, with draw-in animation, hover tooltips and legends.
- `/api/live` polling updates every live counter in place, and `/api/ops`
  exposes the full operations snapshot as JSON.
- Reveal-on-scroll, count-up numbers, theme persistence, custom confirmation
  dialogs, drag-and-drop file zones, reduced-motion and print support.

Scope

This project implements Group 2's Goods Management module. User
authentication, warehouse stock quantities, storage allocation, inbound
receiving, outbound dispatch and shipment tracking are outside this
prototype's implemented scope. The prototype targets a local classroom
demonstration.

## Technology

- Python 3.13
- Flask 3.1 and Jinja templates
- SQLite
- Pillow for image processing
- HTML, hand-written CSS and vanilla JavaScript (no build step, no CDN)

## Installation — Windows PowerShell

Open a terminal in the folder containing `app.py`.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app app run
```

Then open <http://127.0.0.1:5000/>. Press Ctrl+C to stop the server.

## Database initialisation

The application creates missing tables and adds the photo column at startup.
If the `instance` folder is present, its database and photos are used.
Starting without it gives an empty database — add categories on the Categories
page before registering or importing goods.

## Main files

| File | Responsibility |
|---|---|
| `app.py` | HTTP routes, form parsing, CSRF, security headers, error pages |
| `database.py` | SQLite connections, schema bootstrap, backups |
| `goods_repository.py` | Goods validation, storage, lifecycle operations |
| `category_repository.py` | Category operations and deletion protection |
| `audit_repository.py` | Goods history and deleted-record history retrieval |
| `dashboard_repository.py` | Summary counts and recently registered goods |
| `photo_repository.py` | Photo column, photo change logging |
| `photo_storage.py` | Image validation and file storage |
| `csv_import_service.py` | CSV parsing and row-by-row import |
| `flow_repository.py` | Read-only operations snapshot (`/flow`, `/api/live`, `/api/ops`) |
| `templates/` | Jinja pages: layout, macros, dashboard, flow, registry, … |
| `static/css/app.css` | Design system: tokens, layout, components, motion |
| `static/js/charts.js` | SVG chart engine |
| `static/js/app.js` | Theme, navigation, reveal, polling, dialogs, dropzones |
| `static/img/` | Logo artwork and generated illustration set |

## Data storage

- Database: `instance/goodshub.sqlite3`
- Photos: `instance/goods_photos/` (thumbnails in `thumbs/`)
- Settings: `instance/settings.json`
- Backups: `instance/backups/`
- Local session signing key: `instance/secret.key`

The application generates a session key if one does not exist. Do not include
an existing `secret.key` in a shared submission package.

## CSV import

Use UTF-8 encoding and these column headings:

```csv
code,name,category,unit,weight,description
IMP-001,USB cable,Electronics,Piece,0.05,One metre cable
IMP-002,Notebook,Office Supplies,Piece,0.20,A5 notebook
```

Rules:

- Categories must already exist.
- Goods codes must be unique.
- Allowed units: Piece, Box, Pack, Bag, Bottle, Set, Roll.
- Weight must be greater than zero and at most 1,000,000 kg.
- Maximum import size: 500 goods and 2 MB.
- Imported goods start as Active.
- Valid rows are saved; invalid rows receive individual messages.
- Existing goods are not overwritten.
- Photos are uploaded separately.

The exported CSV uses a wider report format and is not directly re-importable.

## Goods photos

Supported input formats: JPG, PNG and WebP. Maximum upload size: 5 MB.
Maximum accepted image area: 20 million pixels. Images are resized to fit
within 1200 × 1200 and stored as JPEG with generated filenames. Replacing a
photo deletes the previous file after the new filename is committed.

## Important business rules

- Goods must be archived before permanent deletion.
- Permanent deletion keeps the goods audit history.
- Categories used by active or archived goods cannot be deleted.
- Goods changes and their audit entries are written in one transaction.
- Dashboard totals count registered goods records, not stock units.
- Deletion requires an explicit confirmation step in addition to the archived
  state.

## Backup

1. Stop the application.
2. Copy the whole project folder, including `instance`.
3. Keep the copy separate from the working folder.

The Settings page can also write a consistent copy to `instance/backups/` and
keeps the ten most recent files.

## Manual demonstration

1. Create a category.
2. Register a goods record.
3. Edit it and inspect its history.
4. Upload a photo and check the dashboard thumbnail.
5. Search and filter goods.
6. Export a filtered CSV report.
7. Import new goods from CSV; repeat to show duplicate protection.
8. Import invalid data to show validation messages.
9. Archive, restore, then archive a test record again.
10. Permanently delete the test record and open its retained history.
11. Open **Operations flow** and pause/resume the diagrams while talking.
12. Switch theme with the header button and reload to show persistence.
