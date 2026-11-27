# Software Requirements Specification
## GoodsHub — Goods Management Module

Course: Software Design and Architecture
Project: Logistics Transit Warehouse Operation and Maintenance System
Team: Group 2
Document version: 1.0

## 1. Purpose

GoodsHub manages goods information for a logistics transit warehouse.
It provides a central catalog where users can register goods, maintain
their details, organize categories, upload photos, and review changes.

This document defines the requirements for the Group 2 Goods Management
prototype.

## 2. Scope

The implemented module includes:

- Goods registration, editing, searching, and filtering.
- Category creation, renaming, and deletion.
- Goods archiving and restoration.
- Permanent deletion of archived goods.
- Retained goods change history.
- Goods photo uploads.
- CSV import and export.
- A dashboard with summary counts and recently registered goods.

The module records goods types, not physical warehouse stock quantities.

The following functions are outside this prototype's scope:

- User accounts, login, and role-based permissions.
- Inbound receiving and outbound dispatch.
- Storage-location allocation.
- Stock quantity management.
- Shipment tracking.

These functions belong to other modules of the wider warehouse system.

## 3. Intended Users

### 3.1 Goods Management Operator

Registers goods, updates their details, organizes categories, manages
photos, and imports or exports catalog information.

### 3.2 Warehouse Manager

Reviews the catalog, dashboard, archived records, and goods change history.

These are intended business roles. The current prototype does not
authenticate users or enforce different permissions between these roles.

## 4. Operating Environment

- Browser-based interface.
- Python and Flask application.
- Jinja HTML templates.
- SQLite database.
- Pillow for image processing.
- Local filesystem storage for photos.
- Developed on Windows using Python 3.13.7.

The prototype runs locally for development and classroom demonstration.

## 5. Functional Requirements

| ID | Requirement |
|---|---|
| FR-01 | The system shall register goods with a code, name, category, unit, weight, and optional description. |
| FR-02 | The system shall reject duplicate goods codes. |
| FR-03 | The system shall allow users to edit existing goods details. |
| FR-04 | The system shall search goods by code or name and filter them by Active, Archived, or All statuses. |
| FR-05 | The system shall create categories with unique names and allow category renaming. |
| FR-06 | The system shall delete a category only when no active or archived goods reference it. |
| FR-07 | The system shall archive active goods and restore archived goods. |
| FR-08 | The system shall allow permanent deletion only for archived goods and require confirmation through the web interface. |
| FR-09 | The system shall record goods creation, updates, status changes, photo changes, and deletion in an audit history. |
| FR-10 | The system shall retain and display goods history after permanent deletion. |
| FR-11 | The system shall accept validated goods photos and display thumbnails in the catalog and dashboard. |
| FR-12 | The system shall import new goods from a CSV file and report the outcome of each processed row. |
| FR-13 | The system shall export goods matching the selected search and status filters as CSV. |
| FR-14 | The dashboard shall display total, active, and archived goods counts, the category count, and up to five recently registered goods. |

## 6. Data Validation Rules

| Field | Rule |
|---|---|
| Goods code | Required; 2–30 characters; trimmed and converted to uppercase; unique. |
| Goods name | Required; 1–120 characters after trimming. |
| Category | Must reference an existing category. |
| Category name | Required; 1–60 characters after trimming; unique without regard to ASCII letter case. |
| Unit | Piece, Box, Pack, Bag, Bottle, Set, or Roll. |
| Weight | A finite number greater than zero and no greater than 1,000,000 kg. |
| Description | Optional; maximum 2,000 characters. |
| Status | Active or Archived. |
| Photo | Valid JPEG, PNG, or WebP; at most 5 MB and 20 million pixels. |

Photos shall be resized to fit within 1200 × 1200 pixels and stored
as JPEG files with generated filenames.

## 7. CSV Import Requirements

The file shall use UTF-8 encoding and this exact header order:

code,name,category,unit,weight,description

