# GoodsHub — UML Diagrams

Course: Software Design and Architecture
Team: Group 2
Module: Goods Management

## 1. Use Case Diagram

This diagram describes the actions available to a GoodsHub user.

The prototype has no login or role-based permissions. Operators and
managers can use the same interface; their business responsibilities
do not restrict access in the current implementation.

```plantuml
@startuml
title GoodsHub — Use Case Diagram
left to right direction

actor "GoodsHub User\n(Operator or Manager)" as User

rectangle "Goods Management Module" {
    usecase "Register goods" as Register
    usecase "Edit goods" as Edit
    usecase "Search and filter goods" as Search
    usecase "Manage categories" as Categories
    usecase "Archive goods" as Archive
    usecase "Restore goods" as Restore
    usecase "Permanently delete\narchived goods" as Delete
    usecase "View goods history\nincluding deleted goods" as History
    usecase "Upload or replace photo" as Photo
    usecase "Import goods from CSV" as Import
    usecase "Export filtered goods" as Export
    usecase "View dashboard" as Dashboard
}

User -- Register
User -- Edit
User -- Search
User -- Categories
User -- Archive
User -- Restore
User -- Delete
User -- History
User -- Photo
User -- Import
User -- Export
User -- Dashboard

note bottom of Delete
Precondition: the goods record is archived.
The user must confirm permanent deletion.
end note
@enduml
```

“Manage categories” includes creating, renaming, and deleting unused
categories. Audit logging is an internal responsibility rather than
a separate user action.

## 2. Class Diagram — Conceptual Domain Model

This diagram models the domain concepts.

The current Python implementation uses functions, SQLite rows, and
dictionaries. It does not define Python classes named Goods, Category,
or AuditEntry. These are conceptual classes used to explain the data.

```plantuml
@startuml
title GoodsHub — Conceptual Class Diagram
hide methods
skinparam classAttributeIconSize 0

class Category <<domain concept>> {
    id : Integer
    name : String
}

class Goods <<domain concept>> {
    id : Integer
    code : String
    name : String
    category_id : Integer
    unit : String
    weight : Real
    description : String
    status : String
    created_at : Timestamp
    updated_at : Timestamp
    photo_filename : String
}

class AuditEntry <<historical record>> {
    id : Integer
    entity_type : String
    entity_id : Integer
    entity_label : String
    action : String
    before_json : String [0..1]
    after_json : String [0..1]
    created_at : Timestamp
}

Category "1" -- "0..*" Goods : classifies

AuditEntry ..> Goods : may describe changes to
AuditEntry ..> Category : may describe changes to

note bottom of Goods
code is unique.
status is active or archived.
photo_filename may be empty.
end note

note bottom of AuditEntry
The dashed dependencies indicate historical references.
entity_type and entity_id identify the subject.
There is no database foreign key to the subject.
History survives deletion of the live record.
end note
@enduml
```

The category relationship is a normal association, not composition:
deleting a category does not automatically delete its goods.

## 3. Sequence Diagram — Register Goods

This diagram shows successful registration and important error paths.

The SQLite participant abstracts the connection obtained through
database.py. Template rendering is summarized in the HTTP responses.

```plantuml
@startuml
title GoodsHub — Register Goods Sequence

actor User
boundary "Browser" as Browser
control "app.py" as App
control "goods_repository.py" as Repo
database "SQLite" as DB

User -> Browser : Submit registration form
Browser -> App : POST /goods with fields and CSRF token

alt Missing or invalid CSRF token
    App --> Browser : HTTP 400
    Browser --> User : Display request error
else Valid CSRF token
    App -> App : Read fields and parse category ID

    alt Category ID cannot be parsed
        App --> Browser : Render form with validation message
        Browser --> User : Display validation message
    else Category ID parsed
        App -> Repo : add_goods(...)

        Repo -> Repo : Validate code, name, unit,\nweight and description

        alt Invalid goods fields
            Repo --> App : Raise ValueError
            App --> Browser : Render form with validation message
            Browser --> User : Display validation message
        else Valid goods fields
            Repo -> DB : SELECT category by ID
            DB --> Repo : Category or no match

            alt Category does not exist
                Repo --> App : Raise ValueError
                App --> Browser : Render form with validation message
                Browser --> User : Display validation message
            else Category exists
                group One database transaction
                    Repo -> DB : INSERT goods

                    alt Duplicate goods code
                        DB --> Repo : Unique constraint error
                        Repo -> DB : ROLLBACK
                        Repo --> App : Raise ValueError
                    else Insert succeeds
                        DB --> Repo : New goods ID
                        Repo -> DB : SELECT saved goods snapshot
                        DB --> Repo : Saved record
                        Repo -> DB : INSERT Created audit entry
                        Repo -> DB : COMMIT
                        Repo --> App : Return goods ID
                    end
                end

                alt Registration succeeded
                    App --> Browser : Redirect to /goods
                    Browser -> App : GET /goods
                    App --> Browser : Render updated goods list
                    Browser --> User : Display goods and success message
                else Duplicate rejected
                    App --> Browser : Render form with validation message
                    Browser --> User : Display duplicate-code message
                end
            end
        end
    end
end
@enduml
```

