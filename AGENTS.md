# Repository Guidelines

## Project Structure & Module Organization

This repository is a Django website for Iron Quill Games Studio. The project configuration lives in `website/`, including settings, root URLs, and WSGI/ASGI entry points. The `home/` app contains the public page implementation: edit `home/views.py`, `home/templates/home/index.html`, and `home/static/home/` for site changes. Tests currently live in `home/tests.py`.

`WebsiteMaterials/` holds curated branding, artwork, and marketing copy. Treat it as source material rather than served static content. `Fonts/` contains original font files. The helper in `tools/upload_website_materials_to_cloudinary.py` uploads supported promotional images to Cloudinary.

## Build, Test, and Development Commands

Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in local values. Useful commands:

```powershell
python manage.py migrate
python manage.py runserver
python manage.py test
python manage.py collectstatic --noinput
venv\Scripts\python.exe tools\upload_website_materials_to_cloudinary.py
```

`runserver` starts the local site, `test` runs Django tests, and `collectstatic` validates the production static-file pipeline. The upload helper requires valid Cloudinary credentials and performs remote writes.

## Coding Style & Naming Conventions

Use four-space indentation for Python and follow standard Django conventions: `snake_case` for functions and variables, `PascalCase` for classes, and lowercase app/module names. Keep templates under `home/templates/home/` and app-specific assets under `home/static/home/`. No formatter or linter is configured, so keep changes small and match surrounding style.

## Testing Guidelines

Add Django `TestCase` methods named `test_<behavior>` in `home/tests.py`. Run `python manage.py test` before opening a pull request. When changing templates or CSS, verify the homepage manually at common desktop and mobile widths.

## Commit & Pull Request Guidelines

Recent commits use short imperative summaries, such as `Adjust image size` and `Add favicon`. Keep each commit focused. Pull requests should explain the user-visible change, note test commands run, link relevant issues, and include before/after screenshots for visual updates. Do not commit `.env`, database files, or generated `staticfiles/`.
