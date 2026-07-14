from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

import httpx

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
SERPER_SEARCH_URL = "https://google.serper.dev/search"
BRAVE_SAFE_PAGE_SIZE = 10


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    description: str
    extra_snippets: tuple[str, ...] = ()


class BraveSearcher:
    def __init__(self, api_key: str, *, timeout: float = 30) -> None:
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_environment(cls) -> BraveSearcher:
        return cls(os.environ["BRAVE_SEARCH_API_KEY"])

    def search(self, query: str, count: int) -> list[SearchResult]:
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        params = {
            "q": query,
            # Some Brave subscription tiers reject counts above 10. Multiple
            # official-domain queries are merged by the caller, so the smaller
            # page size is both cheaper and less brittle.
            "count": min(BRAVE_SAFE_PAGE_SIZE, max(1, count)),
            "search_lang": "en",
            "safesearch": "strict",
            "extra_snippets": "true",
        }
        response = httpx.get(
            BRAVE_SEARCH_URL,
            headers=headers,
            params=params,
            timeout=self.timeout,
        )
        if response.status_code == 422:
            params.pop("extra_snippets")
            response = httpx.get(
                BRAVE_SEARCH_URL,
                headers=headers,
                params=params,
                timeout=self.timeout,
            )
        response.raise_for_status()
        payload = response.json()
        return [
            SearchResult(
                title=str(item.get("title", "")).strip(),
                url=str(item.get("url", "")).strip(),
                description=str(item.get("description", "")).strip(),
                extra_snippets=tuple(
                    str(value).strip()
                    for value in item.get("extra_snippets", [])
                    if str(value).strip()
                ),
            )
            for item in payload.get("web", {}).get("results", [])
            if item.get("url")
        ]


class SerperSearcher:
    def __init__(self, api_key: str, *, timeout: float = 30) -> None:
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_environment(cls) -> SerperSearcher:
        api_key = (
            os.environ.get("SERPER_API_KEY") or os.environ["SERPER_SEARCH_API_KEY"]
        )
        return cls(api_key)

    def search(self, query: str, count: int) -> list[SearchResult]:
        payload = {
            "q": query,
            "num": max(1, min(count, 100)),
            "gl": "us",
            "hl": "en",
        }
        response = httpx.post(
            SERPER_SEARCH_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-API-KEY": self.api_key,
            },
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return [
            SearchResult(
                title=str(item.get("title", "")).strip(),
                url=str(item.get("link", "")).strip(),
                description=str(item.get("snippet", "")).strip(),
            )
            for item in response.json().get("organic", [])
            if item.get("link")
        ]


class SearchRouter:
    def __init__(
        self,
        providers: tuple[tuple[str, Callable[[str, int], list[SearchResult]]], ...],
        *,
        merge_all: bool = False,
    ) -> None:
        self.providers = providers
        self.merge_all = merge_all
        self.used_providers: list[str] = []
        self.usage = {
            name: {"queries": 0, "results": 0, "errors": 0}
            for name, _searcher in providers
        }

    @property
    def provider_label(self) -> str:
        if self.used_providers:
            return "+".join(self.used_providers)
        if self.providers:
            return "+".join(name for name, _searcher in self.providers)
        return "configured-seeds-only"

    def search(self, query: str, count: int) -> list[SearchResult]:
        results: dict[str, SearchResult] = {}
        errors = []
        successful_provider = False
        for name, searcher in self.providers:
            self.usage[name]["queries"] += 1
            try:
                provider_results = searcher(query, count)
            except Exception as exc:
                self.usage[name]["errors"] += 1
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
                continue
            successful_provider = True
            self.usage[name]["results"] += len(provider_results)
            if name not in self.used_providers:
                self.used_providers.append(name)
            for result in provider_results:
                results.setdefault(result.url.split("#", 1)[0], result)
            if not self.merge_all:
                break
        if not successful_provider and errors:
            raise RuntimeError("; ".join(errors))
        return list(results.values())[:count]


def search_router_from_environment(search_priority: str) -> SearchRouter:
    providers = []
    if os.environ.get("SERPER_API_KEY") or os.environ.get("SERPER_SEARCH_API_KEY"):
        providers.append(("serper", SerperSearcher.from_environment().search))
    if os.environ.get("BRAVE_SEARCH_API_KEY"):
        providers.append(("brave", BraveSearcher.from_environment().search))
    return SearchRouter(
        tuple(providers),
        merge_all=search_priority.strip().lower() == "high",
    )
