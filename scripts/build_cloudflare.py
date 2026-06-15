from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    site_url = os.environ.get("GRADWINDOW_SITE_URL")
    if not site_url:
        raise SystemExit(
            "GRADWINDOW_SITE_URL is required, for example "
            "https://gradwindow.pages.dev"
        )

    subprocess.run(
        [sys.executable, "-m", "gradwindow.cli", "build-site"],
        check=True,
    )


if __name__ == "__main__":
    main()
