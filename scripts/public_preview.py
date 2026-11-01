"""Serve the built UI and isolated authenticated organization APIs on one port.

.venv/bin/uvicorn public_preview:create_app --app-dir scripts --factory --port 8080
cloudflared tunnel --url http://127.0.0.1:8080

Set PUBLIC_PREVIEW_READ_ONLY=true to disable sign-in, writes and provider access.
"""
import os
from pathlib import Path


def create_app():
    root = Path(__file__).resolve().parents[1]
    dist = root / 'frontend' / 'dist'
    if not (dist / 'index.html').exists():
        raise RuntimeError('Run npm run build in frontend before starting the public preview')
    from dotenv import load_dotenv
    load_dotenv(root / '.env')
    read_only = os.getenv('PUBLIC_PREVIEW_READ_ONLY', 'false').lower() == 'true'
    # Keep existing public organization records separate from the private localhost workspace.
    os.environ.update({
        'SHIFTPROOF_ENV': 'local',
        'SHIFTPROOF_DATA_DIR': str(root / '.local' / 'public-preview'),
    })
    if read_only:
        os.environ.update({
            'EXTRACTION_PROVIDER': 'scripted',
            'GNANI_API_KEY': '', 'GNANI_SECRET_ARN': '', 'GEMINI_API_KEY': '',
            'GEMINI_FREE_TIER_CONFIRMED': 'false',
        })
    from fastapi import FastAPI, Request
    from fastapi.responses import FileResponse, JSONResponse
    from shiftproof.config import settings
    settings.cache_clear()
    from shiftproof.api import app as api_app, config
    preview = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @preview.middleware('http')
    async def preview_access(request: Request, call_next):
        # /questions is deterministic and read-only despite its POST interface.
        if read_only and request.method not in ('GET', 'HEAD') and not (
            request.method == 'POST' and request.url.path == '/api/questions'
        ):
            return JSONResponse(status_code=403, content={
                'detail': 'This public preview is read-only. Explore the fictional reports, evidence and handover.'
            })
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response

    @preview.get('/api/config')
    def preview_config():
        return {**config(), 'public_read_only': read_only}

    preview.mount('/api', api_app)

    @preview.get('/{path:path}')
    def frontend(path: str):
        if path == 'demo' or path.startswith('demo/'):
            from fastapi.responses import RedirectResponse
            return RedirectResponse('/login', status_code=307)
        target = (dist / path).resolve()
        if not target.is_relative_to(dist.resolve()) or any(part.startswith('.') for part in Path(path).parts):
            return JSONResponse(status_code=404, content={'detail': 'Not found'})
        if target.is_file():
            return FileResponse(target)
        if path and Path(path).suffix:
            return JSONResponse(status_code=404, content={'detail': 'Not found'})
        return FileResponse(dist / 'index.html')

    return preview
