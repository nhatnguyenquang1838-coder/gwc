"""Fail-closed validation for additive Q0 browser conversation bindings."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

HISTORICAL_RECEIPT_NAME = 'browser-report39-039e1f6-delivery.json'


class BrowserBindingError(ValueError):
    """A browser binding failed its stable validation contract."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def current_binding_path(home, run_id) -> Path:
    return Path(home) / 'loop-checkpoints' / run_id / 'browser-bindings' / 'current.json'


def _historical_project(url):
    try:
        path = urlsplit(url).path
    except (TypeError, ValueError):
        return None
    if '/c/' not in path:
        return None
    return path.split('/c/', 1)[0]


def validate_binding_chain(historical: dict, current: dict | None, *, run_id, session_id, controller_url) -> dict:
    if not isinstance(historical, dict):
        raise BrowserBindingError('HISTORICAL_RECEIPT_INVALID')
    if historical.get('run_id') != run_id:
        raise BrowserBindingError('BINDING_RUN_MISMATCH')
    if historical.get('session_id') != session_id:
        raise BrowserBindingError('BINDING_SESSION_MISMATCH')
    if historical.get('send_outcome') != 'SENT_VERIFIED':
        raise BrowserBindingError('HISTORICAL_RECEIPT_INVALID')
    old_url = historical.get('conversation_url')
    if not isinstance(old_url, str) or not old_url:
        raise BrowserBindingError('HISTORICAL_RECEIPT_INVALID')

    if current is None:
        if old_url != controller_url:
            raise BrowserBindingError('CURRENT_BINDING_MISSING')
        return {'mode': 'LEGACY', 'conversation_url': old_url}
    if not isinstance(current, dict):
        raise BrowserBindingError('HISTORICAL_RECEIPT_INVALID')
    if current.get('run_id') != run_id:
        raise BrowserBindingError('BINDING_RUN_MISMATCH')
    if current.get('session_id') != session_id:
        raise BrowserBindingError('BINDING_SESSION_MISMATCH')
    if current.get('conversation_url') != controller_url:
        raise BrowserBindingError('BINDING_URL_MISMATCH')
    if _historical_project(old_url) is None or _historical_project(old_url) != _historical_project(controller_url):
        raise BrowserBindingError('BINDING_PROJECT_MISMATCH')

    marker = current.get('marker')
    if not isinstance(marker, str) or not marker.strip():
        raise BrowserBindingError('BINDING_MARKER_MISSING')
    if marker == historical.get('marker'):
        raise BrowserBindingError('BINDING_MARKER_REUSED')
    if not isinstance(current.get('report_ref'), str) or not current['report_ref'].strip():
        raise BrowserBindingError('BINDING_REPORT_REF_MISSING')
    if current.get('in_app_delivered') is not True or current.get('user_turn_observed') is not True:
        raise BrowserBindingError('BINDING_NOT_DELIVERED')
    if not isinstance(current.get('previous_receipt_path'), str) or not current['previous_receipt_path'].strip():
        raise BrowserBindingError('BINDING_PARENT_DIGEST_MISMATCH')

    expected_digest = historical.get('_receipt_sha256')
    if expected_digest is None:
        expected_digest = hashlib.sha256(json.dumps(historical, sort_keys=True).encode()).hexdigest()
    if current.get('previous_receipt_sha256') != expected_digest:
        raise BrowserBindingError('BINDING_PARENT_DIGEST_MISMATCH')
    return {'mode': 'CHAINED', 'marker': marker, 'conversation_url': controller_url}


def resolve_binding(home, *, run_id, session_id, controller_url) -> dict:
    root = Path(home) / 'loop-checkpoints' / run_id
    receipt_path = root / HISTORICAL_RECEIPT_NAME
    try:
        receipt_bytes = receipt_path.read_bytes()
        historical = json.loads(receipt_bytes)
    except (OSError, ValueError, TypeError):
        raise BrowserBindingError('HISTORICAL_RECEIPT_INVALID') from None
    if not isinstance(historical, dict):
        raise BrowserBindingError('HISTORICAL_RECEIPT_INVALID')
    historical = dict(historical)
    historical['_receipt_sha256'] = hashlib.sha256(receipt_bytes).hexdigest()
    binding_path = current_binding_path(home, run_id)
    try:
        current = json.loads(binding_path.read_bytes())
    except FileNotFoundError:
        current = None
    except (OSError, ValueError, TypeError):
        raise BrowserBindingError('HISTORICAL_RECEIPT_INVALID') from None
    return validate_binding_chain(historical, current, run_id=run_id,
                                  session_id=session_id, controller_url=controller_url)
