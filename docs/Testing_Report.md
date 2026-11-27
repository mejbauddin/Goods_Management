# GoodsHub — Software Testing Report

Course: Software Design and Architecture
Team: Group 2
Module: Goods Management
Version: 1.0

## 1. Objective

Verify that the Goods Management prototype performs its main operations,
rejects invalid input, and preserves goods change history.

Testing covers the implemented module only. It does not establish the
correctness of other warehouse modules.

## 2. Test Environments

### Manual testing

- Windows computer.
- Python 3.13.7 in a virtual environment.
- Flask application accessed through Chrome.
- SQLite database and local photo storage.
- Screenshots captured during execution.

### Reviewer-executed checks

The submitted source was also exercised using Flask's test client and
direct repository/service calls in a separate environment.

These checks used a temporary copy of the submitted database.
The submitted database was not modified.

The reviewer environment used Python 3.12, Flask 3.1.3, and Pillow 13.0.0.
This environment differs from the developer's Windows environment.

## 3. Testing Approach

- Functional testing of forms and pages.
- Validation testing with invalid input.
- Integration testing across routes, repositories, and SQLite.
- Audit-history checks after data changes.
- CSV import and duplicate-protection checks.
- Photo upload, retrieval, and dashboard-display checks.

## 4. Observed Manual Test Results

| ID | Test | Observed result | Status |
|---|---|---|---|
| MT-01 | Rename a category | Updated category name displayed successfully. | Passed |
| MT-02 | Submit an unchanged category name | An unchanged-name message appeared. | Passed |
| MT-03 | Use an existing category name | Duplicate name was rejected. | Passed |
| MT-04 | Delete an unused category | Category was removed and the count decreased. | Passed |
| MT-05 | Delete a category used by goods | Deletion was blocked with a usage message. | Passed |
| MT-06 | Archive and restore goods | Status changes appeared in history and dashboard counts updated. | Passed |
| MT-07 | Delete active goods through the repository | Operation was rejected with an archive-first message. | Passed |
| MT-08 | Permanently delete archived test goods | Record was deleted and its history remained accessible. | Passed |
| MT-09 | Open deleted-goods history list | Deleted test records and history links appeared. | Passed |
| MT-10 | Export goods to CSV | The exported data opened in Excel. | Passed |
| MT-11 | Upload a valid image | Saved image appeared on the photo page and goods table. | Passed |
| MT-12 | Inspect photo history | Photo_updated event contained the saved filename. | Passed |
| MT-13 | Display photo on dashboard | Existing thumbnail appeared after correcting the dashboard query. | Passed |
| MT-14 | Import sample goods | IMP-001 and IMP-002 appeared in the goods list. | Passed |
| MT-15 | Repeat the sample import | Both duplicate codes were rejected. | Passed |
| MT-16 | Inspect imported goods history | Each imported record had a Created event. | Passed |
| MT-17 | Import negative weight, unknown category, and invalid unit | All three rows were rejected; the goods list remained at four records. | Passed |
| MT-18 | Check installed package dependencies | pip check reported no broken requirements. | Passed |

## 5. Reviewer-Executed Checks

The reviewer reported 21 successful checks:

- Ten GET requests returned HTTP 200:
  dashboard, goods, categories, edit page, goods history, photo page,
  CSV import page, deleted-goods list, deleted-record history,
  and CSV export.
- An invalid goods status filter returned HTTP 400.
- A goods submission without a CSRF token returned HTTP 400.
- Goods creation and editing saved the expected values.
- Duplicate goods codes were rejected.
- Active-goods deletion was rejected.
- Deletion of a used category was rejected.
- Archive, restore, deletion, and retained history worked together.
- An unused category could be deleted.
- A mixed CSV import saved one valid row and rejected one invalid row.
- Photo upload, file serving, and dashboard photo display worked.
- A fake image upload was rejected.

These checks provide focused functional evidence. They are not a
complete automated regression suite.

## 6. Defects Found and Corrections

### D-01: Photo link outside the goods loop

Symptom:
The goods page raised a Jinja error stating that item was undefined.

Cause:
A link using item.id was placed outside the goods iteration.

Correction:
Moved the Photo link into the actions cell inside the loop.

Verification:
The goods page loaded and displayed Photo links for its records.

Status: Resolved and manually verified.

### D-02: Dashboard did not display an existing photo

Symptom:
The dashboard displayed Add photo for goods that already had a photo.

Cause:
The recent-goods SELECT query omitted photo_filename.

Correction:
Added goods.photo_filename to the query.

Verification:
The dashboard displayed the saved thumbnail.

Status: Resolved and manually verified.

### D-03: Non-ASCII category CSRF token caused a server error

Symptom:
A reviewer test using a non-ASCII token raised TypeError.

Cause:
The category route compared strings directly with compare_digest,
which does not support non-ASCII string inputs.

Correction:
Encoded both token values as UTF-8 bytes before comparison.

Verification:
The developer supplied a screenshot showing the corrected code.
A runtime regression check of this exact invalid-token case remains
pending.

Status: Code correction confirmed; runtime retest pending.

## 7. Evidence

The development screenshots provide evidence of:

- Goods and category operations.
- Archive and restore history.
- Permanent deletion and retained history.
- CSV export opened in Excel.
- Photo upload and dashboard thumbnails.
- Imported goods and their Created events.
- Duplicate and invalid CSV rejection.
- Successful dependency checking.

Selected screenshots should be embedded in the final report with
captions identifying the operation and observed result.

## 8. Remaining Verification

Before final submission:

1. Retest D-03 and confirm HTTP 400 rather than a server error.
2. Verify installation from requirements.txt in a fresh environment.
3. Confirm a filtered CSV export contains only matching records.
4. Check the dashboard after the final demonstration data is prepared.
5. Confirm the submission copy includes the database and required photos.

Record actual results before marking these checks as passed.

## 9. Testing Limitations

- No load or stress testing was performed.
- No comprehensive concurrent-user testing was performed.
- No full security assessment was performed.
- Not every field-length or file-size boundary was tested.
- Database crash recovery and disk-failure behavior were not tested.
- Other warehouse modules and cross-module integration were not tested.

## 10. Conclusion

The observed tests support the main Goods Management demonstration
workflows, including data maintenance, validation, photos, CSV import,
and retained history.

The results do not establish production readiness.
The remaining verification items must be completed or reported as
limitations in the final submission.