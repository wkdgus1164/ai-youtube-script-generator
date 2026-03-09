"""Python code execution tool — runs code in a subprocess sandbox.

Used by the assistant-dev graph.

TODO(template-user): In production, replace subprocess execution with a
proper sandbox like E2B (https://e2b.dev) or a Docker container to prevent
arbitrary code execution on the host.

Responsibility: Code execution tool
Dependencies: langchain-core
"""
import logging
import subprocess
import tempfile
import os

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10


@tool
def code_executor_tool(code: str, language: str = "python") -> str:
    """
    Python 코드 스니펫을 격리된 서브프로세스에서 실행하고 결과를 반환합니다.

    Args:
        code: 실행할 Python 코드
        language: 프로그래밍 언어 (현재 'python'만 지원)

    Returns:
        코드 실행 결과 (stdout + stderr 합산)
    """
    if language.lower() != "python":
        return f"현재 {language}는 지원하지 않습니다. python만 지원합니다."

    # 임시 파일에 코드를 저장 후 서브프로세스로 실행
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(  # noqa: S603
            ["python3", tmp_path],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        parts = []
        if result.stdout:
            parts.append(f"[stdout]\n{result.stdout}")
        if result.stderr:
            parts.append(f"[stderr]\n{result.stderr}")
        if not parts:
            parts.append(f"[완료] 종료 코드 {result.returncode}")
        return "\n".join(parts)

    except subprocess.TimeoutExpired:
        return f"[타임아웃] {TIMEOUT_SECONDS}초 초과로 실행이 중단되었습니다."
    except Exception as e:
        logger.error(f"Code executor error: {e}")
        return f"[오류] {e}"
    finally:
        os.unlink(tmp_path)
