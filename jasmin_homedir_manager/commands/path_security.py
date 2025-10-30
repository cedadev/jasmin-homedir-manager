"""Security utilities for validating paths and usernames."""

import pathlib


def validate_username(username: str) -> bool:
    """
    Validate that username is safe and cannot be used for path traversal.

    Returns True if username is valid, False otherwise.
    """
    if not username:
        return False

    if username in (".", ".."):
        return False

    if "/" in username or "\\" in username:
        return False

    if username.startswith("."):
        return False

    normalized = username.replace("-", "").replace("_", "")
    if not normalized.isalnum():
        return False

    return True


def validate_path_containment(path: pathlib.Path, parent: pathlib.Path) -> bool:
    """
    Validate that resolved path is contained within parent directory.

    Returns True if path is safely contained, False otherwise.
    """
    try:
        resolved_path = path.resolve()
        resolved_parent = parent.resolve()
        return resolved_path.is_relative_to(resolved_parent)
    except (ValueError, OSError):
        return False
