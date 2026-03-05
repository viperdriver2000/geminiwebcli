"""Playwright-based Gemini web interface automation."""
import asyncio
import base64
import re
import shutil
import tempfile
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page

GEMINI_URL = "https://gemini.google.com"
SYSTEM_CHROMIUM = "/snap/bin/chromium"


def _find_chromium() -> str | None:
    """Return system Chromium path if available, else None (Playwright bundled)."""
    if Path(SYSTEM_CHROMIUM).exists():
        return SYSTEM_CHROMIUM
    alt = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    return alt


class GeminiBrowser:
    def __init__(self, profile_dir: Path, headless: bool = True):
        self._base_dir = profile_dir
        self.headless = headless
        self._session_dir: Path | None = None
        self._playwright = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._response_count = 0
        self._last_response_text = ""

    async def start(self):
        """Start browser, open login flow if no profile exists."""
        first_run = not self._base_dir.exists()
        if first_run:
            self._session_dir = self._base_dir
            self._session_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._session_dir = Path(tempfile.mkdtemp(
                prefix="geminiwebcli-", dir=self._base_dir.parent
            ))
            shutil.copytree(self._base_dir, self._session_dir, dirs_exist_ok=True)
        (self._session_dir / "SingletonLock").unlink(missing_ok=True)
        self._playwright = await async_playwright().start()
        headless = self.headless and not first_run
        self._context = await self._playwright.chromium.launch_persistent_context(
            str(self._session_dir),
            headless=headless,
            executable_path=_find_chromium(),
            accept_downloads=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        if first_run:
            await self._login_flow()
        else:
            await self._page.goto(GEMINI_URL)
            await self._page.wait_for_load_state("load")

    async def _login_flow(self):
        """Open browser visibly for manual Google login."""
        print("First run: please log in with your Google account in the browser window.")
        print("Do NOT close the browser. Press Enter here when done...")
        await self._page.goto("https://accounts.google.com")
        await asyncio.get_event_loop().run_in_executor(None, input)
        # Re-acquire page in case the user opened new tabs
        pages = self._context.pages
        self._page = pages[-1] if pages else await self._context.new_page()
        await self._page.goto(GEMINI_URL)
        await self._page.wait_for_load_state("load")

    async def _get_response_text(self, el) -> str:
        """Extract text from a response element, reconstructing markdown code blocks."""
        text = await self._page.evaluate("""el => {
            function toMarkdown(node) {
                if (node.nodeType === 3) return node.textContent;
                const tag = node.tagName?.toLowerCase();
                if (tag === 'pre') {
                    const code = node.querySelector('code');
                    const lang = code?.className?.match(/language-(\\w+)/)?.[1] ?? '';
                    return '\\n```' + lang + '\\n' + (code || node).innerText + '\\n```\\n';
                }
                if (tag === 'code') return '`' + node.innerText + '`';
                if (tag === 'br') return '\\n';
                if (['p','div','li','h1','h2','h3'].includes(tag))
                    return Array.from(node.childNodes).map(toMarkdown).join('') + '\\n';
                return Array.from(node.childNodes).map(toMarkdown).join('');
            }
            return Array.from(el.childNodes).map(toMarkdown).join('').trim();
        }""", el)
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        # Fold language labels into code fences: "Bash\n\n```\n" -> "```bash\n"
        return re.sub(r'\n(\w{1,30})\n{2,6}```\n', lambda m: f'\n```{m.group(1).lower()}\n', text)

    async def send_message(self, text: str):
        """Type and submit a message in the Gemini chat input."""
        await self._page.wait_for_selector("input-area-v2", timeout=30000)
        # Capture baseline BEFORE sending so fast responses are detected
        els = await self._page.query_selector_all("message-content")
        self._response_count = len(els)
        self._last_response_text = await self._get_response_text(els[-1]) if els else ""
        await self._page.locator("input-area-v2").click()
        try:
            old_clip = await self._page.evaluate("() => navigator.clipboard.readText()")
        except Exception:
            old_clip = None
        await self._page.evaluate("text => document.execCommand('insertText', false, text)", text)
        try:
            await self._page.evaluate("text => navigator.clipboard.writeText(text)", old_clip or "")
        except Exception:
            pass
        await asyncio.sleep(0.3)
        sent = await self._page.evaluate("""() => {
            const btn = document.querySelector('button[aria-label="Nachricht senden"]');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }""")
        if not sent:
            await self._page.keyboard.press("Enter")
        # Wait for navigation (new conversation) then let initial elements settle
        try:
            await self._page.wait_for_url("**/app/**", timeout=5000)
        except Exception:
            pass

    async def _count_images(self, el) -> int:
        """Count non-trivial images in a response element."""
        return await self._page.evaluate("""(el) => {
            let count = 0;
            for (const img of el.querySelectorAll('img')) {
                if (img.width >= 50 && !img.src.startsWith('data:image/svg')) count++;
            }
            return count;
        }""", el)

    async def stream_response(self):
        """Async generator yielding growing response text until stable."""
        # Wait until new element appears OR last element text/images change (60s timeout)
        for _ in range(120):
            await asyncio.sleep(0.5)
            els = await self._page.query_selector_all("message-content")
            if len(els) > self._response_count:
                break
            if els:
                last_text = await self._get_response_text(els[-1])
                if last_text != self._last_response_text:
                    break
                img_count = await self._count_images(els[-1])
                if img_count > 0:
                    break
        else:
            return
        # Poll until text and image count are stable
        prev, stable = "", 0
        prev_imgs = 0
        while stable < 3:
            await asyncio.sleep(0.5)
            els = await self._page.query_selector_all("message-content")
            current = await self._get_response_text(els[-1]) if els else ""
            cur_imgs = await self._count_images(els[-1]) if els else 0
            if (current and current != prev) or cur_imgs != prev_imgs:
                if current:
                    yield current
                stable = 0
            elif current or cur_imgs > 0:
                stable += 1
            prev = current
            prev_imgs = cur_imgs
        self._response_count = len(els)

    async def extract_images(self) -> list[bytes]:
        """Extract generated images from the last response as raw bytes."""
        els = await self._page.query_selector_all("message-content")
        if not els:
            return []
        last_el = els[-1]
        # Find all non-trivial img elements
        img_urls = await self._page.evaluate("""(el) => {
            const urls = [];
            for (const img of el.querySelectorAll('img')) {
                if (img.width >= 50 && img.src && !img.src.startsWith('data:image/svg'))
                    urls.push(img.src);
            }
            return urls;
        }""", last_el)
        if not img_urls:
            return []
        # Try full-res download via "Bild in Originalgröße herunterladen" button
        results = []
        parent = await self._page.evaluate_handle(
            "(el) => el.closest('model-response') || el.parentElement?.parentElement || el",
            last_el,
        )
        dl_buttons = await parent.query_selector_all(
            'button[aria-label="Bild in Originalgröße herunterladen"]'
        )
        for btn in dl_buttons:
            try:
                async with self._page.expect_download(timeout=30000) as dl_info:
                    await btn.click()
                download = await dl_info.value
                path = await download.path()
                if path:
                    results.append(Path(path).read_bytes())
                    await download.delete()
            except Exception as e:
                pass
        # Fallback: fetch preview images
        if not results:
            for url in img_urls:
                try:
                    resp = await self._page.request.get(url)
                    if resp.ok:
                        results.append(await resp.body())
                except Exception:
                    pass
        return results

    async def _open_model_picker(self) -> dict[str, str]:
        """Open model picker, return {mode_id: display_name} for all options."""
        await self._page.locator('button[aria-label="Modusauswahl öffnen"]').click()
        await asyncio.sleep(0.5)
        return await self._page.evaluate("""() => {
            const result = {};
            document.querySelectorAll('button[data-test-id^="bard-mode-option-"]').forEach(btn => {
                const id = btn.getAttribute('data-test-id').replace('bard-mode-option-', '');
                const name = btn.querySelector('span.mode-title')?.innerText?.trim() ?? id;
                const desc = btn.querySelector('span.mode-desc')?.innerText?.trim() ?? '';
                result[id] = {name, desc};
            });
            return result;
        }""")

    async def get_models(self) -> dict[str, str]:
        """Return available models as {mode_id: display_name}. Closes picker afterwards."""
        models = await self._open_model_picker()
        await self._page.keyboard.press("Escape")
        return models

    async def select_model(self, mode: str) -> str:
        """Open model picker and select the given mode. Returns display name."""
        models = await self._open_model_picker()
        key = mode.lower()
        match = (
            key if key in models else
            next((k for k in models if k.startswith(key)), None) or
            next((k for k, v in models.items() if v["name"].lower().startswith(key)), None)
        )
        if match is None:
            await self._page.keyboard.press("Escape")
            available = ", ".join(f"{k} ({v['name']})" for k, v in models.items())
            raise ValueError(f"Unknown mode: {mode!r}. Available: {available}")
        btn = self._page.locator(f'button[data-test-id="bard-mode-option-{match}"]')
        if await btn.get_attribute("disabled") is not None:
            await self._page.keyboard.press("Escape")
            raise ValueError(f"Mode {mode!r} ({models[match]['name']}) requires a paid plan.")
        await btn.click()
        return models[match]["name"]

    async def new_chat(self):
        """Start a new conversation."""
        await self._page.goto(GEMINI_URL)
        await self._page.wait_for_load_state("load")
        self._response_count = 0
        self._last_response_text = ""

    async def stop(self):
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()
        if self._session_dir and self._session_dir != self._base_dir:
            shutil.copytree(self._session_dir, self._base_dir, dirs_exist_ok=True)
            shutil.rmtree(self._session_dir, ignore_errors=True)
