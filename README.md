# Recipe Manager

Small Flask + SQLite recipe web application.

## Features

- One SQLite table: `recipe`
- Two fixed access modes:
  - **Editor**: protected by an editor password; can search, create, edit, and delete recipes
  - **Read Only**: no password; can search and view recipes
- Live substring search across both `recipe.name` and `recipe.description`
- Markdown stored in `recipe.description`
- Live Markdown preview while editing
- Sanitized Markdown HTML when displayed
- Bootstrap 5 loaded from jsDelivr
- SQLite database path can be placed on persistent hosted storage via `DATABASE_PATH`

## Run locally

Set an editor password first:

```bash
export EDITOR_PASSWORD='your-editor-password'
export SECRET_KEY='replace-with-a-random-secret'
```

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start the application:

```bash
python app.py
```

Then open `http://127.0.0.1:5000`.

By default the SQLite database is `recipes.db` next to `app.py`. For a hosted service with persistent storage, set for example:

```text
DATABASE_PATH=/var/data/recipes.db
```

## Login behavior

The login screen provides:

- **Editor password + Login**: starts an editor session.
- **Enter Read Only**: starts a read-only session immediately, without a password.

There is no reader password and no user table.

## Markdown

Recipe descriptions are stored as Markdown text. The edit view has a Markdown input and a live preview. Displayed Markdown is sanitized before being inserted into the page.
