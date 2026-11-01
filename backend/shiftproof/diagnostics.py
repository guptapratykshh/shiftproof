"""Local smoke-test receipts. Reading status never invokes a provider."""
import hashlib
import json
import os
from pathlib import Path
from .config import settings
from .providers import prompt_version
from .models import Extraction


def check_path():
    return Path(os.getenv('PROVIDER_CHECK_PATH', str(Path(__file__).resolve().parents[2] / '.local/provider-checks.json')))


def fingerprint():
    s = settings()
    payload = [s.gemini_model, s.gemini_key, s.gemini_free_tier_confirmed,
               s.gemini_account_tier,s.business_provider_approved,s.gemini_business_terms_confirmed,
               prompt_version(), Extraction.model_json_schema()]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def save_check(receipt):
    path = check_path(); path.parent.mkdir(parents=True, exist_ok=True)
    rows = json.loads(path.read_text()) if path.exists() else []
    rows.append({**receipt, 'configuration_fingerprint': fingerprint()})
    temp = path.with_suffix('.tmp'); temp.write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n')
    temp.chmod(0o600); temp.replace(path)


def last_check():
    s = settings()
    result = {'model': s.gemini_model, 'status': 'not_tested', 'checked_at': None, 'error_category': None}
    if s.provider != 'gemini':
        return result
    try:
        rows = json.loads(check_path().read_text())
        match = next((r for r in reversed(rows) if r['configuration_fingerprint'] == fingerprint()), None)
        if match:
            result.update(status=match['status'], checked_at=match['generated_at'], error_category=match.get('error_category'))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return result
