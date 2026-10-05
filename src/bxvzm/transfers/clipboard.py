"""Read one Amazon link only when the user requests a clipboard handoff."""

import os

from bxvzm.transfers.links import ProviderLink, validate_provider_url


def copied_amazon_link() -> ProviderLink:
    if os.name != "nt":
        raise ValueError("Clipboard reading needs native Windows. Paste the Amazon link instead.")
    import pywintypes
    import win32clipboard

    try:
        win32clipboard.OpenClipboard()
        try:
            if not win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                raise ValueError("Copy an Amazon Music album or track link first")
            value = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
    except pywintypes.error as error:
        raise ValueError("Clipboard is busy. Copy the Amazon link and try again.") from error
    if not isinstance(value, str):
        raise ValueError("Copy an Amazon Music album or track link first")
    link = validate_provider_url(value)
    if link.provider != "Amazon Music":
        raise ValueError("Copy an Amazon Music link; a different provider was copied")
    return link
