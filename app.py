"""GoodsHub - goods registry web application.

Improvements over the original version:
  * CSRF protection is centralised (one before_request hook, no copy-paste).
  * Shared helpers for form parsing and the status filter.
  * New /analytics page with charts (status, categories, units, monthly).
  * New /settings page (theme, app name, default filter, chart range),
    stored in DATA_DIR/settings.json and injected into every template.
  * Security headers, upload size limit, friendly error pages.
  * One place validates settings (validate_settings), and the "default
    status filter" setting is now actually used by the list/export pages.
  * Photo filename checks come from photo_storage, so the app and the
    upload code share exactly one rule.
"""

import csv
import hmac
import io
import json
import os
import secrets
from collections import Counter
from datetime import datetime, timezone

from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from audit_repository import (
    compute_changes,
    get_deleted_goods,
    get_goods_history,
)
from category_repository import (
    add_category,
    delete_category,
    get_all_categories,
    rename_category,
)
from csv_import_service import import_goods_csv, sample_csv
from dashboard_repository import get_dashboard_data, last_months
from database import DATA_DIR, backup_database, initialize_database
from goods_repository import (
    ALLOWED_UNITS,
    STATUS_FILTERS,
    add_goods,
    delete_goods,
    get_all_goods,
    get_goods_by_id,
    set_goods_status,
    update_goods,
)
from photo_repository import initialize_photo_column, replace_goods_photo
from photo_storage import (
    PHOTO_DIR,
    THUMB_DIR,
    delete_goods_photo,
    is_valid_photo_filename,
    save_goods_photo,
)

# --------------------------------------------------------------------------
# App setup
# --------------------------------------------------------------------------

app = Flask(__name__)

initialize_database()
initialize_photo_column()

# Keep the same session key when the application restarts.
_secret_file = DATA_DIR / "secret.key"
if not _secret_file.exists():
    _secret_file.write_text(secrets.token_hex(32), encoding="utf-8")

app.config.update(
    SECRET_KEY=_secret_file.read_text(encoding="utf-8").strip(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Reject huge uploads (photos / CSV files) early.
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    # Ordinary forms are small; refuse anything unexpectedly large.
    MAX_FORM_MEMORY_SIZE=2 * 1024 * 1024,
)

GOODS_FORM_FIELDS = (
    "code", "name", "category_id", "unit", "weight", "description"
)

# --------------------------------------------------------------------------
# Settings (stored as JSON next to the database)
# --------------------------------------------------------------------------

SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "app_name": "GoodsHub",
    "theme": "auto",                  # auto | light | dark
    "default_status_filter": "all",   # all | active | archived
    "chart_months": 6,                # 3 | 6 | 12
}

THEMES = ("auto", "light", "dark")
CHART_MONTH_CHOICES = (3, 6, 12)

MAX_APP_NAME_LENGTH = 40


def validate_settings(data, strict=True):
    """Return a complete, valid settings dict.

    Unknown keys are dropped. With strict=True a ValueError is raised for
    the first invalid value (used when saving the form); with strict=False
    the default is used instead (used when loading a hand-edited file).
    """
    clean = dict(DEFAULT_SETTINGS)

    app_name = str(data.get("app_name", "")).strip()
    if not app_name or len(app_name) > MAX_APP_NAME_LENGTH:
        if strict:
            raise ValueError(
                f"App name must be 1-{MAX_APP_NAME_LENGTH} characters."
            )
    else:
        clean["app_name"] = app_name

    for key, choices, message in (
        ("theme", THEMES, "Please choose a valid theme."),
        (
            "default_status_filter",
            STATUS_FILTERS,
            "Please choose a valid default filter.",
        ),
    ):
        value = data.get(key)
        if value in choices:
            clean[key] = value
        elif strict:
            raise ValueError(message)

    try:
        months = int(data.get("chart_months"))
    except (TypeError, ValueError):
        months = None

    if months in CHART_MONTH_CHOICES:
        clean["chart_months"] = months
    elif strict:
        raise ValueError("Please choose a valid chart range.")

    return clean


