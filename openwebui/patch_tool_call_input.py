from __future__ import annotations

from pathlib import Path


CHUNKS_DIR = Path("/app/build/_app/immutable/chunks")
INDEX_HTML_PATH = Path("/app/build/index.html")
TOOL_CALL_MARKER = "tool-call-args"
ORIGINAL_BRANCH = "w(ye,ne=>{e(s)?ne(Ve):ne(Ce,!1)})"
PATCHED_BRANCH = "w(ye,ne=>{ne(Ce)})"
CUSTOM_SCRIPT_MARKER = "/static/script-writer-custom.js"
CUSTOM_SCRIPT_TAGS = """
        <script src="/static/script-writer-ui-config.js" defer crossorigin="use-credentials"></script>
        <script src="/static/script-writer-custom.js" defer crossorigin="use-credentials"></script>
""".rstrip()


def patch_bundle() -> Path:
    for bundle_path in CHUNKS_DIR.glob("*.js"):
        bundle = bundle_path.read_text()
        if TOOL_CALL_MARKER not in bundle:
            continue
        if PATCHED_BRANCH in bundle:
            return bundle_path
        if ORIGINAL_BRANCH not in bundle:
            continue
        bundle_path.write_text(bundle.replace(ORIGINAL_BRANCH, PATCHED_BRANCH, 1))
        return bundle_path
    raise RuntimeError("Unable to find OpenWebUI ToolCallDisplay bundle to patch")


def patch_index_html() -> None:
    html = INDEX_HTML_PATH.read_text()
    if CUSTOM_SCRIPT_MARKER in html:
        return
    if "</head>" not in html:
        raise RuntimeError("Unable to inject custom scripts into OpenWebUI index.html")
    INDEX_HTML_PATH.write_text(html.replace("</head>", f"{CUSTOM_SCRIPT_TAGS}\n\t</head>", 1))


def main() -> None:
    patched_file = patch_bundle()
    patch_index_html()
    print(f"patched {patched_file}")


if __name__ == "__main__":
    main()
