#!/usr/bin/env python3
"""Markdown scanner for check_sync.py: sections and pipe table parsing."""
import re
import sys

sys.dont_write_bytecode = True


class SectionList(list):
    """List of section dicts with helper lookup by heading name."""

    def get(self, name: str, default=None):
        target = name.strip().lower()
        for s in self:
            if s["heading"].strip().lower() == target:
                return s["lines"]
        return default

    def __getitem__(self, item):
        if isinstance(item, str):
            res = self.get(item)
            if res is None:
                raise KeyError(item)
            return res
        return super().__getitem__(item)


def sections(text: str) -> SectionList:
    """Return headings with their lines, ignoring headings inside fenced code (``` and ~~~).

    Handles CRLF, trailing spaces, and heading levels 1 to 6.
    """
    clean_text = text.replace("\r\n", "\n")
    lines = clean_text.splitlines()

    result = SectionList()
    in_fence = False
    fence_char = ""
    fence_len = 0

    current_heading = ""
    current_level = 0
    current_lines = []

    heading_pat = re.compile(r"^(#{1,6})\s+(.*?)\s*$")

    def flush_section():
        nonlocal current_heading, current_level, current_lines
        if current_heading or current_lines:
            result.append({
                "heading": current_heading,
                "level": current_level,
                "lines": current_lines
            })
            current_lines = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        # Check code block fences (``` or ~~~)
        if not in_fence:
            m_fence = re.match(r"^(`{3,}|~{3,})", stripped)
            if m_fence:
                in_fence = True
                fence_str = m_fence.group(1)
                fence_char = fence_str[0]
                fence_len = len(fence_str)
                current_lines.append(line)
                continue
        else:
            if stripped.startswith(fence_char * fence_len):
                rest = stripped[fence_len:].strip()
                if not rest:
                    in_fence = False
            current_lines.append(line)
            continue

        # Outside fences: check heading levels 1 to 6
        m_head = heading_pat.match(stripped)
        if m_head:
            flush_section()
            current_level = len(m_head.group(1))
            current_heading = m_head.group(2).strip()
        else:
            current_lines.append(line)

    flush_section()
    return result


def table_rows(lines: list) -> list:
    """Return pipe table cells from lines.

    Skips separator rows (e.g. |---|---|).
    Ignores rows inside fenced code blocks (``` and ~~~).
    Handles CRLF and trailing spaces.
    """
    rows = []
    separator_pat = re.compile(r"^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$")
    in_fence = False
    fence_char = ""
    fence_len = 0

    for raw_line in lines:
        line = raw_line.replace("\r\n", "\n").rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        if not in_fence:
            m_fence = re.match(r"^(`{3,}|~{3,})", stripped)
            if m_fence:
                in_fence = True
                fence_str = m_fence.group(1)
                fence_char = fence_str[0]
                fence_len = len(fence_str)
                continue
        else:
            if stripped.startswith(fence_char * fence_len):
                rest = stripped[fence_len:].strip()
                if not rest:
                    in_fence = False
            continue

        if "|" not in stripped:
            continue
        if separator_pat.match(stripped):
            continue

        trimmed = stripped
        if trimmed.startswith("|"):
            trimmed = trimmed[1:]
        if trimmed.endswith("|"):
            trimmed = trimmed[:-1]

        cells = [c.strip() for c in trimmed.split("|")]
        rows.append(cells)

    return rows


def tables(lines: list) -> list:
    """Group lines into separate tables, ignoring lines inside code fences.

    Returns list of tables, where each table is a list of rows (cells).
    """
    all_tables = []
    current_table_lines = []
    in_fence = False
    fence_char = ""
    fence_len = 0

    for raw_line in lines:
        line = raw_line.replace("\r\n", "\n").rstrip()
        stripped = line.strip()
        if not stripped:
            if current_table_lines:
                rows = table_rows(current_table_lines)
                if rows:
                    all_tables.append(rows)
                current_table_lines = []
            continue

        if not in_fence:
            m_fence = re.match(r"^(`{3,}|~{3,})", stripped)
            if m_fence:
                in_fence = True
                fence_str = m_fence.group(1)
                fence_char = fence_str[0]
                fence_len = len(fence_str)
                if current_table_lines:
                    rows = table_rows(current_table_lines)
                    if rows:
                        all_tables.append(rows)
                    current_table_lines = []
                continue
        else:
            if stripped.startswith(fence_char * fence_len):
                rest = stripped[fence_len:].strip()
                if not rest:
                    in_fence = False
            continue

        if "|" in stripped:
            current_table_lines.append(raw_line)
        else:
            if current_table_lines:
                rows = table_rows(current_table_lines)
                if rows:
                    all_tables.append(rows)
                current_table_lines = []

    if current_table_lines:
        rows = table_rows(current_table_lines)
        if rows:
            all_tables.append(rows)

    return all_tables
