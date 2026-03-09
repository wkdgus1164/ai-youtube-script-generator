"""Text normalization, quality validation, and sanitize utilities.

Ported from youtube-script-writer-automation/services/workflow-orchestrator/app/runtime/runner.py
(lines 522-878) as pure module-level functions.

Responsibility: All text processing for the script writer workflow
Dependencies: re (stdlib only)
"""
from __future__ import annotations

import re
from typing import Any


# ── Normalizers ──────────────────────────────────────────────────────────────


def normalize_prompt_output(node_key: str, text: str) -> str:
    """Strip code fences and route to node-specific normalizer."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    normalized = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", normalized)
    normalized = re.sub(r"\n?```$", "", normalized)
    if node_key == "prepare_outline":
        return _normalize_outline_output(normalized)
    if node_key in {"draft_script", "differentiate_script", "expand_script", "format_script", "compose_final"}:
        return _normalize_script_output(normalized)
    if node_key == "generate_intros":
        return _normalize_intro_output(normalized)
    return normalized


def _normalize_outline_output(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if re.match(r"^(以下(は|の)|作成戦略|説明)", line):
            continue
        lines.append(line)
    normalized = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def _normalize_script_output(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if re.match(r"^(以下(は|の)|この追加パート|この長編パート|出力形式|注意事項)", line):
            continue
        if re.match(r"^セグメント\d+", line):
            continue
        if re.match(r"^セクション\s*\d+\s*$", line):
            continue
        if re.match(r"^第\s*\d+\s*章\s*$", line):
            continue
        if re.match(r"^(オープニング|エンディング|エピローグ)\s*$", line):
            continue
        if re.match(r"^[-*]\s*ナレーター[:：]?$", line):
            continue
        if re.match(r"^ナレーター[:：]?$", line):
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        line = re.sub(r"^セクション\s*\d+\s*", "", line)
        line = re.sub(r"^第\s*\d+\s*章(?:では|は|を)?[、,:：]?\s*", "", line)
        line = re.sub(r"^(オープニング|エンディング|エピローグ)\s*[:：]?\s*", "", line)
        line = re.sub(r"\bflashback\b", "導入", line, flags=re.IGNORECASE)
        lines.append(line)
    normalized = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def _normalize_intro_output(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    filtered: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if filtered and filtered[-1] != "":
                filtered.append("")
            continue
        if re.match(r"^(以下(は|の)|ご要望|承知しました|もちろんです|説明|注記)", line):
            continue
        filtered.append(line)
    normalized = "\n".join(filtered).strip()
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


# ── Quality / fallback helpers ────────────────────────────────────────────────


def ensure_outline(text: str, state: dict[str, Any]) -> str:
    cleaned = text.strip()
    if cleaned:
        return cleaned
    transcript = re.sub(r"\s+", " ", str(state.get("transcript", "")).strip())
    excerpt = transcript[:220] or "원문 핵심 쟁점을 우선 정리합니다."
    return "\n".join([
        "構成タイプ: Type B",
        f"オープニングフック: {excerpt}",
        "本文の流れ: 背景 → 핵심 원인 → 사회적 파장 → 시청자 관점의 질문 → 결론",
        "事実ベースの注意点: 推定や断定を避け、因果関係は確認できる範囲でのみ扱う",
        "感情線設計: 불안 제시 → 구조 해설 → 현실적 함의 → 다음 질문으로 마무리",
    ])


def ensure_non_empty(node_key: str, text: str, fallback: str = "") -> str:
    cleaned = text.strip()
    if cleaned:
        return cleaned
    cleaned_fallback = fallback.strip()
    if cleaned_fallback:
        return cleaned_fallback
    raise ValueError(f"{node_key} produced empty output")


def ensure_script_quality(node_key: str, text: str, fallback: str = "") -> str:
    preferred = ensure_non_empty(node_key, text, fallback=fallback)
    cleaned_fallback = fallback.strip()

    if looks_like_meta_output(preferred):
        if cleaned_fallback:
            return cleaned_fallback
        raise ValueError(f"{node_key} produced meta output")

    if cleaned_fallback:
        preferred_len = len(re.sub(r"\s", "", preferred))
        fallback_len = len(re.sub(r"\s", "", cleaned_fallback))
        if fallback_len >= 3200:
            if preferred_len < int(fallback_len * 0.72):
                return cleaned_fallback
        if preferred_len < 2200 and fallback_len >= preferred_len + 1200:
            return cleaned_fallback

    if not re.search(r"[。！？]$", preferred):
        preferred = f"{preferred.rstrip()}。"
    return preferred


def sanitize_script_output(text: str, state: dict[str, Any]) -> str:
    normalized = normalize_prompt_output("format_script", text)
    normalized = replace_placeholder_entities(normalized, state)

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", normalized) if p.strip()]
    cleaned: list[str] = []
    seen: set[str] = set()

    for paragraph in paragraphs:
        p = paragraph
        p = re.sub(r"^セクション\s*\d+\s*", "", p)
        p = re.sub(r"^第\s*\d+\s*章(?:では|は|を)?[、,:：]?\s*", "", p)
        p = re.sub(r"^(オープニング|エンディング|エピローグ)\s*[:：]?\s*", "", p)
        p = p.strip()
        if not p:
            continue
        if looks_like_transcript_leak(p):
            continue
        key = re.sub(r"\s+", " ", p)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(p)

    sanitized = "\n\n".join(cleaned).strip()
    if not sanitized:
        return normalized
    if not re.search(r"[。！？]$", sanitized):
        sanitized = f"{sanitized.rstrip()}。"
    return sanitized


def replace_placeholder_entities(text: str, state: dict[str, Any]) -> str:
    anchor = extract_anchor_entity(str(state.get("transcript", "")))
    if not anchor:
        return text
    for placeholder in ("企業A", "A社"):
        text = text.replace(placeholder, anchor)
    return text


def extract_anchor_entity(transcript: str) -> str | None:
    candidates = re.findall(r"[A-Z][A-Z0-9&.-]{1,10}", transcript)
    filtered = [c for c in candidates if c not in {"AI", "EV", "EB", "GDP"}]
    if not filtered:
        return None
    counts: dict[str, int] = {}
    for c in filtered:
        counts[c] = counts.get(c, 0) + 1
    return max(counts, key=counts.get)  # type: ignore[arg-type]


def ensure_expanded_script(text: str, state: dict[str, Any]) -> str:
    base = normalize_prompt_output("format_script", str(state.get("draft_text", "")))
    expanded = ensure_non_empty("expand_script", text, fallback=base)
    working = expanded if len(expanded) >= len(base) else base
    added = max(len(working) - len(base), 0)
    if added >= 1200 and len(expanded) >= len(base):
        return expanded
    return base


def ensure_intros(text: str, *, formatted_draft: str) -> str:
    cleaned = text.strip()
    if looks_like_three_intros(cleaned) and not contains_hangul(cleaned):
        return cleaned
    return build_fallback_intros(formatted_draft)


def looks_like_three_intros(text: str) -> bool:
    if not text:
        return False
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) >= 3:
        return True
    markers = sum(
        1 for m in ["バージョン1", "バージョン2", "バージョン3", "1.", "2.", "3."]
        if m in text
    )
    return markers >= 3


def build_fallback_intros(formatted_draft: str) -> str:
    cleaned = normalize_prompt_output("format_script", formatted_draft)
    sentences = [s.strip() for s in re.split(r"(?<=[。！？])\s*", cleaned) if s.strip()]
    lead_one = "".join(sentences[:2])[:220]
    lead_two = "".join(sentences[2:4])[:220] or lead_one
    lead_three = "".join(sentences[4:6])[:220] or lead_one
    versions = [
        f"バージョン1: いま日本経済の表面で起きている数字の変化だけを見ていると、本当の構造問題を見誤ります。{lead_one} 今日はその因果関係を掘り下げていきます。",
        f"バージョン2: 物価、賃金、消費のズレが同時に進むとき、家計と企業の現場では何が起きるのか。{lead_two} この流れの核心を掘り下げていきます。",
        f"バージョン3: 一見すると緩やかな減速に見えても、裏側ではもっと深い構造変化が進んでいます。{lead_three} その転換点を掘り下げていきます。",
    ]
    return "\n\n".join(versions)


# ── Character classification helpers ─────────────────────────────────────────


def looks_more_hangul_than_japanese(text: str) -> bool:
    hangul = len(re.findall(r"[\uac00-\ud7a3]", text))
    japanese = len(re.findall(r"[\u3040-\u30ff\u4e00-\u9fff]", text))
    return hangul > 0 and hangul > japanese


def contains_hangul(text: str) -> bool:
    return bool(re.search(r"[\uac00-\ud7a3]", text))


def looks_like_meta_output(text: str) -> bool:
    lowered = text.lower()
    meta_markers = [
        "以下は", "以下の", "セグメント", "ナレーター",
        "出力形式", "注意事項", "箇条書き", "見出し",
        "構成タイプ", "オープニングフック",
    ]
    return any(m.lower() in lowered for m in meta_markers)


def looks_like_transcript_leak(text: str) -> bool:
    if "今回の原資料にも示されているように" in text:
        return True
    if "皆さんこんにちは" in text:
        return True
    return len(re.findall(r"(え、|あの、|その、|ま、)", text)) >= 8


# ── Message text extraction ───────────────────────────────────────────────────


def extract_text(response: object) -> str:
    """Extract plain text string from a LangChain BaseMessage or str."""
    if isinstance(response, str):
        return response.strip()
    content = getattr(response, "content", None)
    if content is None:
        return str(response).strip()
    if isinstance(content, str):
        return content.strip()
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        text = getattr(block, "text", None)
        if text:
            parts.append(str(text))
            continue
        if isinstance(block, dict):
            candidate = block.get("text")
            if isinstance(candidate, str):
                parts.append(candidate)
    return "\n".join(p.strip() for p in parts if p).strip()
