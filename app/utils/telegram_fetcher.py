"""
Public Telegram channel message scraper.
Uses https://t.me/s/{channel} web preview (no bot token required).
"""
import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List


@dataclass
class TelegramMessage:
    id: int
    text: str
    url: str


def _parse_channel_username(channel_url: str) -> str:
    """Extract username from https://t.me/channelname or @channelname."""
    url = channel_url.strip().rstrip('/')
    if url.startswith('@'):
        return url[1:]
    if 't.me/' in url:
        parts = url.split('t.me/')
        return parts[-1].split('/')[0]
    return url


def _parse_message_id(message_url: str) -> int:
    """Extract message ID from https://t.me/channelname/123."""
    try:
        return int(message_url.strip().rstrip('/').split('/')[-1])
    except (ValueError, IndexError):
        return 0


async def fetch_new_messages(channel_username: str, after_id: int) -> List[TelegramMessage]:
    """
    Fetch messages from a public Telegram channel newer than after_id.
    Returns up to ~40 newest messages that haven't been processed yet.
    """
    messages: List[TelegramMessage] = []

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        # Collect from latest page, then go back if needed
        next_before: int | None = None

        for _ in range(5):  # max 5 pages = ~100 messages
            url = f"https://t.me/s/{channel_username}"
            if next_before:
                url += f"?before={next_before}"

            try:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; EduHubBot/1.0)"
                })
                resp.raise_for_status()
            except httpx.HTTPError:
                break

            soup = BeautifulSoup(resp.text, 'lxml')
            posts = soup.select('.tgme_widget_message')

            if not posts:
                break

            page_messages: List[TelegramMessage] = []
            oldest_id_on_page = None

            for post in posts:
                data_post = post.get('data-post', '')
                if '/' not in data_post:
                    continue
                try:
                    msg_id = int(data_post.split('/')[-1])
                except ValueError:
                    continue

                if oldest_id_on_page is None or msg_id < oldest_id_on_page:
                    oldest_id_on_page = msg_id

                if msg_id <= after_id:
                    continue

                text_el = post.select_one('.tgme_widget_message_text')
                text = text_el.get_text('\n', strip=True) if text_el else ''
                if not text.strip():
                    continue

                msg_url = f"https://t.me/{channel_username}/{msg_id}"
                page_messages.append(TelegramMessage(id=msg_id, text=text, url=msg_url))

            messages.extend(page_messages)

            # If oldest message on this page is already processed, stop
            if oldest_id_on_page is not None and oldest_id_on_page <= after_id:
                break

            # Need to go further back
            if oldest_id_on_page is not None:
                next_before = oldest_id_on_page
            else:
                break

    # Sort by ID ascending (oldest first)
    return sorted(messages, key=lambda m: m.id)
