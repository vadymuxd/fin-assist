"""
notion_writer.py — Shared Notion REST API writers for the 3 Context pages.

Used by:
  • sheets_updater.py  → Investments Context (page 33f416f2-7566-81ce-b7e8-dd7b68101342)
  • snapshot_worker.py → Savings Context    (page 34d416f2-7566-81b6-b236-de36e284f4b1)
                       → Pensions Context   (page 34f416f2-7566-8144-8054-e371f2d6e569)

Each page is fully rebuilt: existing blocks are archived, then new blocks are
PATCHed into the page. No incremental updates — keeps the pages clean.

Block builders (`paragraph`, `heading2`, `divider`, `table`) return Notion block
JSON. Compose them into a `blocks` list, then call `rebuild_page(page_id, blocks)`.
"""

import os
import time
import requests


NOTION_VERSION = '2022-06-28'

# Standard context page IDs — single source of truth so callers don't hardcode
INVESTMENTS_CONTEXT_ID = '33f416f2-7566-81ce-b7e8-dd7b68101342'
SAVINGS_CONTEXT_ID     = '34d416f2-7566-81b6-b236-de36e284f4b1'
PENSIONS_CONTEXT_ID    = '34f416f2-7566-8144-8054-e371f2d6e569'


# ── Headers ──────────────────────────────────────────────────────────────────

def notion_headers(key=None):
    """Build standard Notion API headers. Reads NOTION_API_KEY env if key omitted."""
    key = key or os.getenv('NOTION_API_KEY', '')
    return {
        'Authorization': f'Bearer {key}',
        'Notion-Version': NOTION_VERSION,
        'Content-Type':   'application/json',
    }


# ── Rich text + block builders ───────────────────────────────────────────────

def rt(text, bold=False):
    """Build a Notion rich_text object."""
    obj = {'type': 'text', 'text': {'content': str(text)}}
    if bold:
        obj['annotations'] = {'bold': True}
    return obj


def paragraph(text, bold=False):
    return {'object': 'block', 'type': 'paragraph',
            'paragraph': {'rich_text': [rt(text, bold)]}}


def heading2(text):
    return {'object': 'block', 'type': 'heading_2',
            'heading_2': {'rich_text': [rt(text)]}}


def divider():
    return {'object': 'block', 'type': 'divider', 'divider': {}}


def table(rows, has_column_header=True):
    """Build a Notion table block. First row is treated as the header if has_column_header."""
    table_rows = [
        {'object': 'block', 'type': 'table_row',
         'table_row': {'cells': [[rt(cell)] for cell in row]}}
        for row in rows
    ]
    return {
        'object': 'block',
        'type': 'table',
        'table': {
            'table_width':       len(rows[0]) if rows else 0,
            'has_column_header': has_column_header,
            'has_row_header':    False,
            'children':          table_rows,
        },
    }


# ── Page rebuild ─────────────────────────────────────────────────────────────

def archive_page_blocks(page_id, headers=None):
    """Delete all top-level blocks from a Notion page (idempotent)."""
    headers = headers or notion_headers()
    resp = requests.get(
        f'https://api.notion.com/v1/blocks/{page_id}/children',
        headers=headers, timeout=30,
    )
    if resp.status_code != 200:
        print(f"  Could not fetch page blocks: {resp.text[:200]}")
        return
    for block in resp.json().get('results', []):
        for attempt in range(3):
            try:
                requests.patch(
                    f'https://api.notion.com/v1/blocks/{block["id"]}',
                    headers=headers,
                    json={'archived': True},
                    timeout=30,
                )
                break
            except requests.exceptions.Timeout:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)


def rebuild_page(page_id, blocks, headers=None):
    """Archive existing blocks, then PATCH new blocks. Returns True on success."""
    headers = headers or notion_headers()
    if not headers.get('Authorization', '').replace('Bearer ', '').strip():
        print("  NOTION_API_KEY not set — skipping page rebuild")
        return False

    print(f"  Archiving existing blocks on {page_id}...")
    archive_page_blocks(page_id, headers)

    print(f"  Writing {len(blocks)} new blocks...")
    resp = requests.patch(
        f'https://api.notion.com/v1/blocks/{page_id}/children',
        headers=headers,
        json={'children': blocks},
        timeout=30,
    )
    if resp.status_code >= 300:
        print(f"  ⚠ Notion write failed ({resp.status_code}): {resp.text[:300]}")
        return False
    return True


# ── Convenience: standard page header ────────────────────────────────────────

def standard_header(script_name, run_time, source_of_truth):
    """Build the standard header used at the top of every Context page.

    Returns a list of blocks: timestamp line + source line + divider.
    """
    return [
        paragraph(f'⚠️ Auto-updated by {script_name} — {run_time}'),
        paragraph(f'Source of truth: {source_of_truth}'),
        divider(),
    ]
