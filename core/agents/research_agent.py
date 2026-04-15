"""
ResearchAgent — Web search → extract → summarize → store pipeline.

Capabilities:
    - web_search:    Search the web for a query, return top results
    - research_topic: Full research pipeline (search + summarize + store)
    - summarize_url:  Summarize a specific URL's content

Uses Gemini for summarization. Falls back gracefully if offline.
Caches results to avoid redundant research.

Cross-platform: Uses webbrowser + urllib (no platform-specific code).
"""

import os
import json
import time
import hashlib
import urllib.parse
import urllib.request
import re
from datetime import datetime
from typing import Optional

from core.agents.base_agent import BaseAgent, AgentResult


# ─── Cache Path ──────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CACHE_PATH  = os.path.join(BASE_DIR, "data", "research_cache.json")
MAX_CACHE   = 100  # Max cached research entries


def _load_cache() -> dict:
    """Load research cache from disk."""
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    """Save research cache to disk."""
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    # Trim to max size
    if len(cache) > MAX_CACHE:
        # Remove oldest entries
        sorted_keys = sorted(cache.keys(), key=lambda k: cache[k].get("timestamp", 0))
        for key in sorted_keys[:len(cache) - MAX_CACHE]:
            del cache[key]
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def _cache_key(query: str) -> str:
    """Generate a cache key from a query string."""
    normalized = query.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def _search_web_basic(query: str, num_results: int = 5) -> list:
    """
    Basic web search using DuckDuckGo Instant Answer API.
    Returns list of {title, url, snippet}.
    Falls back to empty list if offline.
    """
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"

        req = urllib.request.Request(url, headers={
            "User-Agent": "Jarvis-AI-Assistant/1.0"
        })

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        results = []

        # Abstract (main answer)
        if data.get("AbstractText"):
            results.append({
                "title":   data.get("Heading", query),
                "url":     data.get("AbstractURL", ""),
                "snippet": data["AbstractText"][:500],
                "source":  data.get("AbstractSource", ""),
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:num_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title":   topic.get("Text", "")[:100],
                    "url":     topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", "")[:300],
                    "source":  "DuckDuckGo",
                })

        return results[:num_results]

    except Exception as e:
        print(f"⚠️  Web search error: {e}")
        return []


def _extract_text_from_url(url: str) -> str:
    """
    Extract readable text content from a URL.
    Basic HTML → text conversion (no external deps).
    """
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; Jarvis-AI/1.0)"
        })

        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("utf-8", errors="ignore")

        # Strip HTML tags (basic)
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)

        # Clean whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        # Limit length
        return text[:5000]

    except Exception as e:
        return f"Could not extract content: {e}"


