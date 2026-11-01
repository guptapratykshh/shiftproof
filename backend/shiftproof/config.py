import os
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

class Settings:
    def __init__(self):
        self.cloud = os.getenv('SHIFTPROOF_ENV', 'local') == 'aws'
        self.data_dir = Path(os.getenv('SHIFTPROOF_DATA_DIR', '.local'))
        self.provider = os.getenv('EXTRACTION_PROVIDER', 'bedrock' if self.cloud else 'scripted')
        self.region = os.getenv('AWS_REGION', 'us-east-1')
        self.model_id = os.getenv('BEDROCK_MODEL_ID', 'us.amazon.nova-2-lite-v1:0')
        self.gemini_account_tier = os.getenv('GEMINI_ACCOUNT_TIER', 'free').lower()
        self.business_provider_approved = os.getenv('SHIFTPROOF_BUSINESS_PROVIDER_APPROVED', 'false').lower() == 'true'
        self.gemini_business_terms_confirmed = os.getenv('GEMINI_BUSINESS_TERMS_CONFIRMED', 'false').lower() == 'true'
        self.gnani_account_tier = os.getenv('GNANI_ACCOUNT_TIER', 'programme').lower()
        self.gnani_business_terms_confirmed = os.getenv('GNANI_BUSINESS_TERMS_CONFIRMED', 'false').lower() == 'true'
        self.gemini_model = os.getenv('GEMINI_BUSINESS_MODEL_ID', '') if self.gemini_account_tier == 'business' else os.getenv('GEMINI_MODEL_ID', 'gemini-3.8-flash')
        self.gemini_key = os.getenv('GEMINI_BUSINESS_API_KEY', '') if self.gemini_account_tier == 'business' else os.getenv('GEMINI_API_KEY', '')
        self.gemini_free_tier_confirmed = os.getenv('GEMINI_FREE_TIER_CONFIRMED', 'false').lower() == 'true'
        self.table = os.getenv('TABLE_NAME', '')
        self.bucket = os.getenv('AUDIO_BUCKET', '')
        self.queue = os.getenv('QUEUE_URL', '')
        self.pool = os.getenv('COGNITO_POOL_ID', '')
        self.client = os.getenv('COGNITO_CLIENT_ID', '')
        self.origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',')
        self.max_notes = int(os.getenv('MAX_NOTES_PER_DAY', '100'))
        self.max_calls = int(os.getenv('MAX_MODEL_CALLS_PER_DAY', '200'))

    def gnani_key(self):
        if self.gnani_account_tier == 'business':
            return os.getenv('GNANI_BUSINESS_API_KEY', '')
        key = os.getenv('GNANI_API_KEY', '')
        arn = os.getenv('GNANI_SECRET_ARN')
        if not key and arn:
            import boto3, json
            raw = boto3.client('secretsmanager', region_name=self.region).get_secret_value(SecretId=arn)['SecretString']
            try:
                key = json.loads(raw).get('GNANI_API_KEY', '')
            except (ValueError, AttributeError):
                key = raw
        return key if key and key != 'NOT_CONFIGURED' else ''

@lru_cache
def settings():
    return Settings()
