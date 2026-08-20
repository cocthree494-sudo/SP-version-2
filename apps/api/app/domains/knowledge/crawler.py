"""Bounded same-host crawler with robots, redirect, and SSRF controls."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import posixpath
import socket
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import ClassVar, Protocol
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from anyio import to_thread

from app.core.config import settings
from app.domains.knowledge.extraction import normalize_text, normalize_title


class CrawlError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class CrawledPage:
    url: str
    title: str | None
    text: str
    checksum_sha256: str


class HostResolver(Protocol):
    async def resolve(
        self,
        hostname: str,
    ) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]: ...


class SystemHostResolver:
    async def resolve(self, hostname: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        def _resolve() -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
            addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
            return {ipaddress.ip_address(item[4][0]) for item in addresses}

        try:
            return await to_thread.run_sync(_resolve)
        except socket.gaierror as exc:
            raise CrawlError(
                "dns_resolution_failed",
                "Website hostname could not be resolved",
                retryable=True,
            ) from exc


_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {"fbclid", "gclid"}


def canonicalize_url(value: str) -> str:
    raw = value.strip()
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise CrawlError("invalid_url", "Website URL is invalid", retryable=False) from exc
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise CrawlError("invalid_url", "Only HTTP(S) website URLs are supported", retryable=False)
    if parsed.username or parsed.password:
        raise CrawlError("invalid_url", "Website URLs cannot contain credentials", retryable=False)
    scheme = parsed.scheme.casefold()
    hostname = parsed.hostname.casefold().encode("idna").decode("ascii")
    try:
        port = parsed.port
    except ValueError as exc:
        raise CrawlError("invalid_port", "Website URL port is invalid", retryable=False) from exc
    if port not in {None, 80, 443}:
        raise CrawlError("unsafe_port", "Only standard HTTP(S) ports are allowed", retryable=False)
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None
    netloc = hostname if port is None else f"{hostname}:{port}"
    decoded_path = unquote(parsed.path or "/")
    normalized_path = posixpath.normpath(decoded_path)
    if decoded_path.endswith("/") and not normalized_path.endswith("/"):
        normalized_path += "/"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    path = quote(normalized_path, safe="/:@-._~!$&'()*+,;=")
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in _TRACKING_QUERY_KEYS
        and not key.casefold().startswith(_TRACKING_QUERY_PREFIXES)
    ]
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query_items)), ""))


def _reject_literal_private_host(hostname: str) -> None:
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        raise CrawlError("unsafe_host", "Local website addresses are not allowed", retryable=False)
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise CrawlError(
            "unsafe_host",
            "Private or reserved addresses are not allowed",
            retryable=False,
        )


async def validate_public_url(url: str, resolver: HostResolver) -> str:
    canonical = canonicalize_url(url)
    hostname = urlsplit(canonical).hostname
    if hostname is None:
        raise CrawlError("invalid_url", "Website URL has no hostname", retryable=False)
    _reject_literal_private_host(hostname)
    addresses = await resolver.resolve(hostname)
    if not addresses or any(not address.is_global for address in addresses):
        raise CrawlError(
            "unsafe_host",
            "Website hostname resolves to an unsafe address",
            retryable=False,
        )
    return canonical


class UsefulHtmlParser(HTMLParser):
    _ignored: ClassVar[set[str]] = {
        "script",
        "style",
        "noscript",
        "svg",
        "canvas",
        "template",
    }
    _block: ClassVar[set[str]] = {
        "p",
        "div",
        "article",
        "section",
        "main",
        "h1",
        "h2",
        "h3",
        "h4",
        "li",
        "br",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[str] = []
        self.title_parts: list[str] = []
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        if lowered in self._ignored:
            self._ignored_depth += 1
        if lowered == "title":
            self._in_title = True
        if lowered == "a":
            attributes = dict(attrs)
            href = attributes.get("href")
            if href:
                self.links.append(href)
        if lowered in self._block and self._ignored_depth == 0:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered == "title":
            self._in_title = False
        if lowered in self._ignored and self._ignored_depth:
            self._ignored_depth -= 1
        if lowered in self._block and self._ignored_depth == 0:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        self.parts.append(data)


class WebsiteCrawler:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        resolver: HostResolver | None = None,
    ) -> None:
        self.client = client
        self.resolver = resolver or SystemHostResolver()

    async def _request(self, url: str, *, root_hostname: str) -> httpx.Response:
        current = url
        for _redirect in range(settings.WEBSITE_CRAWL_MAX_REDIRECTS + 1):
            current = await validate_public_url(current, self.resolver)
            if urlsplit(current).hostname != root_hostname:
                raise CrawlError(
                    "cross_domain_redirect",
                    "Website redirected outside its configured hostname",
                    retryable=False,
                )
            try:
                response = await self.client.get(
                    current,
                    headers={"User-Agent": settings.WEBSITE_CRAWL_USER_AGENT},
                    follow_redirects=False,
                )
            except httpx.TimeoutException as exc:
                raise CrawlError(
                    "website_timeout",
                    "Website request timed out",
                    retryable=True,
                ) from exc
            except httpx.HTTPError as exc:
                raise CrawlError(
                    "website_unavailable",
                    "Website request failed",
                    retryable=True,
                ) from exc
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise CrawlError(
                        "invalid_redirect",
                        "Website returned an invalid redirect",
                        retryable=False,
                    )
                current = urljoin(current, location)
                continue
            if response.status_code >= 500 or response.status_code == 429:
                raise CrawlError(
                    "website_unavailable",
                    "Website is temporarily unavailable",
                    retryable=True,
                )
            if response.status_code >= 400:
                raise CrawlError(
                    "website_request_rejected",
                    f"Website returned HTTP {response.status_code}",
                    retryable=False,
                )
            if len(response.content) > settings.WEBSITE_CRAWL_MAX_RESPONSE_BYTES:
                raise CrawlError(
                    "page_too_large",
                    "Website page exceeds the size limit",
                    retryable=False,
                )
            return response
        raise CrawlError(
            "too_many_redirects",
            "Website returned too many redirects",
            retryable=False,
        )

    async def _robots(self, start_url: str, root_hostname: str) -> RobotFileParser:
        parsed = urlsplit(start_url)
        robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
        parser = RobotFileParser(robots_url)
        try:
            response = await self._request(robots_url, root_hostname=root_hostname)
        except CrawlError as exc:
            if exc.code == "website_request_rejected":
                parser.parse([])
                return parser
            raise
        parser.parse(response.text.splitlines())
        return parser

    async def crawl(
        self,
        start_url: str,
        *,
        max_pages: int,
        max_depth: int,
        request_delay_seconds: float,
        progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> list[CrawledPage]:
        canonical_start = await validate_public_url(start_url, self.resolver)
        root_hostname = urlsplit(canonical_start).hostname
        if root_hostname is None:
            raise CrawlError("invalid_url", "Website URL has no hostname", retryable=False)
        robots = await self._robots(canonical_start, root_hostname)
        robots_delay = robots.crawl_delay(settings.WEBSITE_CRAWL_USER_AGENT) or 0
        delay = max(request_delay_seconds, min(float(robots_delay), 10.0))
        pending: deque[tuple[str, int]] = deque([(canonical_start, 0)])
        visited: set[str] = set()
        content_checksums: set[str] = set()
        pages: list[CrawledPage] = []

        while pending and len(pages) < max_pages:
            url, depth = pending.popleft()
            canonical = canonicalize_url(url)
            if canonical in visited:
                continue
            visited.add(canonical)
            if not robots.can_fetch(settings.WEBSITE_CRAWL_USER_AGENT, canonical):
                continue
            if pages and delay:
                await asyncio.sleep(delay)
            try:
                response = await self._request(canonical, root_hostname=root_hostname)
            except CrawlError as exc:
                # A stale internal link should not discard useful pages already
                # found on an otherwise healthy website. The configured start
                # URL still fails closed so a mistyped or inaccessible source
                # cannot be reported as successfully ingested.
                if canonical != canonical_start and exc.code == "website_request_rejected":
                    continue
                raise
            media_type = response.headers.get("content-type", "").partition(";")[0].casefold()
            if media_type not in {"text/html", "application/xhtml+xml", ""}:
                continue
            parser = UsefulHtmlParser()
            try:
                parser.feed(response.text)
            except Exception as exc:
                raise CrawlError(
                    "invalid_html",
                    "Website HTML could not be parsed",
                    retryable=False,
                ) from exc
            text = normalize_text(" ".join(parser.parts))
            if text:
                checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if checksum not in content_checksums:
                    content_checksums.add(checksum)
                    pages.append(
                        CrawledPage(
                            url=canonical,
                            title=normalize_title(" ".join(parser.title_parts)),
                            text=text,
                            checksum_sha256=checksum,
                        )
                    )
                    if progress is not None:
                        await progress(len(pages), max_pages)
            if depth >= max_depth:
                continue
            for href in parser.links:
                try:
                    target = canonicalize_url(urljoin(canonical, href))
                except CrawlError:
                    continue
                if urlsplit(target).hostname == root_hostname and target not in visited:
                    pending.append((target, depth + 1))
        if not pages:
            raise CrawlError(
                "no_useful_pages",
                "No crawlable useful text was found",
                retryable=False,
            )
        return pages


__all__ = [
    "CrawlError",
    "CrawledPage",
    "HostResolver",
    "SystemHostResolver",
    "UsefulHtmlParser",
    "WebsiteCrawler",
    "canonicalize_url",
    "validate_public_url",
]
