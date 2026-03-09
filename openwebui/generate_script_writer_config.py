from __future__ import annotations

import json
import os
from pathlib import Path


OUTPUT_PATH = Path("/app/build/static/script-writer-ui-config.js")


def main() -> None:
    config = {
        "backendBaseUrl": os.environ.get(
            "SCRIPT_WRITER_BACKEND_PUBLIC_URL",
            "http://localhost:8000",
        ).rstrip("/"),
    }
    OUTPUT_PATH.write_text(
        "window.__SCRIPT_WRITER_UI_CONFIG__ = "
        + json.dumps(config, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
