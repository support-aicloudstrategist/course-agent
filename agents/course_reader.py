"""
Course Reader Agent - Connects to an open browser and extracts course content.

Supports two modes:
1. Connect to an existing Chrome/Chromium browser via CDP (Chrome DevTools Protocol)
2. Take a URL and navigate to it (if user provides credentials)

Handles:
- Text-based courses (HTML pages, documentation)
- Video courses (extracts visible text, captions, transcript panels)
- Multi-page/multi-section courses (navigates through modules)
"""
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from config import (
    BROWSER_CONNECT_TIMEOUT,
    PAGE_LOAD_TIMEOUT,
    SCROLL_PAUSE_TIME,
    MAX_SCROLL_ATTEMPTS,
)


class CourseReader:
    """Reads course content from a browser."""

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.all_content: list[dict] = []

    async def connect_to_browser(self, cdp_url: str = "http://localhost:9222"):
        """Connect to an already-running Chrome/Edge browser via CDP."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.connect_over_cdp(
            cdp_url, timeout=BROWSER_CONNECT_TIMEOUT
        )
        # Get the first context (the user's actual browser session)
        contexts = self.browser.contexts
        if contexts:
            self.context = contexts[0]
        else:
            self.context = await self.browser.new_context()
        print(f"[CourseReader] Connected to browser. {len(self.context.pages)} tab(s) open.")

    async def get_open_tabs(self) -> list[dict]:
        """List all open tabs with their titles and URLs."""
        tabs = []
        for i, page in enumerate(self.context.pages):
            tabs.append({
                "index": i,
                "title": await page.title(),
                "url": page.url,
            })
        return tabs

    async def select_tab(self, index: int):
        """Select a specific browser tab to read from."""
        pages = self.context.pages
        if 0 <= index < len(pages):
            self.page = pages[index]
            await self.page.bring_to_front()
            print(f"[CourseReader] Selected tab: {await self.page.title()}")
        else:
            raise ValueError(f"Tab index {index} out of range (0-{len(pages)-1})")

    async def extract_page_content(self) -> dict:
        """Extract all readable content from the current page."""
        if not self.page:
            raise RuntimeError("No page selected. Call select_tab() first.")

        await self.page.wait_for_load_state("domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        time.sleep(1)  # Allow dynamic content to render

        title = await self.page.title()
        url = self.page.url

        # Extract main text content
        text_content = await self._extract_text()

        # Extract code blocks specifically
        code_blocks = await self._extract_code_blocks()

        # Extract video transcript if present
        transcript = await self._extract_transcript()

        # Extract navigation / module structure
        nav_structure = await self._extract_navigation()

        # Extract images with alt text (for diagrams/architecture)
        images = await self._extract_images()

        # Extract links (for resources, downloads)
        links = await self._extract_links()

        content = {
            "title": title,
            "url": url,
            "text_content": text_content,
            "code_blocks": code_blocks,
            "transcript": transcript,
            "navigation": nav_structure,
            "images": images,
            "links": links,
        }
        self.all_content.append(content)
        return content

    async def _extract_text(self) -> str:
        """Extract all visible text from the page, handling infinite scroll."""
        # First, try to get structured content from common course platforms
        selectors = [
            # Common LMS and course platform selectors
            "article", ".lesson-content", ".course-content", ".lab-content",
            ".markdown-body", ".content-body", ".training-content",
            "#main-content", "main", ".module-content", ".step-content",
            ".instructions", ".lab-instructions", ".exercise-content",
            # AWS / Cloud specific
            ".aws-training-content", ".qwiklabs-content",
            # Udemy, Coursera, etc.
            ".ud-component--course-taking--app", ".rc-DesktopContent",
            # Generic
            "[role='main']", ".content",
        ]

        for selector in selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    if len(text.strip()) > 100:
                        return text.strip()
            except Exception:
                continue

        # Fallback: scroll and collect all text from body
        return await self._scroll_and_extract()

    async def _scroll_and_extract(self) -> str:
        """Scroll through the entire page collecting text content."""
        texts = []
        last_height = 0

        for _ in range(MAX_SCROLL_ATTEMPTS):
            # Get current visible text
            text = await self.page.evaluate("""
                () => {
                    const body = document.body;
                    const selection = window.getSelection();
                    const range = document.createRange();
                    range.selectNodeContents(body);
                    // Get text content but skip script/style
                    const walker = document.createTreeWalker(
                        body, NodeFilter.SHOW_TEXT, {
                            acceptNode: (node) => {
                                const parent = node.parentElement;
                                if (!parent) return NodeFilter.FILTER_REJECT;
                                const tag = parent.tagName.toLowerCase();
                                if (['script', 'style', 'noscript'].includes(tag))
                                    return NodeFilter.FILTER_REJECT;
                                if (parent.offsetHeight === 0)
                                    return NodeFilter.FILTER_REJECT;
                                return NodeFilter.FILTER_ACCEPT;
                            }
                        }
                    );
                    const parts = [];
                    while (walker.nextNode()) {
                        const t = walker.currentNode.textContent.trim();
                        if (t) parts.push(t);
                    }
                    return parts.join('\\n');
                }
            """)
            texts.append(text)

            # Scroll down
            current_height = await self.page.evaluate("document.documentElement.scrollHeight")
            if current_height == last_height:
                break
            last_height = current_height
            await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(SCROLL_PAUSE_TIME)

        # Deduplicate while preserving order
        combined = "\n".join(texts)
        lines = combined.split("\n")
        seen = set()
        unique = []
        for line in lines:
            stripped = line.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                unique.append(stripped)
        return "\n".join(unique)

    async def _extract_code_blocks(self) -> list[dict]:
        """Extract code blocks from the page."""
        blocks = await self.page.evaluate("""
            () => {
                const results = [];
                // <pre><code> blocks
                document.querySelectorAll('pre code, pre, .code-block, .highlight code, .CodeMirror').forEach(el => {
                    const text = el.innerText || el.textContent;
                    if (text && text.trim().length > 5) {
                        const lang = el.className.match(/language-(\\w+)/)?.[1] ||
                                     el.closest('pre')?.className.match(/language-(\\w+)/)?.[1] || '';
                        results.push({ code: text.trim(), language: lang });
                    }
                });
                // Also check for copy-to-clipboard elements (common in labs)
                document.querySelectorAll('[data-copy], .copy-code, .copyable').forEach(el => {
                    const text = el.innerText || el.getAttribute('data-copy') || '';
                    if (text.trim().length > 5) {
                        results.push({ code: text.trim(), language: '' });
                    }
                });
                return results;
            }
        """)
        return blocks

    async def _extract_transcript(self) -> str:
        """Extract video transcript/captions if available."""
        transcript_selectors = [
            ".transcript-text", ".video-transcript", ".captions-text",
            "[class*='transcript']", "[class*='caption']", "[class*='subtitle']",
            ".vjs-text-track-display", ".ytp-caption-segment",
        ]

        for selector in transcript_selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                if elements:
                    texts = []
                    for el in elements:
                        t = await el.inner_text()
                        if t.strip():
                            texts.append(t.strip())
                    if texts:
                        return "\n".join(texts)
            except Exception:
                continue

        # Try to click "Show Transcript" / "Transcript" buttons
        transcript_buttons = [
            "button:has-text('Transcript')", "button:has-text('Show Transcript')",
            "button:has-text('CC')", "[aria-label='Transcript']",
            "[aria-label='Show transcript']",
        ]
        for btn_selector in transcript_buttons:
            try:
                btn = await self.page.query_selector(btn_selector)
                if btn:
                    await btn.click()
                    await asyncio.sleep(2)
                    # Re-try transcript extraction
                    for selector in transcript_selectors:
                        elements = await self.page.query_selector_all(selector)
                        if elements:
                            texts = []
                            for el in elements:
                                t = await el.inner_text()
                                if t.strip():
                                    texts.append(t.strip())
                            if texts:
                                return "\n".join(texts)
            except Exception:
                continue

        return ""

    async def _extract_navigation(self) -> list[dict]:
        """Extract the course module/section navigation structure."""
        nav_items = await self.page.evaluate("""
            () => {
                const items = [];
                const navSelectors = [
                    '.sidebar-navigation a', '.course-nav a', '.module-list a',
                    '.table-of-contents a', '.toc a', 'nav a',
                    '.curriculum-item a', '.lesson-list a', '.section-list a',
                    '[class*="sidebar"] a', '[class*="nav"] li a',
                ];
                for (const sel of navSelectors) {
                    document.querySelectorAll(sel).forEach(a => {
                        const text = (a.innerText || '').trim();
                        const href = a.href || '';
                        if (text && text.length > 2 && text.length < 200) {
                            items.push({ text, href, active: a.classList.contains('active') ||
                                a.getAttribute('aria-current') === 'true' });
                        }
                    });
                    if (items.length > 0) break;
                }
                return items;
            }
        """)
        return nav_items

    async def _extract_images(self) -> list[dict]:
        """Extract images with their alt text (useful for architecture diagrams)."""
        images = await self.page.evaluate("""
            () => {
                const imgs = [];
                document.querySelectorAll('img').forEach(img => {
                    const alt = img.alt || '';
                    const src = img.src || '';
                    if (src && (alt || img.width > 200)) {
                        imgs.push({ alt, src: src.substring(0, 500), width: img.width, height: img.height });
                    }
                });
                return imgs;
            }
        """)
        return images

    async def _extract_links(self) -> list[dict]:
        """Extract relevant resource links."""
        links = await self.page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const text = (a.innerText || '').trim();
                    const href = a.href || '';
                    // Filter for resource-like links
                    if (text && href && !href.startsWith('javascript:') && text.length < 200) {
                        const isResource = /download|github|repo|documentation|docs|resource|file|template/i.test(text + href);
                        if (isResource) {
                            results.push({ text, href });
                        }
                    }
                });
                return results;
            }
        """)
        return links

    async def navigate_to_section(self, section_url: str):
        """Navigate to a specific course section/module."""
        if not self.page:
            raise RuntimeError("No page selected.")
        await self.page.goto(section_url, timeout=PAGE_LOAD_TIMEOUT)
        await self.page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2)

    async def read_all_sections(self) -> list[dict]:
        """Navigate through all course sections and extract content from each."""
        if not self.page:
            raise RuntimeError("No page selected.")

        # First, get the current page content
        first_content = await self.extract_page_content()

        # Get navigation structure
        nav = first_content.get("navigation", [])
        if not nav:
            print("[CourseReader] No multi-section navigation found. Single page only.")
            return self.all_content

        # Navigate to each section
        visited_urls = {self.page.url}
        for item in nav:
            url = item.get("href", "")
            if url and url not in visited_urls and not url.startswith("#"):
                visited_urls.add(url)
                try:
                    print(f"[CourseReader] Navigating to: {item['text'][:60]}")
                    await self.navigate_to_section(url)
                    await self.extract_page_content()
                except Exception as e:
                    print(f"[CourseReader] Failed to read section: {e}")

        return self.all_content

    async def take_screenshot(self, path: str):
        """Take a screenshot of the current page."""
        if self.page:
            await self.page.screenshot(path=path, full_page=False)

    async def close(self):
        """Disconnect from browser (does NOT close the user's browser)."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print("[CourseReader] Disconnected from browser.")

    def get_all_content_as_text(self) -> str:
        """Combine all extracted content into a single text for AI processing."""
        parts = []
        for i, content in enumerate(self.all_content):
            parts.append(f"\n{'='*60}")
            parts.append(f"SECTION {i+1}: {content['title']}")
            parts.append(f"URL: {content['url']}")
            parts.append(f"{'='*60}\n")

            if content['text_content']:
                parts.append("--- CONTENT ---")
                parts.append(content['text_content'])

            if content['code_blocks']:
                parts.append("\n--- CODE BLOCKS ---")
                for j, block in enumerate(content['code_blocks']):
                    lang = block.get('language', '')
                    parts.append(f"\n```{lang}")
                    parts.append(block['code'])
                    parts.append("```")

            if content['transcript']:
                parts.append("\n--- VIDEO TRANSCRIPT ---")
                parts.append(content['transcript'])

            if content['links']:
                parts.append("\n--- RESOURCES ---")
                for link in content['links']:
                    parts.append(f"  - {link['text']}: {link['href']}")

        return "\n".join(parts)