- The file shall contain at most 500 non-empty goods rows.
- The file size shall not exceed 2 MB.
- Category names shall already exist.
- Imported goods shall start as Active.
- Existing goods shall not be overwritten.
- Valid rows shall be saved independently.
- Invalid rows shall be reported with their CSV line and error message.
- File structure shall be checked before goods are saved.
- Photos shall be uploaded separately.

CSV import and CSV export use different column formats.
The exported report is not a direct re-import or database backup format.

## 8. Business Rules

BR-01: Dashboard totals represent goods records, not stock quantities.

BR-02: Archiving retains the goods record and allows later restoration.

BR-03: Permanent deletion removes the goods record from the catalog,
but retains its audit history.

BR-04: Active goods must be archived before permanent deletion.

BR-05: A category referenced by any goods record cannot be deleted,
including when all associated goods are archived.

BR-06: Goods mutations and their audit entries shall be committed
together in a database transaction.

BR-07: History shall be presented newest first, with timestamps
identified as UTC.

BR-08: Replacing a photo shall update the current photo reference
while retaining the previous image file.

## 9. Non-Functional Requirements

### 9.1 Usability

Forms shall have clear labels and validation messages.
The interface shall distinguish active and archived goods.
Permanent deletion shall explain that the action cannot be undone.

### 9.2 Data Integrity

The database shall enforce goods-category relationships, uniqueness,
and applicable field constraints.

Failed transactional operations shall not leave a goods change without
its corresponding audit entry.

### 9.3 Request and Input Protection

State-changing web forms shall validate a session-based CSRF token.
Database queries shall use parameters for user-provided values.
Uploaded images shall be decoded and validated before storage.
Stored photo filenames shall be generated by the application.

These protections do not replace authentication or authorization.

### 9.4 Maintainability

Routing, database access, CSV processing, photo processing, and HTML
presentation shall be organized into separate files.

### 9.5 Persistence and Recovery

Goods, categories, and audit history shall persist in SQLite.
Photo files shall persist in the instance folder.

A complete backup shall include the database and photos.
The application shall be stopped before a simple filesystem backup.

### 9.6 Performance Scope

The prototype targets a small classroom demonstration dataset.
High-volume throughput and concurrent multi-user performance have
not been established by load testing.

## 10. Acceptance Criteria

| ID | Scenario | Expected outcome |
|---|---|---|
| AC-01 | Register valid goods | One goods record and a Created history event are saved. |
| AC-02 | Register an existing code | Validation rejects the duplicate. |
| AC-03 | Edit goods | Updated details and before/after history are available. |
| AC-04 | Archive and restore goods | Status and dashboard counts reflect each change. |
| AC-05 | Delete active goods | Deletion is rejected. |
| AC-06 | Confirm deletion of archived goods | The catalog record is removed and history remains available. |
| AC-07 | Delete a category used by goods | Deletion is rejected. |
| AC-08 | Upload a valid photo | The photo appears on its page, the goods list, and the dashboard. |
| AC-09 | Upload an invalid image | The upload is rejected without replacing the current photo. |
| AC-10 | Import valid CSV rows | New goods and Created history events are saved. |
| AC-11 | Import duplicate or invalid rows | Errors are reported and rejected rows are not saved. |
| AC-12 | Import mixed valid and invalid rows | Valid rows are saved and invalid rows are reported. |
| AC-13 | Export filtered goods | The CSV contains the matching goods records. |
| AC-14 | Submit a missing or invalid CSRF token | The state-changing request is rejected. |

These criteria define expected behavior. Actual test results are recorded
separately in the testing report.

## 11. Known Limitations

- No login or role-based access control.
- No stock quantities, storage locations, or shipment operations.
- No automatic cleanup of historical photo files.
- No browser interface for category audit history.
- CSV imports can partially succeed; they are not one batch transaction.
- No measured high-volume or concurrent-user performance guarantee.