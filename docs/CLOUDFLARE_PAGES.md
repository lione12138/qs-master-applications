# Cloudflare Pages

Use these settings when connecting the GitHub repository to Cloudflare Pages:

- Production branch: `main`
- Build command: `python -m pip install . && python scripts/build_cloudflare.py`
- Build output directory: `site`
- Root directory: leave empty

Add this environment variable:

- `GRADWINDOW_SITE_URL=https://gradwindow.pages.dev`

Use Python 3.12 or newer. The build reads the reviewed JSON data already
committed to the repository. It does not run the daily page monitors or modify
admissions records.