def load_settings():
    """Read settings from disk, falling back to defaults on any problem."""
    try:
        stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULT_SETTINGS)

    if not isinstance(stored, dict):
        return dict(DEFAULT_SETTINGS)

    return validate_settings(stored, strict=False)


def save_settings(settings):
    """Validate and write settings atomically (crash-safe replace).

    Returns the settings that were actually stored.
    """
    settings = validate_settings(settings)

    temp_file = SETTINGS_FILE.with_suffix(".tmp")
    temp_file.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temp_file, SETTINGS_FILE)

    return settings


def current_settings():
    if "settings" not in g:
        g.settings = load_settings()
    return g.settings


# --------------------------------------------------------------------------
# Security: CSRF, headers, template context
# --------------------------------------------------------------------------

def get_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


@app.before_request
def protect_against_csrf():
    """Check the CSRF token on every state-changing request."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    saved = session.get("csrf_token", "")
    submitted = request.form.get("csrf_token", "")

    if not saved or not hmac.compare_digest(
        saved.encode("utf-8"), submitted.encode("utf-8")
    ):
        abort(
            400,
            description="This form expired. Reload the page and try again.",
        )


@app.context_processor
def inject_globals():
    # Explicit render_template(csrf_token=...) arguments still win, so the
    # existing templates keep working unchanged.
    return {
        "csrf_token": get_csrf_token(),
        "settings": current_settings(),
    }


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


# --------------------------------------------------------------------------
# Error pages
# --------------------------------------------------------------------------

def _error_page(code, title, message):
    return render_template(
        "error.html", code=code, title=title, message=message
    ), code


@app.errorhandler(400)
def bad_request(error):
    return _error_page(
        400, "Bad request", error.description or "The request was invalid."
    )


@app.errorhandler(404)
def not_found(error):
    return _error_page(
        404, "Not found", error.description or "That page does not exist."
    )


@app.errorhandler(413)
def too_large(error):
    return _error_page(
        413, "File too large", "The uploaded file is larger than 8 MB."
    )


@app.errorhandler(500)
def server_error(error):
    return _error_page(
        500, "Something went wrong", "An unexpected error occurred."
    )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def read_status_filter(source, key="status", default=None, strict=True):
    """Return a valid status filter; abort(400) or fall back if invalid.

    A value that is present but unknown is an error (strict=True) or
    "all"; a missing value falls back to `default`, then to the saved
    "default status filter" setting.
    """
    value = source.get(key)

    if not value:
        return default or current_settings()["default_status_filter"]

    if value not in STATUS_FILTERS:
        if strict:
            abort(400, description="Invalid status filter.")
        return "all"

    return value


def read_search():
    return request.args.get("q", "").strip()


def read_goods_form():
    return {
        field: request.form.get(field, "").strip()
        for field in GOODS_FORM_FIELDS
    }


def blank_goods_form():
    form_data = {field: "" for field in GOODS_FORM_FIELDS}
    form_data["unit"] = "Piece"
    return form_data


def goods_form_from_record(item):
    """Fill the goods form with the values of an existing record."""
    return {
        "code": item["code"],
        "name": item["name"],
        "category_id": str(item["category_id"]),
        "unit": item["unit"],
        "weight": str(item["weight"]),
        "description": item["description"],
    }


def get_goods_or_404(goods_id):
    item = get_goods_by_id(goods_id)

    if item is None:
        abort(404, description="Goods record not found.")

    return item


def goods_arguments(form_data):
    """Validate the goods form and convert it to repository arguments."""
    try:
        category_id = int(form_data["category_id"])
    except (TypeError, ValueError):
        raise ValueError("Please select a category.") from None

    return {
        "code": form_data["code"],
        "name": form_data["name"],
        "category_id": category_id,
        "unit": form_data["unit"],
        "weight": form_data["weight"],
        "description": form_data["description"],
    }


# --------------------------------------------------------------------------
# Dashboard and analytics
# --------------------------------------------------------------------------

@app.get("/")
def home():
    return render_template("dashboard.html", dashboard=get_dashboard_data())


def _share(counter, limit=None):
    """Turn a Counter into rows with a percentage of the largest value."""
    rows = counter.most_common(limit)
    total = sum(counter.values()) or 1
    top = rows[0][1] if rows else 1

    return [
        {
            "label": label,
            "count": count,
            "percent": round(count * 100 / total, 1),
            "bar": round(count * 100 / top, 1),
        }
        for label, count in rows
    ]


def _number(value):
    """Return `value` as a finite float, or 0.0 when it is unusable."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0

    return number if abs(number) < float("inf") else 0.0


