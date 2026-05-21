"""
notion_db.py — Notion database query + page update helpers.

Used by sync_worker.py to read the Financial Updates DB and write back
status flags after processing each row.
"""

import os
import requests

from lib.notion_writer import NOTION_VERSION, notion_headers


FINANCIAL_UPDATES_DS_ID = '2f1334f8-c046-4e10-b770-77816e602fca'
FINANCIAL_UPDATES_DB_ID = 'a863ed07-0e62-4419-b8a2-e2c0dc17c596'


# ── Query helpers ────────────────────────────────────────────────────────────

def query_database(database_id, filter_=None, sorts=None, headers=None):
    """Query a Notion database. Returns list of page objects.

    filter_: Notion filter object (or None for all rows)
    sorts:   list of sort objects (or None for default)
    """
    headers = headers or notion_headers()
    results = []
    payload = {}
    if filter_:
        payload['filter'] = filter_
    if sorts:
        payload['sorts'] = sorts

    while True:
        resp = requests.post(
            f'https://api.notion.com/v1/databases/{database_id}/query',
            headers=headers,
            json=payload,
            timeout=30,
        )
        if resp.status_code >= 300:
            print(f"  ⚠ Notion query failed ({resp.status_code}): {resp.text[:300]}")
            return results

        data = resp.json()
        results.extend(data.get('results', []))

        if not data.get('has_more'):
            break
        payload['start_cursor'] = data['next_cursor']

    return results


def fetch_unsynced_financial_updates(headers=None):
    """Fetch Financial Updates rows where Status=confirmed AND Sheets Written=false."""
    filter_ = {
        'and': [
            {'property': 'Status',         'select':   {'equals': 'confirmed'}},
            {'property': 'Sheets Written', 'checkbox': {'equals': False}},
        ],
    }
    sorts = [{'property': 'Event Date', 'direction': 'ascending'}]
    return query_database(FINANCIAL_UPDATES_DB_ID, filter_=filter_, sorts=sorts, headers=headers)


# ── Property extraction (from Notion API response shape) ─────────────────────

def get_prop(page, name, kind=None):
    """Extract a property value from a Notion page object.

    page['properties'][name] structure varies by type:
      title         → list of rich_text → join text
      rich_text     → list of rich_text → join text
      select        → {name: 'value'} or None
      number        → number or None
      date          → {start: 'YYYY-MM-DD', end: ..., ...} or None
      checkbox      → bool
    """
    prop = page.get('properties', {}).get(name)
    if not prop:
        return None
    t = prop.get('type')

    if t in ('title', 'rich_text'):
        parts = prop.get(t, [])
        return ''.join(p.get('plain_text', '') for p in parts) or None
    if t == 'select':
        sel = prop.get('select')
        return sel.get('name') if sel else None
    if t == 'number':
        return prop.get('number')
    if t == 'date':
        d = prop.get('date')
        return d.get('start') if d else None
    if t == 'checkbox':
        return bool(prop.get('checkbox'))
    return None


def extract_financial_update(page):
    """Return a dict of Financial Updates row values for one Notion page object."""
    return {
        'id':               page.get('id'),
        'url':              page.get('url'),
        'title':            get_prop(page, 'Title'),
        'type':             get_prop(page, 'Type'),
        'domain':           get_prop(page, 'Domain'),
        'account':          get_prop(page, 'Account'),
        'from_account':     get_prop(page, 'From Account'),
        'to_account':       get_prop(page, 'To Account'),
        'new_balance':      get_prop(page, 'New Balance'),
        'amount':           get_prop(page, 'Amount'),
        'ticker':           get_prop(page, 'Ticker'),
        'qty':              get_prop(page, 'Qty'),
        'price':            get_prop(page, 'Price'),
        'event_date':       get_prop(page, 'Event Date'),
        'notes':            get_prop(page, 'Notes'),
        'source':           get_prop(page, 'Source'),
        'status':           get_prop(page, 'Status'),
        'sheets_written':   get_prop(page, 'Sheets Written'),
        'supabase_written': get_prop(page, 'Supabase Written'),
    }


# ── Page update helpers ──────────────────────────────────────────────────────

def update_page_properties(page_id, properties, headers=None):
    """PATCH a Notion page's properties. `properties` is a dict in Notion's wire format."""
    headers = headers or notion_headers()
    resp = requests.patch(
        f'https://api.notion.com/v1/pages/{page_id}',
        headers=headers,
        json={'properties': properties},
        timeout=30,
    )
    if resp.status_code >= 300:
        print(f"  ⚠ Notion page update failed ({resp.status_code}): {resp.text[:300]}")
        return False
    return True


def prop_select(value):
    return {'select': {'name': value}} if value else {'select': None}


def prop_checkbox(value):
    return {'checkbox': bool(value)}


def prop_date(iso_date):
    return {'date': {'start': iso_date}} if iso_date else {'date': None}


def prop_text(value):
    return {'rich_text': [{'type': 'text', 'text': {'content': str(value)}}]} if value else {'rich_text': []}


def mark_row_synced(page_id, headers=None):
    """Mark a Financial Updates row as fully synced — sets all flags + Status."""
    import datetime
    today = datetime.date.today().isoformat()
    return update_page_properties(page_id, {
        'Status':           prop_select('synced'),
        'Sheets Written':   prop_checkbox(True),
        'Supabase Written': prop_checkbox(True),
        'Synced At':        prop_date(today),
    }, headers=headers)


def mark_row_failed(page_id, error_msg, headers=None):
    """Mark a Financial Updates row as failed and append error to Notes."""
    return update_page_properties(page_id, {
        'Status': prop_select('failed'),
        'Notes':  prop_text(f'sync_worker error: {error_msg}'),
    }, headers=headers)


def mark_sheets_written(page_id, headers=None):
    return update_page_properties(page_id, {
        'Sheets Written': prop_checkbox(True),
    }, headers=headers)


def mark_supabase_written(page_id, headers=None):
    return update_page_properties(page_id, {
        'Supabase Written': prop_checkbox(True),
    }, headers=headers)