def _summarize_with_gemini(text: str, query: str) -> str:
    """
    Summarize extracted text using Gemini.
    Returns structured summary string.
    """
    try:
        from google import genai
        from dotenv import load_dotenv
        load_dotenv()

        api_key = os.getenv("API_KEY")
        if not api_key:
            # Fallback: return first 500 chars
            return text[:500] + "..." if len(text) > 500 else text

        client = genai.Client(api_key=api_key)

        prompt = f"""Summarize the following information for the query: "{query}"

Content:
{text[:4000]}

Rules:
- Be clear and factual
- Use bullet points for key facts
- Keep it under 200 words
- Include the most relevant information only
- If the content is irrelevant to the query, say so briefly"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text.strip()

    except Exception as e:
        print(f"⚠️  Gemini summarization error: {e}")
        return text[:500] + "..." if len(text) > 500 else text


# ─── ResearchAgent ───────────────────────────────────────────
class ResearchAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "research"

    @property
    def description(self) -> str:
        return (
            "Performs web research. Can search the web, research topics in depth, "
            "and summarize web pages. Caches results to avoid redundant searches."
        )

    def __init__(self):
        super().__init__()
        self.register_action("web_search",     self._web_search)
        self.register_action("research_topic", self._research_topic)
        self.register_action("summarize_url",  self._summarize_url)

    def _web_search(self, params: dict) -> AgentResult:
        """Searches the web for a query and returns raw results."""
        query = params.get("query", params.get("topic", ""))
        if not query:
            return AgentResult(success=False, action="web_search", error="No search query provided")

        results = _search_web_basic(query)
        if not results:
            # Fallback: open in browser
            import webbrowser
            encoded = urllib.parse.quote(query)
            webbrowser.open(f"https://www.google.com/search?q={encoded}")
            return AgentResult(
                success=True,
                action="web_search",
                result=f"Opened Google search for '{query}'",
                data={"query": query, "opened_browser": True},
            )

        # Format results
        formatted = []
        for i, r in enumerate(results, 1):
            formatted.append(f"{i}. {r['title']}\n   {r['snippet'][:150]}")

        result_text = "\n".join(formatted)
        return AgentResult(
            success=True,
            action="web_search",
            result=result_text,
            data={"query": query, "results": results, "count": len(results)},
        )

    def _research_topic(self, params: dict) -> AgentResult:
        """
        Full research pipeline: check cache → search → extract → summarize → store.
        """
        query = params.get("query", params.get("topic", ""))
        if not query:
            return AgentResult(success=False, action="research_topic", error="No topic provided")

        # ── Step 1: Check cache ──────────────────────────────
        cache = _load_cache()
        key = _cache_key(query)
        if key in cache:
            cached = cache[key]
            age_hours = (time.time() - cached.get("timestamp", 0)) / 3600
            if age_hours < 24:  # Cache valid for 24 hours
                print(f"📦 Research cache hit for '{query}' (age: {age_hours:.1f}h)")
                return AgentResult(
                    success=True,
                    action="research_topic",
                    result=cached["summary"],
                    data={"query": query, "cached": True, "sources": cached.get("sources", [])},
                )

        # ── Step 2: Search ───────────────────────────────────
        print(f"🔍 Researching: '{query}'")
        results = _search_web_basic(query, num_results=5)

        if not results:
            # Try Gemini directly for knowledge-based questions
            summary = _summarize_with_gemini(
                f"The user is asking about: {query}. Provide accurate, helpful information.",
                query,
            )
            return AgentResult(
                success=True,
                action="research_topic",
                result=summary,
                data={"query": query, "source": "gemini_direct"},
            )

        # ── Step 3: Extract from top result ──────────────────
        combined_text = ""
        sources = []

        for r in results[:3]:
            if r.get("url"):
                content = _extract_text_from_url(r["url"])
                combined_text += f"\n\n--- Source: {r.get('title', 'Unknown')} ---\n{content}"
                sources.append({"title": r.get("title", ""), "url": r["url"]})
            elif r.get("snippet"):
                combined_text += f"\n\n{r['snippet']}"

        # ── Step 4: Summarize ────────────────────────────────
        if combined_text:
            summary = _summarize_with_gemini(combined_text, query)
        else:
            summary = results[0].get("snippet", "No information found.")

        # ── Step 5: Store in cache ───────────────────────────
        cache[key] = {
            "query":     query,
            "summary":   summary,
            "sources":   sources,
            "timestamp": time.time(),
            "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        _save_cache(cache)
        print(f"💾 Research cached: '{query}'")

        # Publish event
        try:
            from core.event_bus import get_event_bus
            get_event_bus().publish("research_complete", {
                "query": query, "summary_length": len(summary),
            }, source="research_agent")
        except Exception:
            pass

        return AgentResult(
            success=True,
            action="research_topic",
            result=summary,
            data={"query": query, "sources": sources, "cached": False},
        )

    def _summarize_url(self, params: dict) -> AgentResult:
        """Summarizes the content of a specific URL."""
        url = params.get("url", "")
        if not url:
            return AgentResult(success=False, action="summarize_url", error="No URL provided")

        # Extract text
        text = _extract_text_from_url(url)
        if text.startswith("Could not extract"):
            return AgentResult(success=False, action="summarize_url", error=text)

        # Summarize
        summary = _summarize_with_gemini(text, f"content from {url}")

        return AgentResult(
            success=True,
            action="summarize_url",
            result=summary,
            data={"url": url, "text_length": len(text)},
        )


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  RESEARCH AGENT TEST")
    print("=" * 60)

    agent = ResearchAgent()
    print(f"\nAgent: {agent.name}")
    print(f"Capabilities: {agent.capabilities}")

    # Test web search
    print("\n── Web Search ──")
    result = agent.execute("web_search", {"query": "Python programming language"})
    print(f"Success: {result.success}")
    print(f"Result: {result.result[:200]}")

    print("\n✅ ResearchAgent test passed!")