def _monthly_rows(created, months):
    """Build the monthly chart rows for the last `months` months."""
    month_keys = last_months(months)
    peak = max((created.get(key, 0) for key in month_keys), default=0) or 1

    rows = []

    for key in month_keys:
        moment = datetime.strptime(key, "%Y-%m")
        count = created.get(key, 0)
        rows.append({
            "label": moment.strftime("%b"),
            "full_label": moment.strftime("%B %Y"),
            "count": count,
            "height": round(count * 100 / peak, 1),
        })

    return rows


def build_analytics(goods, months):
    """Compute every number and chart row the analytics page needs."""
    total = len(goods)
    status_counts = Counter(item["status"] for item in goods)
    active = status_counts.get("active", 0)
    archived = status_counts.get("archived", 0)

    categories = Counter(
        item["category_name"] or "Uncategorised" for item in goods
    )
    units = Counter(item["unit"] for item in goods)

    total_weight = sum(_number(item["weight"]) for item in goods)

    created = Counter(str(item["created_at"])[:7] for item in goods)
    monthly = _monthly_rows(created, months)

    return {
        "total": total,
        "active": active,
        "archived": archived,
        "active_percent": round(active * 100 / total, 1) if total else 0,
        "archived_percent": round(archived * 100 / total, 1) if total else 0,
        "category_count": len(categories),
        "avg_weight": round(total_weight / total, 2) if total else 0,
        "categories": _share(categories, limit=8),
        "units": _share(units),
        "monthly": monthly,
        "monthly_total": sum(row["count"] for row in monthly),
    }


@app.get("/analytics")
def analytics_page():
    settings = current_settings()
    goods = get_all_goods("", "all")

    return render_template(
        "analytics.html",
        stats=build_analytics(goods, settings["chart_months"]),
    )


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

def _settings_form(settings):
    return {
        "app_name": settings["app_name"],
        "theme": settings["theme"],
        "default_status_filter": settings["default_status_filter"],
        "chart_months": str(settings["chart_months"]),
    }


@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    form = _settings_form(current_settings())

    if request.method == "POST":
        # Keep whatever the user typed, so the form can be corrected.
        form = {
            "app_name": request.form.get("app_name", "").strip(),
            "theme": request.form.get("theme", ""),
            "default_status_filter":
                request.form.get("default_status_filter", ""),
            "chart_months": request.form.get("chart_months", ""),
        }

        try:
            save_settings(form)
        except ValueError as error:
            flash(str(error), "error")
        else:
            flash("Settings saved.", "success")
            return redirect(url_for("settings_page"))

    return render_template(
        "settings.html",
        form=form,
        themes=THEMES,
        status_filters=STATUS_FILTERS,
        month_choices=CHART_MONTH_CHOICES,
    )


@app.post("/settings/backup")
def backup_page():
    path = backup_database()
    flash(f"Backup saved: {path.name}", "success")
    return redirect(url_for("settings_page"))


# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------

@app.route("/categories", methods=["GET", "POST"])
def categories_page():
    category_name = ""

    if request.method == "POST":
        category_name = request.form.get("name", "")

        try:
            add_category(category_name)
        except ValueError as error:
            flash(str(error), "error")
        else:
            flash("Category added successfully.", "success")
            # Redirect so refreshing does not submit the form again.
            return redirect(url_for("categories_page"))

    return render_template(
        "categories.html",
        categories=get_all_categories(),
        category_name=category_name,
    )


