import time
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum
from .config import settings
from .repository import Conflict
from .providers import ProviderError
from . import service

app = FastAPI(title='ShiftProof', version='0.1.0', description='Organization-scoped voice reporting, human review and shift handovers.')
app.add_middleware(CORSMiddleware, allow_origins=settings().origins, allow_credentials=False, allow_methods=['GET','POST','PUT','DELETE','OPTIONS'], allow_headers=['Authorization','Content-Type'])

@app.exception_handler(Conflict)
async def conflict_handler(request, exc):
    return JSONResponse(status_code=409, content={'detail': str(exc)})

@app.exception_handler(ProviderError)
async def provider_handler(request, exc):
    return JSONResponse(status_code=503, content={'detail': str(exc)})

@app.exception_handler(OSError)
async def storage_handler(request, exc):
    import errno
    full=exc.errno in (errno.ENOSPC,errno.EDQUOT)
    return JSONResponse(status_code=507 if full else 503,content={'detail':
        'Recording storage is full. Your phone draft is retained; contact the organization owner.' if full else
        'Storage is temporarily unavailable. Keep your draft and retry.'})

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'shiftproof'}

@app.get('/ready')
def readiness():
    import os
    durable=os.getenv('SHIFTPROOF_DURABLE_JOBS','false').lower()=='true'
    heartbeat=Path(os.getenv('SHIFTPROOF_WORKER_HEALTH_FILE') or settings().data_dir/'worker-health.json')
    healthy=not durable or (heartbeat.exists() and time.time()-heartbeat.stat().st_mtime<30)
    return JSONResponse(status_code=200 if healthy else 503,content={'status':'ready' if healthy else 'worker_unavailable','durable_jobs':durable})

@app.get('/config')
def config():
    from .diagnostics import last_check
    s = settings()
    configured = bool(s.gemini_key and (s.gemini_free_tier_confirmed if s.gemini_account_tier=='free' else s.business_provider_approved and s.gemini_business_terms_confirmed and s.gemini_model)) if s.provider == 'gemini' else s.provider == 'scripted'
    check = last_check()
    status = 'sample_only' if s.provider == 'scripted' else 'smoke_passed' if configured and check['status'] == 'passed' else 'configured_not_verified' if configured else 'setup_required'
    return {'mode': 'aws' if s.cloud else 'local', 'extraction_provider': s.provider, 'extraction_configured': configured, 'extraction_model': service.providers.model_name(), 'extraction_check': check, 'configuration_status': status, 'speech_configured': bool(s.gnani_key()), 'cognito_region': s.region, 'cognito_pool_id': s.pool, 'cognito_client_id': s.client, 'organization_accounts_required': True}

handler = Mangum(app, lifespan='off')

# All operational routes require authenticated organization membership.
from .accounts_api import router as accounts_router
from .organizations_api import router as organizations_router
from .pilot_api import router as pilot_router
from .pilot_recovery_api import router as pilot_recovery_router
app.include_router(accounts_router)
app.include_router(organizations_router)
app.include_router(pilot_router)
app.include_router(pilot_recovery_router)

@app.middleware('http')
async def account_origin_guard(request: Request, call_next):
    # Same-origin browser application; enforce Origin on all account mutations,
    # including login/signup before a CSRF token exists.
    path = request.url.path.removeprefix(request.scope.get('root_path', ''))
    protected = path.startswith(('/auth/signup','/auth/login','/auth/worker','/auth/recover','/auth/password','/auth/logout','/organizations','/invitations/accept'))
    if protected and request.method not in ('GET','HEAD','OPTIONS'):
        origin = request.headers.get('origin')
        expected = f"{request.url.scheme}://{request.headers.get('host')}"
        if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and origin != expected and origin not in settings().origins):
            return JSONResponse(status_code=403, content={'detail':'Cross-origin account changes are not allowed'})
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Permissions-Policy'] = 'camera=(), geolocation=(), microphone=(self)'
    if protected or path == '/auth/session' or path.startswith('/invitations/'): response.headers['Cache-Control'] = 'no-store'
    return response
