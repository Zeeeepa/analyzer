"""
User-friendly error messages for Eversale.
Translates technical errors into helpful guidance.
"""

from typing import Tuple


def friendly_error(error: Exception) -> Tuple[str, str]:
    """
    Convert technical error to user-friendly message.

    Returns:
        (title, message) tuple for display
    """
    error_str = str(error).lower()
    error_type = type(error).__name__

    # Connection errors
    if "connection refused" in error_str or "connect" in error_str:
        if "11434" in error_str or "ollama" in error_str:
            return (
                "Ollama Not Running",
                "The AI engine isn't running.\n\nStart it with: ollama serve"
            )
        if "playwright" in error_str or "browser" in error_str:
            return (
                "Browser Connection Failed",
                "Couldn't connect to browser.\n\nTry: playwright install chromium"
            )
        return (
            "Connection Failed",
            "Couldn't connect to a required service.\n\nCheck that all services are running."
        )

    # Timeout errors
    if "timeout" in error_str or "timed out" in error_str:
        return (
            "Request Timed Out",
            "The operation took too long.\n\nThis might be due to:\n- Slow network\n- Page not loading\n- Service being busy\n\nTry again or simplify your request."
        )

    # Login/auth errors
    if "sign in" in error_str or "login" in error_str or "auth" in error_str:
        return (
            "Login Required",
            "You need to be logged in for this.\n\nUse: login <service>\nExample: login gmail"
        )

    # Browser errors
    if "element not found" in error_str or "no such element" in error_str:
        return (
            "Element Not Found",
            "Couldn't find the expected element on the page.\n\nThe page might have changed or loaded differently.\nTry again or try a different approach."
        )

    if "navigation" in error_str:
        return (
            "Navigation Failed",
            "Couldn't load the page.\n\nCheck if the URL is correct and accessible."
        )

    # Network errors
    if "network" in error_str or "dns" in error_str:
        return (
            "Network Error",
            "Network connection issue.\n\nCheck your internet connection."
        )

    # File errors
    if "permission denied" in error_str:
        return (
            "Permission Denied",
            "Can't access this file or folder.\n\nCheck file permissions."
        )

    if "no such file" in error_str or "file not found" in error_str:
        return (
            "File Not Found",
            "The requested file doesn't exist.\n\nCheck the path and try again."
        )

    # Model errors
    if "model" in error_str and ("not found" in error_str or "pull" in error_str):
        return (
            "Model Not Available",
            "The AI model isn't installed.\n\nTry: ollama pull llama3.1:8b-instruct-q8_0"
        )

    # Rate limiting
    if "rate limit" in error_str or "too many requests" in error_str:
        return (
            "Rate Limited",
            "Too many requests. Please wait a moment and try again."
        )

    # Blocked/CAPTCHA
    if "captcha" in error_str or "blocked" in error_str or "cloudflare" in error_str:
        return (
            "Access Blocked",
            "The site is blocking automated access.\n\nTry:\n- Using 'show browser' to login manually\n- Waiting a few minutes\n- Using a different approach"
        )

    # Memory/resource errors
    if "memory" in error_str or "out of memory" in error_str:
        return (
            "Out of Memory",
            "Not enough memory for this operation.\n\nTry closing other applications."
        )

    # Generic fallback
    if error_type == "KeyboardInterrupt":
        return (
            "Interrupted",
            "Operation cancelled."
        )

    # Unknown error - show technical details but friendly wrapper
    return (
        "Something Went Wrong",
        f"An error occurred: {str(error)[:200]}\n\nCheck logs/eversale.log for details."
    )


def format_error_for_display(error: Exception) -> str:
    """Format error for CLI display."""
    title, message = friendly_error(error)
    return f"{title}\n\n{message}"