@app.post("/categories/<int:category_id>/rename")
def rename_category_page(category_id):
    try:
        changed = rename_category(category_id, request.form.get("name", ""))
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash(
            "Category renamed successfully."
            if changed else "The category name is unchanged.",
            "success",
        )

    return redirect(url_for("categories_page"))


@app.post("/categories/<int:category_id>/delete")
def delete_category_page(category_id):
    try:
        delete_category(category_id)
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash("Category deleted successfully.", "success")

    return redirect(url_for("categories_page"))


# --------------------------------------------------------------------------
# Goods: list, create, edit
# --------------------------------------------------------------------------

def _render_goods_page(form_data, search, status_filter, editing_id=None):
    return render_template(
        "goods.html",
        goods=get_all_goods(search, status_filter),
        categories=get_all_categories(),
        units=ALLOWED_UNITS,
        form_data=form_data,
        search=search,
        status_filter=status_filter,
        editing_id=editing_id,
    )


@app.route("/goods", methods=["GET", "POST"])
def goods_page():
    form_data = blank_goods_form()

    if request.method == "POST":
        form_data = read_goods_form()

        try:
            add_goods(**goods_arguments(form_data))
        except ValueError as error:
            flash(str(error), "error")
        else:
            flash("Goods registered successfully.", "success")
            return redirect(url_for("goods_page"))

    # Shown for GET requests and after validation errors.
    return _render_goods_page(
        form_data, read_search(), read_status_filter(request.args)
    )


@app.route("/goods/<int:goods_id>/edit", methods=["GET", "POST"])
def edit_goods_page(goods_id):
    item = get_goods_or_404(goods_id)
    form_data = goods_form_from_record(item)

    if request.method == "POST":
        form_data = read_goods_form()

        try:
            changed = update_goods(
                goods_id=goods_id, **goods_arguments(form_data)
            )
        except ValueError as error:
            flash(str(error), "error")
        else:
            flash(
                "Goods updated successfully."
                if changed else "No changes were made.",
                "success",
            )
            return redirect(url_for("goods_page"))

    return _render_goods_page(form_data, "", "all", editing_id=goods_id)


STATUS_MESSAGES = {
    "archived": "Goods archived successfully.",
    "active": "Goods restored successfully.",
}


@app.post("/goods/<int:goods_id>/status")
def change_goods_status(goods_id):
    get_goods_or_404(goods_id)
    new_status = request.form.get("status", "")

    try:
        changed = set_goods_status(goods_id, new_status)
    except ValueError as error:
        flash(str(error), "error")
    else:
        if changed:
            flash(STATUS_MESSAGES.get(new_status, "Status updated."), "success")
        else:
            flash("The goods already have this status.", "success")

    return redirect(
        url_for(
            "goods_page",
            q=request.form.get("q", "").strip(),
            # Send the user back to the list they were looking at; an odd
            # value must never break the redirect.
            status=read_status_filter(
                request.form, key="status_filter", default="all",
                strict=False,
            ),
        )
    )


# --------------------------------------------------------------------------
# Goods: history, deletion
# --------------------------------------------------------------------------

@app.get("/goods/<int:goods_id>/history")
def goods_history_page(goods_id):
    item = get_goods_by_id(goods_id)
    history = get_goods_history(goods_id)
    is_deleted = item is None

    if is_deleted:
        if not history:
            abort(404, description="Goods history not found.")

        latest = history[0]
        snapshot = latest["after"] or latest["before"]

        item = {
            "id": goods_id,
            "code": snapshot.get("code", latest["entity_label"]),
            "name": snapshot.get("name", "Deleted goods"),
        }

    for entry in history:
        entry["changes"] = compute_changes(entry["before"], entry["after"])

    return render_template(
        "goods_history.html",
        item=item,
        history=history,
        is_deleted=is_deleted,
    )