The diagram highlights the normal and validation paths. Other database
failures before commit also cause the transaction to roll back.

## 4. Activity Diagram — Permanent Goods Deletion

This diagram describes the web deletion workflow.

The repository rechecks the goods record and its status inside the
transaction before deleting it.

```plantuml
@startuml
title GoodsHub — Permanent Deletion Activity

start
:Open goods deletion page;
:Load goods record;

if (Record exists?) then (yes)
else (no)
    :Return HTTP 404;
    stop
endif

if (Record is archived?) then (yes)
else (no)
    :Explain that archiving is required;
    :Redirect to goods list;
    stop
endif

:Display deletion warning\nand confirmation checkbox;

if (User chooses Cancel?) then (yes)
    :Return to goods list;
    stop
else (no)
    :Submit deletion form;
endif

if (CSRF token valid?) then (yes)
else (no)
    :Return HTTP 400;
    stop
endif

if (Confirmation supplied?) then (yes)
else (no)
    :Show confirmation-required message;
    :Redisplay confirmation page;
    stop
endif

:Begin database transaction;
:Reload goods record;

if (Record still exists and is archived?) then (yes)
else (no)
    :Roll back transaction;
    :Report validation error;
    stop
endif

:Capture previous goods values;
:Delete goods record;
:Insert Deleted audit entry\nwith previous snapshot;

if (Database operations succeed?) then (yes)
    :Commit transaction;
    :Redirect to retained goods history;
    :Display deleted-record notice and events;
else (no)
    :Roll back transaction;
    :Propagate database error;
endif

stop
@enduml
```

Archiving is a separate operation. It is a precondition for deletion,
not an automatic step performed by the deletion page.

## 5. Component Diagram

This diagram shows the main implementation modules and their
dependencies.

The repositories are grouped to keep the diagram readable.

```plantuml
@startuml
title GoodsHub — Component Diagram
top to bottom direction
skinparam componentStyle uml2

component "Web Browser" as Browser

package "GoodsHub Flask Application" {
    component "Routes and CSV Export\napp.py" as App
    component "HTML Presentation\ntemplates/" as Templates
    component "CSV Import\ncsv_import_service.py" as CSV
    component "Image Processing\nphoto_storage.py" as Photos

    component "Repository Modules" as Repos
    component "Database Connections and Schema\ndatabase.py" as DatabaseAccess
}

database "SQLite\ninstance/goodshub.sqlite3" as SQLite
folder "Photo Storage\ninstance/goods_photos/" as Files

Browser --> App : HTTP requests
App --> Templates : render
App --> CSV : import file
App --> Photos : validate and save image
App --> Repos : read or change data
CSV --> Repos : look up categories and add goods
Repos --> DatabaseAccess : open connections
App --> DatabaseAccess : initialize schema at startup
DatabaseAccess --> SQLite : SQL connections
Photos --> Files : write JPEG files
App --> Files : serve requested photo

note bottom of Repos
goods_repository.py
category_repository.py
audit_repository.py
dashboard_repository.py
photo_repository.py
end note
@enduml
```

The browser receives HTML rendered through Flask and Jinja.

Repository functions that mutate goods or categories also insert their
audit entries. audit_repository.py is responsible for retrieving
history, not writing every audit event.

## 6. Traceability to Requirements

| Diagram | Main requirements explained |
|---|---|
| Use Case | FR-01 through FR-14: user-visible functions |
| Conceptual Class | Goods, categories, and audit-history data concepts |
| Registration Sequence | FR-01, FR-02, FR-09: registration, uniqueness, and audit creation |
| Deletion Activity | FR-08, FR-10: confirmed deletion and retained history |
| Component | Maintainability and separation of implementation responsibilities |

## 7. Diagram Interpretation

- The diagrams describe the implemented Goods Management scope.
- Business roles are not enforced access-control roles.
- The conceptual class diagram does not claim that corresponding
  Python classes already exist.
- Historical audit references are not database foreign keys.
- SQLite and image files are separate storage mechanisms.
- Other warehouse modules are outside this implementation.