# Project Proposal — GoodsHub

**Course:** Software Design and Architecture  
**Course project:** Development of a Logistics Transit Warehouse Operation and Maintenance System  
**Team and module:** Group 2 · Goods Management

## 1. Problem and objective

A warehouse operator needs to know whether a product already has a catalog entry before registering it. Two records called “USB cable” can describe different products, while two entries for the same cable can cause confusion about which weight or unit to use. If someone later corrects a weight, the manager also needs to see the previous value and when it changed.

Group 2 proposes GoodsHub, a shared catalog in which each goods type has a unique code, a category, a unit, and a weight per unit. The objective is to let staff find the right record, maintain it throughout its life, and explain changes using its history.

## 2. Users and scope

The **goods management operator** registers and edits goods, organizes categories, attaches photos, and imports or exports catalog data. The **warehouse manager** reviews recent registrations, active and archived records, and change history. Both use the same interface in the classroom prototype. User accounts and permissions belong to the wider system.

Group 2 owns the information describing each goods type. For example, a catalog entry can say that one USB cable weighs 0.05 kg. Stock counts, receiving and dispatch, storage locations, and shipment tracking belong to other warehouse modules.

## 3. Proposed workflow

1. The operator searches by code or name before registering a product. GoodsHub checks the code, category, unit, and weight before saving the record.
2. When a product detail changes, the operator edits the record. The history shows the previous value, the new value, and the time of the change.
3. When the warehouse stops using a goods type, the operator archives it. An archived record can be restored. Permanent deletion requires confirmation, and its history remains available afterward.
4. For larger catalog updates, the operator imports new goods from CSV and reviews the result for each row. A filtered CSV export supports reporting. Photos help users recognize products, and the dashboard shows recent registrations and catalog counts.

## 4. Technical design

GoodsHub will run locally as one Python Flask application. Jinja templates provide the browser interface. Flask routes handle form submissions, repository modules read and write SQLite records, and separate modules process CSV files and photos. This structure lets the team change an import rule or a page layout without putting both responsibilities in the same file.

The database design uses three main tables: `categories`, `goods`, and `audit_log`. Each goods record references a category. A goods change and its audit entry are saved in one transaction so that the history matches the saved record. The audit entry keeps enough information to describe a deleted item. Photo files are stored locally, and the goods record stores the filename.

## 5. Deliverables and verification

The team will document requirements in the SRS, describe the architecture and database relationships, and provide use case, class, sequence, activity, and component diagrams. The working prototype and testing report will support the final written report, PowerPoint presentation, and classroom demonstration.

| Demonstration | Expected result |
|---|---|
| Register a USB cable, then submit the same code again | The catalog contains one record with that code and one creation event. The second submission reports a duplicate. |
| Correct the cable's weight | The catalog shows the corrected weight. History shows both values and the time of the change. |
| Try to delete an active item, then archive it and confirm deletion | The first attempt is rejected. After confirmed deletion, the catalog entry disappears and its history can still be opened. |
| Import one valid row and one row with an unknown category | The valid item is created. The results identify the rejected row and explain the category error. |
| Upload a photo for a recently registered item and export a filtered list | The thumbnail appears in the catalog and dashboard. The export contains the records matching the selected filters. |

The testing report will record the observed results and any remaining issues. The final presentation will follow one product from registration through a change and show how a manager can trace its history.
