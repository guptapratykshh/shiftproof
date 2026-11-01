"""Persistent-host factory. Run migrations before accepting requests."""
import os
from pathlib import Path

def bootstrap():
    from shiftproof.identity import database,organization,tenant_repo
    with database() as db:
        rows=db.execute('SELECT * FROM organizations').fetchall()
    for row in rows: tenant_repo(organization(dict(row)))

def create_app():
    from fastapi import FastAPI,Request
    from fastapi.responses import FileResponse,JSONResponse
    from shiftproof.api import app as api
    from shiftproof.config import settings
    if settings().cloud: raise RuntimeError('Pilot hosting requires persistent local storage; AWS remains paused')
    bootstrap()
    root=Path(__file__).resolve().parents[1];dist=root/'frontend'/'dist'
    if not (dist/'index.html').exists(): raise RuntimeError('Build the frontend first')
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    @app.middleware('http')
    async def headers(request:Request,call_next):
        response=await call_next(request)
        response.headers.update({'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
            'Permissions-Policy':'camera=(), geolocation=(), microphone=(self)',
            'Content-Security-Policy':"default-src 'self'; script-src 'self' blob:; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
        if request.url.scheme=='https': response.headers['Strict-Transport-Security']='max-age=31536000'
        if request.url.path.startswith('/api/') or request.url.path in ('/sw.js','/index.html'): response.headers['Cache-Control']='no-store'
        return response
    app.mount('/api',api)
    @app.get('/{path:path}')
    def frontend(path:str):
        target=(dist/path).resolve()
        if not target.is_relative_to(dist.resolve()) or any(part.startswith('.') for part in Path(path).parts): return JSONResponse(status_code=404,content={'detail':'Not found'})
        if target.is_file(): return FileResponse(target)
        if path and Path(path).suffix: return JSONResponse(status_code=404,content={'detail':'Not found'})
        return FileResponse(dist/'index.html',headers={'Cache-Control':'no-store'})
    return app
