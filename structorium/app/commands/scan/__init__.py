"""Scan command package with lazy command export to avoid import cycles."""

from __future__ import annotations


def __getattr__(name: str):
    if name == "cmd_scan":
        from .scan import cmd_scan

        return cmd_scan
    raise AttributeError(name)

__all__ = ["cmd_scan"]
