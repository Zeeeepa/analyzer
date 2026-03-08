"""
Cross-platform output path detection.
Ensures files land in user's Desktop or Downloads folder.
"""

import os
import platform
from pathlib import Path
from loguru import logger


def get_output_folder() -> Path:
    """
    Get the best output folder for the current OS.

    Priority:
    1. Desktop (most visible)
    2. Downloads (fallback)
    3. Home directory (last resort)

    Works on: Windows, Mac, Linux, WSL
    """

    system = platform.system()
    home = Path.home()

    # Check if running in WSL (can access Windows folders)
    is_wsl = "microsoft" in platform.uname().release.lower() if hasattr(platform.uname(), 'release') else False

    # Try Desktop first (most visible to user)
    desktop_paths = []

    if system == "Windows":
        # Windows Desktop locations
        desktop_paths = [
            home / "Desktop",
            home / "OneDrive" / "Desktop",  # OneDrive sync
            Path(os.environ.get("USERPROFILE", "")) / "Desktop",
        ]
    elif system == "Darwin":  # macOS
        desktop_paths = [
            home / "Desktop",
        ]
    else:  # Linux / WSL
        desktop_paths = [
            home / "Desktop",
            home / "desktop",  # Some distros use lowercase
        ]
        # WSL: also check Windows user folders
        if is_wsl:
            # Try common Windows user paths via /mnt/c
            for user in ["Owner", "User", os.environ.get("USER", "")]:
                desktop_paths.extend([
                    Path(f"/mnt/c/Users/{user}/Desktop"),
                    Path(f"/mnt/c/Users/{user}/OneDrive/Desktop"),
                ])

    # Check Desktop paths
    for desktop in desktop_paths:
        if desktop.exists() and desktop.is_dir():
            output = desktop / "AI_Agent_Output"
            output.mkdir(exist_ok=True)
            logger.info(f"Output folder: {output}")
            return output

    # Fallback to Downloads
    downloads_paths = []

    if system == "Windows":
        downloads_paths = [
            home / "Downloads",
            Path(os.environ.get("USERPROFILE", "")) / "Downloads",
        ]
    elif system == "Darwin":
        downloads_paths = [
            home / "Downloads",
        ]
    else:
        downloads_paths = [
            home / "Downloads",
            home / "downloads",
        ]
        # WSL: also check Windows Downloads
        if is_wsl:
            for user in ["Owner", "User", os.environ.get("USER", "")]:
                downloads_paths.append(Path(f"/mnt/c/Users/{user}/Downloads"))

    for downloads in downloads_paths:
        if downloads.exists() and downloads.is_dir():
            output = downloads / "AI_Agent_Output"
            output.mkdir(exist_ok=True)
            logger.info(f"Output folder: {output}")
            return output

    # Last resort: home directory
    output = home / "AI_Agent_Output"
    output.mkdir(exist_ok=True)
    logger.info(f"Output folder (fallback): {output}")
    return output


def get_output_path(filename: str) -> Path:
    """
    Get full path for an output file.

    Args:
        filename: Name of the file (e.g., "leads.csv")

    Returns:
        Full path in the output folder
    """
    folder = get_output_folder()
    return folder / filename


def save_output(filename: str, content: str) -> Path:
    """
    Save content to output folder.

    Args:
        filename: Name of the file
        content: Content to write

    Returns:
        Path where file was saved
    """
    path = get_output_path(filename)
    path.write_text(content, encoding='utf-8')
    logger.info(f"Saved: {path}")
    return path


def save_csv(filename: str, rows: list, headers: list = None, append: bool = False) -> Path:
    """
    Save CSV to output folder with optional append mode.

    Args:
        filename: Name of file (adds .csv if needed)
        rows: List of dicts or lists
        headers: Optional headers (auto-detected from dicts)
        append: If True, append to existing file instead of overwriting

    Returns:
        Path where file was saved
    """
    import csv

    if not filename.endswith('.csv'):
        filename += '.csv'

    path = get_output_path(filename)

    # Check if file exists for append mode
    file_exists = path.exists()
    mode = 'a' if append and file_exists else 'w'
    write_headers = not (append and file_exists)  # Don't write headers when appending to existing file

    # Auto-detect headers from dict rows
    if rows and isinstance(rows[0], dict):
        if not headers:
            headers = list(rows[0].keys())

        with open(path, mode, newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            if write_headers:
                writer.writeheader()
            writer.writerows(rows)
    else:
        with open(path, mode, newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if write_headers and headers:
                writer.writerow(headers)
            writer.writerows(rows)

    action = "Appended to" if (append and file_exists) else "Saved"
    logger.info(f"{action} CSV: {path} ({len(rows)} rows)")
    return path


# Cache the output folder
_output_folder = None

def get_cached_output_folder() -> Path:
    """Get cached output folder (faster after first call)."""
    global _output_folder
    if _output_folder is None:
        _output_folder = get_output_folder()
    return _output_folder


def get_file_location_message(path: Path, row_count: int = 0, appended: bool = False) -> str:
    """
    Get a human-readable message about where a file was saved.

    Args:
        path: Path to the saved file
        row_count: Number of rows saved (optional)
        appended: Whether data was appended vs written new

    Returns:
        User-friendly message about the file location
    """
    action = "Added" if appended else "Saved"
    count_msg = f" ({row_count} rows)" if row_count > 0 else ""

    # Make path more readable for users
    path_str = str(path)

    # Shorten WSL paths for readability
    if "/mnt/c/Users/" in path_str:
        # Convert /mnt/c/Users/Owner/... to C:\Users\Owner\...
        path_str = path_str.replace("/mnt/c/", "C:\\").replace("/", "\\")

    return f"{action}{count_msg} to: {path_str}"


def should_append_to_file(prompt: str) -> bool:
    """
    Detect if user wants to append to existing file rather than overwrite.

    Args:
        prompt: User's prompt text

    Returns:
        True if user wants to append, False otherwise
    """
    prompt_lower = (prompt or "").lower()

    append_patterns = [
        "add more", "add to", "append", "add additional", "keep adding",
        "also find", "also search", "more of", "same file", "add these",
        "add to the file", "add to file", "same csv", "keep searching"
    ]

    return any(pattern in prompt_lower for pattern in append_patterns)


# Note: Output folder location is shown by the UI during startup
# No need to print on import (reduces noise in logs)
