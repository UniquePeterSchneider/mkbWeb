import os
import sqlite3
from functools import wraps
from pathlib import Path

import bleach
import markdown
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "mkb.db"))
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
EDITOR_PASSWORD = "editor"

if not EDITOR_PASSWORD:
    raise RuntimeError("Set EDITOR_PASSWORD environment variable.")

EDITOR_PASSWORD_HASH = generate_password_hash(
    EDITOR_PASSWORD,
    method="pbkdf2:sha256",
)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
)


def get_db():
    if "db" not in g:
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            text TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.commit()


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("role") not in {"read", "write"}:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped_view


def write_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("role") != "write":
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


ALLOWED_MARKDOWN_TAGS = {
    "p", "br", "hr", "strong", "em", "del", "blockquote", "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6", "code", "pre", "a",
}
ALLOWED_MARKDOWN_ATTRIBUTES = {
    "a": ["href", "title", "rel", "target"],
}
ALLOWED_MARKDOWN_PROTOCOLS = {"http", "https", "mailto"}


def render_markdown(text):
    """Convert Markdown to sanitized HTML suitable for displaying a recipe."""
    rendered = markdown.markdown(
        text or "",
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )
    safe_html = bleach.clean(
        rendered,
        tags=ALLOWED_MARKDOWN_TAGS,
        attributes=ALLOWED_MARKDOWN_ATTRIBUTES,
        protocols=ALLOWED_MARKDOWN_PROTOCOLS,
        strip=True,
    )
    return Markup(safe_html)


app.jinja_env.filters["markdown"] = render_markdown


@app.context_processor
def inject_user():
    role = session.get("role")
    return {
        "current_role": role,
        "is_editor": role == "write",
        "is_read_only": role == "read",
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("role") in {"read", "write"}:
        return redirect(url_for("recipes"))

    if request.method == "POST":
        password = request.form.get("password", "")

        if check_password_hash(EDITOR_PASSWORD_HASH, password):
            session.clear()
            session["role"] = "write"
            next_url = request.form.get("next") or url_for("recipes")
            return redirect(next_url)

        flash("Incorrect editor password.", "danger")

    return render_template("login.html")


@app.post("/login/read-only")
def enter_read_only():
    session.clear()
    session["role"] = "read"
    return redirect(request.form.get("next") or url_for("recipes"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return redirect(url_for("recipes"))


@app.route("/recipes")
@login_required
def recipes():
    rows = get_db().execute(
        "SELECT id, name, text FROM entries ORDER BY name COLLATE NOCASE"
    ).fetchall()
    recipes_data = [
        {
            "id": row["id"],
            "name": row["name"],
            "text": row["text"],
            "text_html": render_markdown(row["text"]),
        }
        for row in rows
    ]

    selected_id = request.args.get("selected", type=int)
    edit_mode = request.args.get("edit", "0") == "1" and selected_id is not None
    return render_template(
        "recipes.html",
        recipes=recipes_data,
        selected_id=selected_id,
        edit_mode=edit_mode,
    )


@app.route("/recipes/new", methods=["POST"])
@write_required
def recipe_new():
    name = request.form.get("name", "").strip()
    if not name:
        flash("A recipe name is required.", "warning")
        return redirect(url_for("recipes"))

    db = get_db()
    cursor = db.execute(
        "INSERT INTO entries (name, text) VALUES (?, ?)",
        (name, ""),
    )
    db.commit()

    return redirect(url_for("recipes", selected=cursor.lastrowid, edit=1))


@app.route("/recipes/<int:recipe_id>/edit", methods=["POST"])
@write_required
def recipe_edit(recipe_id):
    name = request.form.get("name", "").strip()
    text = request.form.get("text", "")

    if not name:
        flash("A recipe name is required.", "warning")
        return redirect(url_for("recipes", selected=recipe_id, edit=1))

    db = get_db()
    result = db.execute(
        "UPDATE entries SET name = ?, text = ? WHERE id = ?",
        (name, text, recipe_id),
    )
    db.commit()

    if result.rowcount == 0:
        abort(404)

    flash("Recipe saved.", "success")
    return redirect(url_for("recipes", selected=recipe_id))


@app.route("/recipes/<int:recipe_id>/delete", methods=["POST"])
@write_required
def recipe_delete(recipe_id):
    db = get_db()
    result = db.execute("DELETE FROM entries WHERE id = ?", (recipe_id,))
    db.commit()

    if result.rowcount == 0:
        abort(404)

    flash("Recipe deleted.", "success")
    return redirect(url_for("recipes"))


@app.errorhandler(403)
def forbidden(error):
    return (
        render_template(
            "error.html", code=403, message="You are not allowed to do that."
        ),
        403,
    )


@app.errorhandler(404)
def not_found(error):
    return (
        render_template(
            "error.html", code=404, message="The requested page was not found."
        ),
        404,
    )


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=True)