@app.route("/goods/<int:goods_id>/delete", methods=["GET", "POST"])
def delete_goods_page(goods_id):
    item = get_goods_or_404(goods_id)

    if item["status"] != "archived":
        flash("Archive this goods record before deleting it.", "error")
        return redirect(url_for("goods_page"))

    if request.method == "POST":
        if request.form.get("confirmation") != "delete":
            flash("Please confirm permanent deletion.", "error")
        else:
            try:
                delete_goods(goods_id)
            except ValueError as error:
                flash(str(error), "error")
            else:
                return redirect(
                    url_for("goods_history_page", goods_id=goods_id)
                )

    return render_template("goods_delete.html", item=item)


@app.get("/goods/deleted")
def deleted_goods_page():
    return render_template(
        "deleted_goods.html", deleted_goods=get_deleted_goods()
    )


# --------------------------------------------------------------------------
# Goods: CSV export / import
# --------------------------------------------------------------------------

EXPORT_HEADER = [
    "ID", "Goods code", "Goods name", "Category", "Unit",
    "Weight per unit (kg)", "Description", "Status",
    "Created at (UTC)", "Updated at (UTC)",
]

# Leading characters that spreadsheet programs treat as a formula.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def spreadsheet_text(value):
    """Keep formula-like user text as text in spreadsheets (CSV injection)."""
    text = str(value)

    if text.lstrip().startswith(FORMULA_PREFIXES):
        return "'" + text

    return text


def _export_row(item):
    return [
        item["id"],
        spreadsheet_text(item["code"]),
        spreadsheet_text(item["name"]),
        spreadsheet_text(item["category_name"]),
        spreadsheet_text(item["unit"]),
        item["weight"],
        spreadsheet_text(item["description"]),
        item["status"],
        item["created_at"],
        item["updated_at"],
    ]


def _csv_download(data, filename):
    return Response(
        data,
        content_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@app.get("/goods/export")
def export_goods():
    goods = get_all_goods(read_search(), read_status_filter(request.args))

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(EXPORT_HEADER)

    for item in goods:
        writer.writerow(_export_row(item))

    # UTF-8 BOM helps Excel recognise multilingual text.
    csv_data = output.getvalue().encode("utf-8-sig")
    output.close()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return _csv_download(csv_data, f"goodshub_goods_{stamp}.csv")


@app.get("/goods/import/template")
def import_template():
    return _csv_download(sample_csv(), "goods_import_template.csv")


@app.route("/goods/import", methods=["GET", "POST"])
def import_goods_page():
    result = None

    if request.method == "POST":
        try:
            result = import_goods_csv(request.files.get("csv_file"))
        except ValueError as error:
            flash(str(error), "error")

    return render_template("goods_import.html", result=result)


# --------------------------------------------------------------------------
# Goods: photos
# --------------------------------------------------------------------------

@app.get("/goods/photos/<filename>")
def goods_photo_file(filename):
    # Only accept filenames generated by our upload code.
    if not is_valid_photo_filename(filename):
        abort(404)

    return send_from_directory(PHOTO_DIR, filename)


@app.get("/goods/photos/thumbs/<filename>")
def goods_thumb_file(filename):
    if not is_valid_photo_filename(filename):
        abort(404)

    return send_from_directory(THUMB_DIR, filename)


@app.route("/goods/<int:goods_id>/photo", methods=["GET", "POST"])
def goods_photo_page(goods_id):
    item = get_goods_or_404(goods_id)

    if request.method == "POST":
        filename = None

        try:
            filename = save_goods_photo(request.files.get("photo"))
            old_filename = replace_goods_photo(goods_id, filename)
        except ValueError as error:
            # The upload never reached the database: remove the new file
            # (if any) and show the problem to the user.
            if filename:
                delete_goods_photo(filename)

            flash(str(error), "error")
        except Exception:
            # Unexpected problem: keep the files consistent, then re-raise
            # so the error page and the log report it.
            if filename:
                delete_goods_photo(filename)

            raise
        else:
            # The new photo is saved; the replaced one is no longer used.
            if old_filename:
                delete_goods_photo(old_filename)

            flash("Goods photo saved successfully.", "success")
            return redirect(url_for("goods_photo_page", goods_id=goods_id))

    return render_template("goods_photo.html", item=item)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
