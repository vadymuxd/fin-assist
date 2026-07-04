"""Shared lib package for Fin Assist scripts.

Importing this package patches gspread's HTTPClient to retry on transient
Sheets API errors (429 rate limit, 5xx) instead of crashing the whole
worker. The bot_sync pipeline runs several scripts back-to-back against the
same spreadsheet/user, so it's easy to burst past Google's default 60
requests-per-minute-per-user quota — a short backoff-and-retry clears it
without any change to call sites.
"""

import random
import time

import gspread.http_client
from gspread.exceptions import APIError

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 5


def _patch_gspread_retry():
    original_request = gspread.http_client.HTTPClient.request

    def request_with_retry(self, *args, **kwargs):
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return original_request(self, *args, **kwargs)
            except APIError as e:
                status = e.response.status_code
                if status not in _RETRYABLE_STATUS or attempt == _MAX_ATTEMPTS:
                    raise
                retry_after = e.response.headers.get('Retry-After')
                if retry_after:
                    delay = float(retry_after)
                else:
                    delay = min(2 ** attempt, 30) + random.uniform(0, 1)
                print(f"  ⚠ Sheets API {status} — retrying in {delay:.1f}s "
                      f"(attempt {attempt}/{_MAX_ATTEMPTS})")
                time.sleep(delay)

    gspread.http_client.HTTPClient.request = request_with_retry


_patch_gspread_retry()
