"""Standalone HTML prompt editor for the script-writer workflow."""
from __future__ import annotations


def render_prompt_editor_html() -> str:
    """Return the prompt editor page used from the OpenWebUI overlay."""
    return """<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>YouTube Script Writer Prompt Editor</title>
    <style>
      :root {
        color-scheme: dark;
        --bg: #0b1020;
        --panel: rgba(15, 23, 42, 0.88);
        --panel-border: rgba(148, 163, 184, 0.22);
        --text: #e5eefb;
        --muted: #94a3b8;
        --accent: #38bdf8;
        --accent-2: #0f172a;
        --danger: #f97316;
        --success: #22c55e;
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background:
          radial-gradient(circle at top, rgba(56, 189, 248, 0.15), transparent 30%),
          linear-gradient(180deg, #020617 0%, #0f172a 100%);
        color: var(--text);
      }

      .shell {
        width: min(1280px, calc(100vw - 32px));
        margin: 0 auto;
        padding: 24px 0 40px;
      }

      .topbar {
        position: sticky;
        top: 0;
        z-index: 20;
        display: flex;
        gap: 12px;
        align-items: center;
        justify-content: space-between;
        padding: 16px 0 20px;
        backdrop-filter: blur(16px);
      }

      .title {
        font-size: 24px;
        font-weight: 700;
        letter-spacing: -0.02em;
      }

      .subtitle {
        margin-top: 6px;
        color: var(--muted);
        font-size: 14px;
      }

      .actions {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        justify-content: flex-end;
      }

      button {
        border: 1px solid transparent;
        border-radius: 999px;
        padding: 10px 16px;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        transition: transform 120ms ease, opacity 120ms ease, background 120ms ease;
      }

      button:hover {
        transform: translateY(-1px);
      }

      button:disabled {
        cursor: wait;
        opacity: 0.7;
        transform: none;
      }

      .primary {
        background: linear-gradient(135deg, #38bdf8 0%, #2563eb 100%);
        color: white;
      }

      .secondary {
        background: rgba(15, 23, 42, 0.75);
        color: var(--text);
        border-color: var(--panel-border);
      }

      .ghost {
        background: transparent;
        color: var(--muted);
        border-color: rgba(148, 163, 184, 0.16);
      }

      .status {
        min-height: 24px;
        margin-bottom: 16px;
        color: var(--muted);
        font-size: 13px;
      }

      .status[data-tone="success"] {
        color: var(--success);
      }

      .status[data-tone="error"] {
        color: var(--danger);
      }

      .grid {
        display: grid;
        gap: 16px;
      }

      .card {
        border: 1px solid var(--panel-border);
        background: var(--panel);
        border-radius: 24px;
        padding: 20px;
        box-shadow: 0 18px 50px rgba(2, 6, 23, 0.28);
      }

      .card-head {
        display: flex;
        gap: 16px;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 14px;
      }

      .card-title {
        font-size: 18px;
        font-weight: 700;
        margin-bottom: 4px;
      }

      .card-key {
        color: var(--muted);
        font-size: 12px;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }

      .meta {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        justify-content: flex-end;
      }

      .pill {
        border-radius: 999px;
        padding: 6px 10px;
        font-size: 12px;
        color: var(--muted);
        background: rgba(30, 41, 59, 0.68);
        border: 1px solid rgba(148, 163, 184, 0.14);
      }

      textarea {
        width: 100%;
        min-height: 320px;
        border: 1px solid rgba(148, 163, 184, 0.22);
        border-radius: 18px;
        background: rgba(2, 6, 23, 0.72);
        color: var(--text);
        padding: 16px;
        resize: vertical;
        font: 13px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace;
      }

      .card-footer {
        margin-top: 12px;
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: center;
      }

      .helper {
        color: var(--muted);
        font-size: 12px;
      }

      @media (max-width: 960px) {
        .shell {
          width: min(100vw, calc(100vw - 20px));
          padding-top: 16px;
        }

        .topbar,
        .card-head,
        .card-footer {
          flex-direction: column;
          align-items: stretch;
        }

        .actions,
        .meta {
          justify-content: flex-start;
        }
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="topbar">
        <div>
          <div class="title">YouTube Script Writer Prompt Editor</div>
          <div class="subtitle">저장하면 다음 요청부터 바로 적용됩니다. 현재 편집 대상은 LLM 프롬프트 노드 6개입니다.</div>
        </div>
        <div class="actions">
          <button id="reset-all" class="ghost" type="button">기본값으로 되돌리기</button>
          <button id="save-all" class="primary" type="button">저장</button>
        </div>
      </div>

      <div id="status" class="status" data-tone="neutral">프롬프트를 불러오는 중입니다...</div>
      <div id="prompt-grid" class="grid"></div>
    </div>

    <script>
      const statusNode = document.getElementById("status");
      const gridNode = document.getElementById("prompt-grid");
      const saveButton = document.getElementById("save-all");
      const resetAllButton = document.getElementById("reset-all");

      let prompts = [];

      function setStatus(message, tone = "neutral") {
        statusNode.textContent = message;
        statusNode.dataset.tone = tone;
      }

      function textareaId(key) {
        return `prompt-${key}`;
      }

      function render() {
        gridNode.innerHTML = "";

        prompts.forEach((prompt) => {
          const card = document.createElement("section");
          card.className = "card";

          const title = document.createElement("div");
          title.className = "card-title";
          title.textContent = prompt.title;

          const key = document.createElement("div");
          key.className = "card-key";
          key.textContent = prompt.key;

          const titleWrap = document.createElement("div");
          titleWrap.append(title, key);

          const meta = document.createElement("div");
          meta.className = "meta";
          meta.innerHTML = `
            <div class="pill">max_tokens ${prompt.max_tokens}</div>
            <div class="pill">temperature ${prompt.temperature}</div>
          `;

          const head = document.createElement("div");
          head.className = "card-head";
          head.append(titleWrap, meta);

          const textarea = document.createElement("textarea");
          textarea.id = textareaId(prompt.key);
          textarea.value = prompt.body;
          textarea.spellcheck = false;

          const resetButton = document.createElement("button");
          resetButton.type = "button";
          resetButton.className = "secondary";
          resetButton.textContent = "이 노드만 기본값 복원";
          resetButton.addEventListener("click", () => {
            textarea.value = prompt.default_body;
            setStatus(`${prompt.title} 기본값을 로드했습니다. 저장하면 적용됩니다.`);
          });

          const helper = document.createElement("div");
          helper.className = "helper";
          helper.textContent = "중괄호 변수는 그대로 유지하세요. 예: {transcript}, {outline}, {draft_text}";

          const footer = document.createElement("div");
          footer.className = "card-footer";
          footer.append(resetButton, helper);

          card.append(head, textarea, footer);
          gridNode.append(card);
        });
      }

      async function loadPrompts() {
        const response = await fetch("/api/script-writer/prompts");
        if (!response.ok) {
          throw new Error(`프롬프트 로딩 실패: ${response.status}`);
        }
        const payload = await response.json();
        prompts = payload.prompts;
        render();
        setStatus("프롬프트를 불러왔습니다.");
      }

      function collectPromptBodies() {
        return Object.fromEntries(
          prompts.map((prompt) => [
            prompt.key,
            document.getElementById(textareaId(prompt.key)).value.trim(),
          ])
        );
      }

      async function savePrompts() {
        saveButton.disabled = true;
        resetAllButton.disabled = true;
        setStatus("저장 중입니다...");

        try {
          const response = await fetch("/api/script-writer/prompts", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompts: collectPromptBodies() }),
          });

          if (!response.ok) {
            const detail = await response.text();
            throw new Error(detail || `저장 실패: ${response.status}`);
          }

          const payload = await response.json();
          prompts = payload.prompts;
          render();
          setStatus("저장되었습니다. 다음 요청부터 새 프롬프트가 적용됩니다.", "success");
        } catch (error) {
          setStatus(error instanceof Error ? error.message : "저장 중 오류가 발생했습니다.", "error");
        } finally {
          saveButton.disabled = false;
          resetAllButton.disabled = false;
        }
      }

      async function resetPrompts() {
        if (!window.confirm("모든 프롬프트를 기본값으로 되돌릴까요?")) {
          return;
        }

        saveButton.disabled = true;
        resetAllButton.disabled = true;
        setStatus("기본값으로 복원 중입니다...");

        try {
          const response = await fetch("/api/script-writer/prompts/reset", {
            method: "POST",
          });
          if (!response.ok) {
            const detail = await response.text();
            throw new Error(detail || `복원 실패: ${response.status}`);
          }

          const payload = await response.json();
          prompts = payload.prompts;
          render();
          setStatus("기본 프롬프트로 복원했습니다.", "success");
        } catch (error) {
          setStatus(error instanceof Error ? error.message : "복원 중 오류가 발생했습니다.", "error");
        } finally {
          saveButton.disabled = false;
          resetAllButton.disabled = false;
        }
      }

      saveButton.addEventListener("click", savePrompts);
      resetAllButton.addEventListener("click", resetPrompts);
      loadPrompts().catch((error) => {
        setStatus(error instanceof Error ? error.message : "프롬프트를 불러오지 못했습니다.", "error");
      });
    </script>
  </body>
</html>
"""
