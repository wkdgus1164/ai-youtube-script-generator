"""
웹 검색 툴 - Tavily API 사용 (없으면 더미 결과 반환).
assistant-research 그래프에서 사용됩니다.
"""
import json
import logging
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def web_search_tool(query: str, max_results: int = 3) -> str:
    """
    웹에서 최신 정보를 검색합니다.

    Args:
        query: 검색할 키워드 또는 질문
        max_results: 최대 검색 결과 수 (기본 3)

    Returns:
        검색 결과를 JSON 문자열로 반환
    """
    try:
        from langchain_community.tools.tavily_search import TavilySearchResults
        from config import settings

        if not settings.tavily_api_key:
            return _dummy_search(query)

        searcher = TavilySearchResults(
            max_results=max_results,
            tavily_api_key=settings.tavily_api_key,
        )
        results = searcher.invoke(query)
        return json.dumps(results, ensure_ascii=False)

    except ImportError:
        logger.warning("langchain_community not installed, using dummy search")
        return _dummy_search(query)
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return json.dumps({"error": str(e)})


def _dummy_search(query: str) -> str:
    """Tavily 키가 없을 때 반환하는 더미 결과."""
    return json.dumps([
        {
            "title": f"[더미] {query} 관련 문서",
            "url": "https://example.com/result1",
            "content": f"'{query}'에 대한 더미 검색 결과입니다. "
                       "실제 사용을 위해 TAVILY_API_KEY를 .env에 설정하세요.",
        }
    ], ensure_ascii=False)
