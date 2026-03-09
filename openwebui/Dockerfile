ARG OPENWEBUI_BASE_IMAGE=ghcr.io/open-webui/open-webui:v0.8.10
FROM ${OPENWEBUI_BASE_IMAGE}

COPY patch_tool_call_input.py /tmp/patch_tool_call_input.py
COPY script_writer_custom.js /app/build/static/script-writer-custom.js
COPY generate_script_writer_config.py /app/codex/generate_script_writer_config.py
COPY start-codex.sh /app/start-codex.sh

RUN python /tmp/patch_tool_call_input.py \
    && chmod +x /app/start-codex.sh \
    && rm /tmp/patch_tool_call_input.py

CMD ["bash", "/app/start-codex.sh"]
