"""
Google Docs Integration for Eversale CLI

Provides automation capabilities for Google Docs including document creation,
content management, formatting, and text manipulation.

Key Features:
- Create new documents with formatted content
- Open existing documents
- Append content to documents
- Find and replace text
- Support markdown-like formatting syntax
- Handle headers, lists, bold, italic, links

Usage:
    from engine.agent.google_docs_integration import create_google_doc

    result = await create_google_doc(
        page=page,
        title="Project Plan",
        content="# Introduction\n\nThis is **bold** text."
    )
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError


@dataclass
class DocCreateResult:
    """Result from creating a Google Doc"""
    success: bool
    url: Optional[str] = None
    title: Optional[str] = None
    error: Optional[str] = None


@dataclass
class DocOpenResult:
    """Result from opening a Google Doc"""
    success: bool
    title: Optional[str] = None
    error: Optional[str] = None


class GoogleDocsFormattingMixin:
    """Mixin providing text formatting capabilities for Google Docs"""

    FORMATTING_SHORTCUTS = {
        'bold': 'Control+b',
        'italic': 'Control+i',
        'underline': 'Control+u',
        'h1': 'Control+Alt+1',
        'h2': 'Control+Alt+2',
        'h3': 'Control+Alt+3',
        'h4': 'Control+Alt+4',
        'h5': 'Control+Alt+5',
        'h6': 'Control+Alt+6',
        'normal': 'Control+Alt+0',
        'bullet_list': 'Control+Shift+8',
        'numbered_list': 'Control+Shift+7',
        'link': 'Control+k',
    }

    async def apply_format(self, page: Page, format_type: str, text: Optional[str] = None):
        """
        Apply formatting to selected text or current position

        Args:
            page: Playwright page object
            format_type: Type of formatting from FORMATTING_SHORTCUTS
            text: Optional text to type after applying format
        """
        if format_type not in self.FORMATTING_SHORTCUTS:
            raise ValueError(f"Unknown format type: {format_type}")

        shortcut = self.FORMATTING_SHORTCUTS[format_type]
        await page.keyboard.press(shortcut)
        await asyncio.sleep(0.1)

        if text:
            await page.keyboard.type(text, delay=10)
            await asyncio.sleep(0.05)


class GoogleDocsIntegration(GoogleDocsFormattingMixin):
    """Main integration class for Google Docs automation"""

    DOCS_HOME = "https://docs.google.com"
    DOCS_NEW = "https://docs.google.com/document/create"

    SELECTORS = {
        'title_input': '.docs-title-input',
        'editor_canvas': '.kix-appview-editor',
        'save_status': '.docs-save-indicator-text',
        'share_button': '[aria-label*="Share"]',
        'find_replace_dialog': '[role="dialog"][aria-label*="Find and replace"]',
        'find_input': 'input[aria-label*="Find"]',
        'replace_input': 'input[aria-label*="Replace"]',
        'replace_all_button': 'button:has-text("Replace all")',
    }

    def __init__(self, page: Page):
        """
        Initialize Google Docs integration

        Args:
            page: Playwright page object
        """
        self.page = page

    async def create_document(self, title: str, content: str = "") -> DocCreateResult:
        """
        Create a new Google Doc with title and content

        Args:
            title: Document title
            content: Document content with markdown-like formatting
                    Supports:
                    - # Header 1 through ###### Header 6
                    - **bold text**
                    - *italic text*
                    - [link text](url)
                    - - Bullet lists (lines starting with -)
                    - 1. Numbered lists (lines starting with number.)

        Returns:
            DocCreateResult with success status, URL, and any errors
        """
        try:
            # Check if logged in
            login_check = await self._check_login_state()
            if not login_check:
                return DocCreateResult(
                    success=False,
                    error="Not logged into Google account. Please log in first."
                )

            # Create blank document
            doc_created = await self._create_blank_document()
            if not doc_created:
                return DocCreateResult(
                    success=False,
                    error="Failed to create blank document"
                )

            # Set title
            await self._set_document_title(title)

            # Add content if provided
            if content:
                await self._add_content(content)

            # Wait for save and get URL
            url = await self._wait_for_save_and_get_url()

            return DocCreateResult(
                success=True,
                url=url,
                title=title
            )

        except Exception as e:
            return DocCreateResult(
                success=False,
                error=f"Error creating document: {str(e)}"
            )

    async def open_document(self, url: str) -> DocOpenResult:
        """
        Open an existing Google Doc

        Args:
            url: Full URL to the Google Doc

        Returns:
            DocOpenResult with success status and document title
        """
        try:
            # Navigate to document
            await self.page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for editor to load
            await self.page.wait_for_selector(
                self.SELECTORS['editor_canvas'],
                state="visible",
                timeout=10000
            )

            # Get document title
            title = await self._get_document_title()

            return DocOpenResult(
                success=True,
                title=title
            )

        except PlaywrightTimeoutError:
            return DocOpenResult(
                success=False,
                error="Timeout waiting for document to load"
            )
        except Exception as e:
            return DocOpenResult(
                success=False,
                error=f"Error opening document: {str(e)}"
            )

    async def append_to_document(self, content: str, url: Optional[str] = None) -> DocCreateResult:
        """
        Append content to the end of a document

        Args:
            content: Content to append (supports markdown-like formatting)
            url: Optional URL to open first. If None, uses current page

        Returns:
            DocCreateResult with success status
        """
        try:
            # Open document if URL provided
            if url:
                open_result = await self.open_document(url)
                if not open_result.success:
                    return DocCreateResult(
                        success=False,
                        error=open_result.error
                    )

            # Move to end of document
            await self.page.keyboard.press('Control+End')
            await asyncio.sleep(0.2)

            # Add a newline before appending
            await self.page.keyboard.press('Enter')
            await asyncio.sleep(0.1)

            # Add content
            await self._add_content(content)

            # Wait for save
            current_url = await self._wait_for_save_and_get_url()
            title = await self._get_document_title()

            return DocCreateResult(
                success=True,
                url=current_url,
                title=title
            )

        except Exception as e:
            return DocCreateResult(
                success=False,
                error=f"Error appending to document: {str(e)}"
            )

    async def find_and_replace(
        self,
        find_text: str,
        replace_text: str,
        url: Optional[str] = None
    ) -> DocCreateResult:
        """
        Find and replace text in a document

        Args:
            find_text: Text to find
            replace_text: Text to replace with
            url: Optional URL to open first. If None, uses current page

        Returns:
            DocCreateResult with success status
        """
        try:
            # Open document if URL provided
            if url:
                open_result = await self.open_document(url)
                if not open_result.success:
                    return DocCreateResult(
                        success=False,
                        error=open_result.error
                    )

            # Open find and replace dialog (Ctrl+H)
            await self.page.keyboard.press('Control+h')
            await asyncio.sleep(0.5)

            # Wait for dialog to appear
            await self.page.wait_for_selector(
                self.SELECTORS['find_replace_dialog'],
                state="visible",
                timeout=5000
            )

            # Type find text
            find_input = self.page.locator(self.SELECTORS['find_input'])
            await find_input.click()
            await find_input.fill(find_text)
            await asyncio.sleep(0.2)

            # Type replace text
            replace_input = self.page.locator(self.SELECTORS['replace_input'])
            await replace_input.click()
            await replace_input.fill(replace_text)
            await asyncio.sleep(0.2)

            # Click Replace All
            replace_all_btn = self.page.locator(self.SELECTORS['replace_all_button'])
            await replace_all_btn.click()
            await asyncio.sleep(0.5)

            # Close dialog (Escape)
            await self.page.keyboard.press('Escape')
            await asyncio.sleep(0.3)

            # Wait for save
            current_url = await self._wait_for_save_and_get_url()
            title = await self._get_document_title()

            return DocCreateResult(
                success=True,
                url=current_url,
                title=title
            )

        except PlaywrightTimeoutError:
            return DocCreateResult(
                success=False,
                error="Timeout waiting for find/replace dialog"
            )
        except Exception as e:
            return DocCreateResult(
                success=False,
                error=f"Error in find and replace: {str(e)}"
            )

    # Private helper methods

    async def _check_login_state(self) -> bool:
        """
        Check if user is logged into Google

        Returns:
            True if logged in, False otherwise
        """
        try:
            # Navigate to Google Docs home
            await self.page.goto(self.DOCS_HOME, wait_until="networkidle", timeout=15000)
            await asyncio.sleep(1)

            # Check if we see a sign-in page or redirect
            current_url = self.page.url

            # If URL contains accounts.google.com, we're not logged in
            if 'accounts.google.com' in current_url:
                return False

            # If we can see the Docs interface, we're logged in
            # Look for common Docs UI elements
            try:
                await self.page.wait_for_selector(
                    '[aria-label*="Start a new document"], .docs-homescreen-templates-templateview',
                    timeout=3000
                )
                return True
            except PlaywrightTimeoutError:
                return False

        except Exception:
            return False

    async def _create_blank_document(self) -> bool:
        """
        Navigate to create a new blank document

        Returns:
            True if successful, False otherwise
        """
        try:
            await self.page.goto(self.DOCS_NEW, wait_until="networkidle", timeout=30000)

            # Wait for editor to be visible
            await self.page.wait_for_selector(
                self.SELECTORS['editor_canvas'],
                state="visible",
                timeout=10000
            )

            # Click into editor to focus
            editor = self.page.locator(self.SELECTORS['editor_canvas'])
            await editor.click()
            await asyncio.sleep(0.3)

            return True

        except PlaywrightTimeoutError:
            return False
        except Exception:
            return False

    async def _set_document_title(self, title: str):
        """
        Set the document title

        Args:
            title: Document title to set
        """
        try:
            # Click on title input
            title_input = self.page.locator(self.SELECTORS['title_input'])
            await title_input.click()
            await asyncio.sleep(0.2)

            # Clear existing title
            await self.page.keyboard.press('Control+a')
            await asyncio.sleep(0.1)

            # Type new title
            await self.page.keyboard.type(title, delay=20)
            await asyncio.sleep(0.2)

            # Click back into editor
            editor = self.page.locator(self.SELECTORS['editor_canvas'])
            await editor.click()
            await asyncio.sleep(0.2)

        except Exception as e:
            # Title setting is non-critical, log but don't fail
            print(f"Warning: Could not set document title: {str(e)}")

    async def _add_content(self, content: str):
        """
        Add formatted content to the document

        Args:
            content: Content string with markdown-like formatting
        """
        # Split content into lines
        lines = content.split('\n')

        for i, line in enumerate(lines):
            if line.strip():  # Skip empty lines
                await self._add_formatted_line(line)

            # Add newline between lines (except for last line)
            if i < len(lines) - 1:
                await self.page.keyboard.press('Enter')
                await asyncio.sleep(0.05)

    async def _add_formatted_line(self, line: str):
        """
        Add a single formatted line to the document

        Args:
            line: Line of text with possible formatting
        """
        # Check for header formatting (# Header)
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if header_match:
            level = len(header_match.group(1))
            text = header_match.group(2)
            await self.apply_format(self.page, f'h{level}')
            await self._type_text_with_inline_formatting(text)
            await self.apply_format(self.page, 'normal')
            return

        # Check for bullet list (- Item)
        if re.match(r'^-\s+', line):
            text = re.sub(r'^-\s+', '', line)
            await self.apply_format(self.page, 'bullet_list')
            await self._type_text_with_inline_formatting(text)
            return

        # Check for numbered list (1. Item)
        if re.match(r'^\d+\.\s+', line):
            text = re.sub(r'^\d+\.\s+', '', line)
            await self.apply_format(self.page, 'numbered_list')
            await self._type_text_with_inline_formatting(text)
            return

        # Plain text with inline formatting
        await self._type_text_with_inline_formatting(line)

    async def _type_text_with_inline_formatting(self, text: str):
        """
        Type text with inline formatting like **bold**, *italic*, [link](url)

        Args:
            text: Text with inline markdown formatting
        """
        # Pattern to match **bold**, *italic*, and [text](url)
        pattern = r'(\*\*.*?\*\*|\*.*?\*|\[.*?\]\(.*?\))'
        parts = re.split(pattern, text)

        for part in parts:
            if not part:
                continue

            # Bold: **text**
            if part.startswith('**') and part.endswith('**'):
                plain_text = part[2:-2]
                await self.apply_format(self.page, 'bold')
                await self.page.keyboard.type(plain_text, delay=10)
                await self.apply_format(self.page, 'bold')  # Toggle off

            # Italic: *text*
            elif part.startswith('*') and part.endswith('*') and not part.startswith('**'):
                plain_text = part[1:-1]
                await self.apply_format(self.page, 'italic')
                await self.page.keyboard.type(plain_text, delay=10)
                await self.apply_format(self.page, 'italic')  # Toggle off

            # Link: [text](url)
            elif part.startswith('[') and '](' in part and part.endswith(')'):
                link_match = re.match(r'\[(.*?)\]\((.*?)\)', part)
                if link_match:
                    link_text = link_match.group(1)
                    link_url = link_match.group(2)

                    # Type the link text first
                    await self.page.keyboard.type(link_text, delay=10)
                    await asyncio.sleep(0.1)

                    # Select the text
                    for _ in range(len(link_text)):
                        await self.page.keyboard.press('Shift+ArrowLeft')
                    await asyncio.sleep(0.1)

                    # Open link dialog (Ctrl+K)
                    await self.apply_format(self.page, 'link')
                    await asyncio.sleep(0.3)

                    # Type URL
                    await self.page.keyboard.type(link_url, delay=10)
                    await asyncio.sleep(0.1)

                    # Press Enter to confirm
                    await self.page.keyboard.press('Enter')
                    await asyncio.sleep(0.2)

            # Plain text
            else:
                await self.page.keyboard.type(part, delay=10)

    async def _wait_for_save_and_get_url(self, timeout: int = 10000) -> str:
        """
        Wait for document to save and return the URL

        Args:
            timeout: Maximum time to wait in milliseconds

        Returns:
            Document URL
        """
        try:
            # Wait for save indicator to show "Saved to Drive" or similar
            save_indicator = self.page.locator(self.SELECTORS['save_status'])

            # Wait up to timeout for save to complete
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) * 1000 < timeout:
                try:
                    text = await save_indicator.text_content(timeout=1000)
                    if text and ('Saved' in text or 'All changes saved' in text):
                        break
                except:
                    pass
                await asyncio.sleep(0.5)

            # Return current URL
            return self.page.url

        except Exception:
            # If we can't verify save, just return the current URL
            return self.page.url

    async def _get_document_title(self) -> str:
        """
        Get the current document title

        Returns:
            Document title or "Untitled document" if not found
        """
        try:
            title_input = self.page.locator(self.SELECTORS['title_input'])
            title = await title_input.input_value(timeout=3000)
            return title if title else "Untitled document"
        except:
            return "Untitled document"


# Convenience functions for easy usage

async def create_google_doc(
    page: Page,
    title: str,
    content: str = ""
) -> DocCreateResult:
    """
    Convenience function to create a Google Doc

    Args:
        page: Playwright page object
        title: Document title
        content: Document content with markdown-like formatting

    Returns:
        DocCreateResult with success status and document URL

    Example:
        result = await create_google_doc(
            page=page,
            title="Meeting Notes",
            content="# Agenda\n\n- Item 1\n- Item 2"
        )
        if result.success:
            print(f"Created: {result.url}")
    """
    integration = GoogleDocsIntegration(page)
    return await integration.create_document(title, content)


async def open_google_doc(page: Page, url: str) -> DocOpenResult:
    """
    Convenience function to open a Google Doc

    Args:
        page: Playwright page object
        url: Full URL to the Google Doc

    Returns:
        DocOpenResult with success status and document title

    Example:
        result = await open_google_doc(
            page=page,
            url="https://docs.google.com/document/d/..."
        )
        if result.success:
            print(f"Opened: {result.title}")
    """
    integration = GoogleDocsIntegration(page)
    return await integration.open_document(url)


async def append_to_google_doc(
    page: Page,
    content: str,
    url: Optional[str] = None
) -> DocCreateResult:
    """
    Convenience function to append content to a Google Doc

    Args:
        page: Playwright page object
        content: Content to append
        url: Optional URL to open first

    Returns:
        DocCreateResult with success status

    Example:
        result = await append_to_google_doc(
            page=page,
            content="## New Section\n\nAdditional notes",
            url="https://docs.google.com/document/d/..."
        )
    """
    integration = GoogleDocsIntegration(page)
    return await integration.append_to_document(content, url)


async def find_and_replace_in_doc(
    page: Page,
    find_text: str,
    replace_text: str,
    url: Optional[str] = None
) -> DocCreateResult:
    """
    Convenience function to find and replace text in a Google Doc

    Args:
        page: Playwright page object
        find_text: Text to find
        replace_text: Text to replace with
        url: Optional URL to open first

    Returns:
        DocCreateResult with success status

    Example:
        result = await find_and_replace_in_doc(
            page=page,
            find_text="TODO",
            replace_text="DONE",
            url="https://docs.google.com/document/d/..."
        )
    """
    integration = GoogleDocsIntegration(page)
    return await integration.find_and_replace(find_text, replace_text, url)
