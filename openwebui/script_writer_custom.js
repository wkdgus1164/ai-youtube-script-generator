(() => {
  const CONFIG = window.__SCRIPT_WRITER_UI_CONFIG__ || {};
  const SCRIPT_WRITER_MODEL_ID = "youtube-script-writer";
  const PROMPT_BUTTON_ID = "script-writer-prompt-editor-button";
  const PROMPT_ANCHOR_ID = "script-writer-prompt-editor-anchor";
  const PROMPT_OVERLAY_ID = "script-writer-prompt-editor-overlay";
  const PROMPT_IFRAME_ID = "script-writer-prompt-editor-frame";
  const INPUT_ID = "chat-input";
  const CHAT_COPY_BUTTON_ID = "chat-copy-button";
  const CHAT_MENU_IDS_TO_HIDE = ["chat-share-button", "chat-artifacts-button"];
  const MESSAGE_ACTIONS_TO_HIDE = new Set([
    "download",
    "edit",
    "delete",
    "move",
    "archive",
    "share",
    "plain text (.txt)",
    "pdf document (.pdf)",
    "export chat (.json)",
    "artifacts",
  ]);

  function normalizeLabel(value) {
    return (value || "").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function getNodeLabel(node) {
    return normalizeLabel(
      node?.getAttribute?.("aria-label")
        || node?.getAttribute?.("title")
        || node?.textContent
        || ""
    );
  }

  function getBackendBaseUrl() {
    if (CONFIG.backendBaseUrl) {
      return CONFIG.backendBaseUrl.replace(/\/+$/, "");
    }

    const { protocol, hostname } = window.location;
    if (hostname === "localhost" || hostname === "127.0.0.1") {
      return `${protocol}//${hostname}:8000`;
    }

    return `${protocol}//${window.location.host.replace(/:\d+$/, ":8000")}`;
  }

  function promptEditorUrl() {
    return `${getBackendBaseUrl()}/script-writer/prompts`;
  }

  function ensureStyles() {
    if (document.getElementById("script-writer-custom-style")) {
      return;
    }

    const style = document.createElement("style");
    style.id = "script-writer-custom-style";
    style.textContent = `
      [data-codex-hidden="true"] {
        display: none !important;
      }

      #${PROMPT_ANCHOR_ID} {
        display: flex;
        justify-content: flex-start;
        padding: 0 0 10px;
      }

      #${PROMPT_BUTTON_ID} {
        appearance: none;
        border: 1px solid rgba(56, 189, 248, 0.24);
        border-radius: 999px;
        background: rgba(15, 23, 42, 0.82);
        color: #e2e8f0;
        font-size: 13px;
        font-weight: 600;
        padding: 8px 14px;
        cursor: pointer;
      }

      #${PROMPT_BUTTON_ID}:hover {
        background: rgba(30, 41, 59, 0.92);
      }

      #${PROMPT_OVERLAY_ID} {
        position: fixed;
        inset: 0;
        display: none;
        align-items: center;
        justify-content: center;
        background: rgba(2, 6, 23, 0.7);
        backdrop-filter: blur(10px);
        z-index: 9999;
        padding: 20px;
      }

      #${PROMPT_OVERLAY_ID}[data-open="true"] {
        display: flex;
      }

      #${PROMPT_OVERLAY_ID} .script-writer-editor-shell {
        width: min(1400px, 100%);
        height: min(900px, calc(100vh - 40px));
        display: flex;
        flex-direction: column;
        border-radius: 28px;
        overflow: hidden;
        background: rgba(15, 23, 42, 0.96);
        border: 1px solid rgba(148, 163, 184, 0.16);
        box-shadow: 0 30px 80px rgba(2, 6, 23, 0.45);
      }

      #${PROMPT_OVERLAY_ID} .script-writer-editor-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        padding: 14px 18px;
        color: #e2e8f0;
        background: rgba(2, 6, 23, 0.76);
        border-bottom: 1px solid rgba(148, 163, 184, 0.12);
      }

      #${PROMPT_OVERLAY_ID} .script-writer-editor-title {
        font-size: 14px;
        font-weight: 700;
      }

      #${PROMPT_OVERLAY_ID} .script-writer-editor-close {
        appearance: none;
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 999px;
        background: transparent;
        color: #cbd5e1;
        padding: 8px 12px;
        cursor: pointer;
      }

      #${PROMPT_IFRAME_ID} {
        flex: 1;
        width: 100%;
        border: 0;
        background: #020617;
      }
    `;
    document.head.appendChild(style);
  }

  function hideNode(node) {
    if (!node || node.dataset.codexHidden === "true") {
      return;
    }
    node.dataset.codexHidden = "true";
  }

  function ensureOverlay() {
    let overlay = document.getElementById(PROMPT_OVERLAY_ID);
    if (overlay) {
      return overlay;
    }

    overlay = document.createElement("div");
    overlay.id = PROMPT_OVERLAY_ID;
    overlay.innerHTML = `
      <div class="script-writer-editor-shell" role="dialog" aria-modal="true" aria-label="Prompt Editor">
        <div class="script-writer-editor-bar">
          <div class="script-writer-editor-title">YouTube Script Writer Prompt Editor</div>
          <button type="button" class="script-writer-editor-close">Close</button>
        </div>
        <iframe id="${PROMPT_IFRAME_ID}" title="Prompt Editor"></iframe>
      </div>
    `;

    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) {
        closeOverlay();
      }
    });

    overlay
      .querySelector(".script-writer-editor-close")
      ?.addEventListener("click", closeOverlay);

    document.body.appendChild(overlay);
    return overlay;
  }

  function openOverlay() {
    const overlay = ensureOverlay();
    const frame = overlay.querySelector(`#${PROMPT_IFRAME_ID}`);
    if (frame && frame.src !== promptEditorUrl()) {
      frame.src = promptEditorUrl();
    }
    overlay.dataset.open = "true";
    document.body.style.overflow = "hidden";
  }

  function closeOverlay() {
    const overlay = document.getElementById(PROMPT_OVERLAY_ID);
    if (!overlay) {
      return;
    }
    overlay.dataset.open = "false";
    document.body.style.overflow = "";
  }

  function ensurePromptButton() {
    const input = document.getElementById(INPUT_ID);
    const form = input?.closest("form");
    if (!input || !form) {
      return;
    }

    let anchor = document.getElementById(PROMPT_ANCHOR_ID);
    if (!anchor || !form.contains(anchor)) {
      anchor = document.createElement("div");
      anchor.id = PROMPT_ANCHOR_ID;
      form.prepend(anchor);
    }

    let button = document.getElementById(PROMPT_BUTTON_ID);
    if (!button) {
      button = document.createElement("button");
      button.id = PROMPT_BUTTON_ID;
      button.type = "button";
      button.textContent = "Prompt Editor";
      button.addEventListener("click", openOverlay);
      anchor.appendChild(button);
    } else if (!anchor.contains(button)) {
      anchor.appendChild(button);
    }
  }

  function shouldKeepComposerButton(button) {
    if (!button) {
      return true;
    }

    if (button.id === PROMPT_BUTTON_ID) {
      return true;
    }

    const buttonType = button.getAttribute("type");
    if (buttonType === "submit") {
      return true;
    }

    const label = getNodeLabel(button);
    return label === "send" || label === "send message" || label === "stop" || label === "stop response";
  }

  function pruneComposerButtons() {
    const input = document.getElementById(INPUT_ID);
    const form = input?.closest("form");
    if (!input || !form) {
      return;
    }

    for (const button of form.querySelectorAll("button")) {
      if (!shouldKeepComposerButton(button)) {
        hideNode(button);
      }
    }
  }

  function pruneChatActionMenus(root = document) {
    for (const id of CHAT_MENU_IDS_TO_HIDE) {
      hideNode(root.getElementById ? root.getElementById(id) : document.getElementById(id));
    }

    const copyButton = root.getElementById
      ? root.getElementById(CHAT_COPY_BUTTON_ID)
      : document.getElementById(CHAT_COPY_BUTTON_ID);

    if (!copyButton) {
      return;
    }

    const menu = copyButton.parentElement;
    if (!menu) {
      return;
    }

    for (const button of menu.querySelectorAll("button")) {
      if (button.id !== CHAT_COPY_BUTTON_ID) {
        hideNode(button);
      }
    }
  }

  function pruneMessageActionButtons(root = document) {
    for (const button of root.querySelectorAll("button,[role='button']")) {
      const label = getNodeLabel(button);
      if (MESSAGE_ACTIONS_TO_HIDE.has(label)) {
        hideNode(button.closest("button,[role='button']") || button);
      }
    }
  }

  function keepModelMenuEntry(node) {
    return getNodeLabel(node).includes(SCRIPT_WRITER_MODEL_ID);
  }

  function pruneModelPicker(root = document) {
    for (const button of root.querySelectorAll("button,[role='button'],[role='option'],option")) {
      const label = getNodeLabel(button);
      const isMenuEntry = button.getAttribute("role") === "option" || Boolean(button.closest("[role='listbox']"));

      if (
        label === "add model"
        || label === "set as default"
        || label === "기본값으로 설정"
        || label.includes("arena model")
      ) {
        hideNode(button.closest("button,[role='button'],[role='option'],option") || button);
        continue;
      }

      if (isMenuEntry && label.startsWith("select ") && !keepModelMenuEntry(button)) {
        hideNode(button.closest("[role='option'],button,option") || button);
      }
    }
  }

  function scan(root = document) {
    ensurePromptButton();
    pruneComposerButtons();
    pruneChatActionMenus(root);
    pruneMessageActionButtons(root);
    pruneModelPicker(root);
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeOverlay();
    }
  });

  function boot() {
    ensureStyles();
    ensureOverlay();
    scan(document);

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node instanceof HTMLElement) {
            scan(node);
          }
        }
      }
      scan(document);
    });

    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
