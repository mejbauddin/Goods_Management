 GoodsHub — Goods Management Module
Software Design and Architecture Course Project  
Group 2

 Overview
GoodsHub is a Flask and SQLite prototype for managing goods information
within a logistics transit warehouse system.

The module manages registered goods types. Its record counts do not
represent warehouse stock quantities.

 Features
- Register, edit, search, and filter goods.
- Create, rename, and delete unused categories.
- Archive and restore goods.
- Permanently delete archived goods while retaining their history.
- Display before-and-after changes in an audit history.
- Upload goods photos and display dashboard thumbnails.
- Import new goods from CSV with validation and duplicate protection.
- Export goods matching the current search and status filters.
- Display summary counts and recently registered goods.

Scope
This project implements Group 2's Goods Management module.
User authentication, warehouse stock quantities, storage allocation,
inbound receiving, outbound dispatch, and shipment tracking are outside
this prototype's implemented scope.
The prototype is intended for a local classroom demonstration.

Technology
- Python
- Flask and Jinja templates
- SQLite
- Pillow for image processing
- HTML and CSS

Installation — Windows PowerShell
Open a terminal in the folder containing app.py.
The project was developed using Python 3.13.7.
Create a virtual environment:
```powershell
py -3.13 -m venv .venv
```
Install dependencies:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
Start the application:
```powershell
.\.venv\Scripts\python.exe -m flask --app app run
```
Open:
http://127.0.0.1:5000/
To stop the server, press Ctrl+C.

Database Initialization
The application creates missing database tables and adds the photo
column automatically at startup.
If the instance folder is included, the application uses its existing
database and photos.
If starting without an instance folder, the application starts with
an empty database. Add categories through the Categories page before
registering or importing goods.

Main Files
| File | Responsibility |
|---|---|
| app.py | HTTP routes, forms, and page rendering |
| database.py | SQLite connections and initial schema |
| goods_repository.py | Goods validation, storage, and lifecycle operations |
| category_repository.py | Category operations and deletion protection |
| audit_repository.py | Goods history and deleted-record history retrieval |
| dashboard_repository.py | Summary counts and recently registered goods |
| photo_repository.py | Photo database column and photo-change logging |
| photo_storage.py | Image validation and file storage |
| csv_import_service.py | CSV parsing and row-by-row goods import |
| templates/ | Jinja HTML pages |

Data Storage
- Database: instance/goodshub.sqlite3
- Photos: instance/goods_photos/
- Local session signing key: instance/secret.key
The application generates a session key if one does not exist.
Do not include an existing secret.key in a shared submission package.

CSV Import
Use UTF-8 encoding and these exact column headings:
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
- Valid rows are saved; invalid rows receive individual error messages.
- Existing goods are not overwritten.
- Photos are uploaded separately.
The exported CSV report uses a different format and cannot be imported
directly without converting its columns.

Goods Photos
Supported input formats: JPG, PNG, and WebP.
Maximum upload size: 5 MB.
Maximum accepted image area: 20 million pixels.
Images are resized to fit within 1200 × 1200 pixels and saved as JPEG
files with generated filenames.
Replacing a photo retains the previous file. Automatic cleanup of
historical photo files is not implemented.

Important Business Rules
- Goods must be archived before permanent deletion.
- Permanent deletion retains the goods audit history.
- Categories used by active or archived goods cannot be deleted.
- Goods changes and their audit entries are saved together in a
  database transaction.
- Dashboard totals count registered goods records, not stock units.

Backup
1. Stop the application.
2. Copy the project folder, including the entire instance folder.
3. Keep the backup separate from the working folder.
The database and photo files must be backed up together.

Manual Demonstration
1. Create a category.
2. Register a goods record.
3. Edit it and inspect its history.
4. Upload a photo and check the dashboard thumbnail.
5. Search and filter goods.
6. Export a filtered CSV report.
7. Import new goods from CSV.
8. Repeat the import to demonstrate duplicate protection.
9. Import invalid data to demonstrate validation.
10. Archive, restore, and then archive a test record again.
11. Permanently delete the test record.
12. Open its retained history from Deleted goods history.