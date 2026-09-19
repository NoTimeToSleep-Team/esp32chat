#!/usr/bin/env python3
"""LC Moderation API — standalone FastAPI server on port 18081."""
import sys, os
sys.path.insert(0, '/home/gamecat/lc-server')
from app.services.auto_moderator import AutoModerator
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3, time, uvicorn

DB = '/home/gamecat/lc-server/data/sqlite/local_chat.db'
mod = AutoModerator(DB)
mod.start(interval=10)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

class ResolveReq(BaseModel):
    session_token: str = ''
    report_id: int = 0
    action: str = 'dismiss'
    token: str = ''

@app.get('/reports')
async def get_reports(token: str = Query('')):
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    row = c.execute(
        "SELECT u.role FROM sessions s JOIN users u ON s.user_id=u.id "
        "WHERE s.id=? AND s.expires_at_ms>?",
        (token, int(time.time()*1000))
    ).fetchone()
    c.close()
    if not row or row['role'] not in ('admin','moderator'):
        return {'status':'error','message':'Access denied'}
    reports = mod.get_reports(limit=50)
    pending = len(mod.get_reports(status='pending', limit=1000))
    return {'status':'ok','reports':reports,'pending_count':pending}

@app.post('/reports/resolve')
async def resolve_report(req: ResolveReq):
    tok = req.session_token or req.token
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    row = c.execute(
        "SELECT u.login,u.role FROM sessions s JOIN users u ON s.user_id=u.id "
        "WHERE s.id=? AND s.expires_at_ms>?",
        (tok, int(time.time()*1000))
    ).fetchone()
    c.close()
    if not row or row['role'] not in ('admin','moderator'):
        return {'status':'error'}
    mod.resolve(req.report_id, req.action, row['login'])
    return {'status':'ok'}

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=18081)
