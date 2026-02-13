import hashlib
from typing import Literal, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from psycopg.types.json import Jsonb

from .auth import AuthUser, create_access_token, token_from_header, verify_access_token
from .config import AUTH_COOKIE_DOMAIN, AUTH_COOKIE_NAME, AUTH_COOKIE_SECURE
from .db import db_conn
from .embeddings import get_embedder, pgvector_text
from .llm import openai_chat_completion
from .retrieval import hybrid_retrieve


# Загружаем .env при запуске вне Docker (удобство для локальной разработки)
load_dotenv(override=False)

app = FastAPI(title="KB-RING API", version="0.0.1")


def _set_auth_cookie(resp: JSONResponse, token: str):
    kwargs = {
        "key": AUTH_COOKIE_NAME,
        "value": token,
        "max_age": 3600,
        "path": "/",
        "httponly": True,
        "samesite": "lax",
        "secure": AUTH_COOKIE_SECURE,
    }
    if AUTH_COOKIE_DOMAIN:
        kwargs["domain"] = AUTH_COOKIE_DOMAIN
    resp.set_cookie(**kwargs)


def get_current_user(request: Request, authorization: Optional[str] = Header(None)) -> AuthUser:
    token = token_from_header(authorization) or request.cookies.get(AUTH_COOKIE_NAME)
    user = verify_access_token(token or "")
    if not user:
        raise HTTPException(status_code=401, detail="требуется авторизация")
    return user


@app.get("/health", response_class=JSONResponse)
def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(
        "<h1>KB-RING</h1>"
        "<p><a href='/ui'>UI</a> | <a href='/docs'>OpenAPI</a></p>"
        "<ul>"
        "<li>POST /api/v1/ingest/transcript</li>"
        "<li>GET /api/v1/search?q=...</li>"
        "</ul>"
    )


@app.post("/api/v1/dev/login", response_class=JSONResponse)
def dev_login(user_id: int = 1, email: str = "dev@example.com", name: str = "Dev"):
    # Хелпер для локальной разработки. В проде авторизация должна быть как в TG (OAuth Яндекс + JWT).
    token = create_access_token(user_id=user_id, email=email, display_name=name)
    if not token:
        raise HTTPException(status_code=500, detail="JWT_SECRET не задан")
    resp = JSONResponse({"access_token": token, "token_type": "bearer"})
    _set_auth_cookie(resp, token)
    return resp


@app.post("/api/v1/ingest/transcript", response_class=JSONResponse)
def ingest_transcript(
    request: Request,
    title: str = Form(...),
    text: str = Form(...),
    source_ref: Optional[str] = Form(default=None),
    uri: Optional[str] = Form(default=None),
    current_user: AuthUser = Depends(get_current_user),
):
    """
    Этап 1: сохранить транскрипт в БД и поставить задачу индексации/обогащения.
    Модель авторизации: как в TG (JWT, `sub = user_id`, cookie `auth_token`).
    """
    if not text.strip():
        raise HTTPException(status_code=400, detail="text is empty")

    content_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tac.documents (user_id, source, source_ref, uri, doc_type, title, body_text, content_sha256, meta)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    current_user.user_id,
                    "transcription",
                    source_ref,
                    uri,
                    "transcript",
                    title,
                    text,
                    content_sha,
                    Jsonb({"ingest": "api"}),
                ),
            )
            doc_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO op.jobs (user_id, kind, status, payload)
                VALUES (%s, %s, 'queued', %s)
                RETURNING id
                """,
                (current_user.user_id, "index_document", Jsonb({"document_id": doc_id})),
            )
            job_id = cur.fetchone()[0]
    return {"document_id": doc_id, "job_id": job_id}


@app.get("/api/v1/search", response_class=JSONResponse)
def search(
    q: str,
    limit: int = 10,
    current_user: AuthUser = Depends(get_current_user),
):
    """
    Hybrid search:
    - FTS по `tac.chunks.tsv`
    - vector similarity по `tac.embeddings` (локальные sentence-transformers), если доступно
    """
    q = (q or "").strip()
    if not q:
        return {"items": []}
    limit = max(1, min(50, int(limit)))

    embedder = get_embedder()
    qvec_txt: Optional[str] = None
    model: Optional[str] = None
    if embedder is not None and int(getattr(embedder, "dims", 0) or 0) == 384:
        try:
            qvec_txt = pgvector_text(embedder.embed_one(q))
            model = embedder.model_name
        except Exception:
            qvec_txt = None
            model = None

    with db_conn() as conn:
        with conn.cursor() as cur:
            if qvec_txt and model:
                cur.execute(
                    """
                    WITH
                      fts AS (
                        SELECT
                          c.id AS chunk_id,
                          ts_rank(c.tsv, plainto_tsquery('simple', %(q)s)) AS s_fts
                        FROM tac.chunks c
                        JOIN tac.documents d ON d.id = c.document_id
                        WHERE d.user_id = %(user_id)s
                          AND c.tsv @@ plainto_tsquery('simple', %(q)s)
                        ORDER BY s_fts DESC
                        LIMIT 200
                      ),
                      vec AS (
                        SELECT
                          e.chunk_id AS chunk_id,
                          (1.0 - (e.embedding <=> (%(qvec)s)::vector(384))) AS s_vec
                        FROM tac.embeddings e
                        JOIN tac.chunks c ON c.id = e.chunk_id
                        JOIN tac.documents d ON d.id = c.document_id
                        WHERE d.user_id = %(user_id)s
                          AND e.model = %(model)s
                        ORDER BY e.embedding <=> (%(qvec)s)::vector(384)
                        LIMIT 200
                      ),
                      comb AS (
                        SELECT
                          COALESCE(fts.chunk_id, vec.chunk_id) AS chunk_id,
                          COALESCE(fts.s_fts, 0.0) AS s_fts,
                          COALESCE(vec.s_vec, 0.0) AS s_vec,
                          (0.55 * COALESCE(fts.s_fts, 0.0) + 0.45 * COALESCE(vec.s_vec, 0.0)) AS rank
                        FROM fts
                        FULL OUTER JOIN vec ON vec.chunk_id = fts.chunk_id
                      )
                    SELECT
                      d.id, d.title, d.source, d.doc_type, d.source_ref, d.uri,
                      c.chunk_text,
                      comb.rank,
                      comb.s_fts,
                      comb.s_vec
                    FROM comb
                    JOIN tac.chunks c ON c.id = comb.chunk_id
                    JOIN tac.documents d ON d.id = c.document_id
                    WHERE d.user_id = %(user_id)s
                    ORDER BY comb.rank DESC
                    LIMIT %(limit)s
                    """,
                    {"q": q, "user_id": current_user.user_id, "limit": limit, "qvec": qvec_txt, "model": model},
                )
            else:
                cur.execute(
                    """
                    SELECT d.id, d.title, d.source, d.doc_type, d.source_ref, d.uri,
                           c.chunk_text,
                           ts_rank(c.tsv, plainto_tsquery('simple', %s)) AS rank
                    FROM tac.chunks c
                    JOIN tac.documents d ON d.id = c.document_id
                    WHERE d.user_id = %s
                      AND c.tsv @@ plainto_tsquery('simple', %s)
                    ORDER BY rank DESC
                    LIMIT %s
                    """,
                    (q, current_user.user_id, q, limit),
                )
            rows = cur.fetchall()
    items = []
    for r in rows:
        items.append(
            {
                "document_id": r[0],
                "title": r[1],
                "source": r[2],
                "doc_type": r[3],
                "source_ref": r[4],
                "uri": r[5],
                "chunk_text": r[6],
                "rank": float(r[7]),
                "fts_rank": float(r[8]) if len(r) > 8 and r[8] is not None else None,
                "vec_score": float(r[9]) if len(r) > 9 and r[9] is not None else None,
            }
        )
    return {"items": items}


@app.get("/ui", response_class=HTMLResponse)
def ui(current_user: AuthUser = Depends(get_current_user)):
    # Minimal UI with tabs. Later we can split into templates.
    return HTMLResponse(
        """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>KB-RING</title>
  <style>
    :root { --bg: #0b1020; --card: #121a33; --fg: #e8ecff; --muted: #a8b1d9; --accent: #6ee7ff; }
    body { margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; background: radial-gradient(1000px 600px at 20% -10%, #1d2a5a 0%, transparent 55%), radial-gradient(900px 600px at 80% 0%, #123a3a 0%, transparent 55%), var(--bg); color: var(--fg); }
    .wrap { max-width: 980px; margin: 0 auto; padding: 28px 18px 60px; }
    .top { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0.3px; }
    .me { color: var(--muted); font-size: 13px; }
    .tabs { display: flex; gap: 10px; margin-top: 16px; flex-wrap: wrap; }
    .tab { display: inline-flex; align-items: center; gap: 8px; padding: 10px 12px; border: 1px solid rgba(255,255,255,0.10); border-radius: 10px; text-decoration: none; color: var(--fg); background: rgba(255,255,255,0.02); }
    .tab.active { border-color: rgba(110,231,255,0.65); box-shadow: 0 0 0 3px rgba(110,231,255,0.10) inset; }
    .card { margin-top: 14px; background: rgba(18,26,51,0.75); border: 1px solid rgba(255,255,255,0.10); border-radius: 14px; padding: 16px; backdrop-filter: blur(6px); }
    label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
    input[type=text], textarea { width: 100%; box-sizing: border-box; border-radius: 10px; border: 1px solid rgba(255,255,255,0.12); background: rgba(0,0,0,0.15); color: var(--fg); padding: 10px 12px; outline: none; }
    textarea { min-height: 140px; resize: vertical; }
    .row { display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: end; }
    button { border: 0; border-radius: 10px; padding: 10px 12px; background: linear-gradient(135deg, rgba(110,231,255,0.9), rgba(130,170,255,0.9)); color: #061018; font-weight: 700; cursor: pointer; }
    .hint { margin-top: 8px; font-size: 12px; color: var(--muted); line-height: 1.45; }
    .results { margin-top: 14px; display: grid; gap: 10px; }
    .hit { border: 1px solid rgba(255,255,255,0.10); border-radius: 12px; padding: 12px; background: rgba(0,0,0,0.10); }
    .hit .title { font-weight: 700; font-size: 14px; }
    .hit .meta { margin-top: 4px; color: var(--muted); font-size: 12px; }
    .hit pre { margin: 10px 0 0; white-space: pre-wrap; word-wrap: break-word; font-size: 13px; }
    .disabled { opacity: 0.6; pointer-events: none; }

    /* Chat */
    .chatlog { margin-top: 12px; display: grid; gap: 10px; }
    .msg { border: 1px solid rgba(255,255,255,0.10); border-radius: 12px; padding: 12px; background: rgba(0,0,0,0.10); }
    .msg.user { border-color: rgba(110,231,255,0.35); }
    .msg.assistant { border-color: rgba(255,255,255,0.10); }
    .msg .role { font-size: 12px; color: var(--muted); }
    .msg pre { margin: 8px 0 0; white-space: pre-wrap; word-wrap: break-word; font-size: 13px; }
    .cit { margin-top: 10px; border-top: 1px solid rgba(255,255,255,0.10); padding-top: 8px; }
    .cit .c { font-size: 12px; color: var(--muted); line-height: 1.45; }
  </style>
  <script>
    const CHAT_SID_KEY = 'kb_ring_session_id';
    let chatInitDone = false;

    function setTab(tab) {
      const tabs = document.querySelectorAll('[data-tab]');
      tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
      document.querySelectorAll('[data-pane]').forEach(p => p.style.display = (p.dataset.pane === tab) ? 'block' : 'none');
      location.hash = tab;
      if (tab === 'chat') initChat();
    }

    function escapeHtml(s) {
      return (s || '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
    }

    async function doSearch() {
      const q = document.getElementById('q').value.trim();
      const out = document.getElementById('results');
      out.innerHTML = '';
      if (!q) return;
      const r = await fetch('/api/v1/search?q=' + encodeURIComponent(q) + '&limit=20', { headers: { 'accept': 'application/json' }});
      if (!r.ok) {
        out.innerHTML = '<div class="hit"><div class="title">Ошибка поиска</div><pre>' + (await r.text()) + '</pre></div>';
        return;
      }
      const data = await r.json();
      const items = data.items || [];
      if (!items.length) {
        out.innerHTML = '<div class="hit"><div class="title">Ничего не найдено</div><div class="meta">Попробуйте другой запрос.</div></div>';
        return;
      }
      for (const it of items) {
        const el = document.createElement('div');
        el.className = 'hit';
        const title = (it.title || '(untitled)');
        const meta = [it.source, it.doc_type, it.source_ref ? ('ref: ' + it.source_ref) : null].filter(Boolean).join(' | ');
        el.innerHTML = '<div class="title">' + title + '</div>' +
                       '<div class="meta">' + meta + '</div>' +
                       '<pre>' + (it.chunk_text || '') + '</pre>';
        out.appendChild(el);
      }
    }

    async function ingestTranscript() {
      const title = document.getElementById('t_title').value.trim();
      const text = document.getElementById('t_text').value.trim();
      const ref = document.getElementById('t_ref').value.trim();
      const out = document.getElementById('ingest_out');
      out.textContent = '';
      const body = new URLSearchParams();
      body.set('title', title || 'transcript');
      body.set('text', text);
      if (ref) body.set('source_ref', ref);
      const r = await fetch('/api/v1/ingest/transcript', { method: 'POST', body });
      out.textContent = r.ok ? JSON.stringify(await r.json(), null, 2) : await r.text();
    }

    async function ensureChatSession() {
      let sid = localStorage.getItem(CHAT_SID_KEY);
      if (sid) return parseInt(sid, 10);
      const body = new URLSearchParams();
      body.set('title', 'ui');
      const r = await fetch('/api/v1/chat/sessions', { method: 'POST', body });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      sid = data.session_id;
      localStorage.setItem(CHAT_SID_KEY, String(sid));
      return sid;
    }

    async function loadChat() {
      const out = document.getElementById('chatlog');
      out.innerHTML = '';
      const sid = await ensureChatSession();
      const r = await fetch('/api/v1/chat/sessions/' + sid, { headers: { 'accept': 'application/json' }});
      if (!r.ok) {
        out.innerHTML = '<div class="msg assistant"><div class="role">system</div><pre>' + escapeHtml(await r.text()) + '</pre></div>';
        return;
      }
      const data = await r.json();
      const msgs = data.messages || [];
      for (const m of msgs) {
        const el = document.createElement('div');
        el.className = 'msg ' + (m.role === 'user' ? 'user' : 'assistant');
        el.innerHTML = '<div class="role">' + escapeHtml(m.role) + '</div><pre>' + escapeHtml(m.content || '') + '</pre>';
        out.appendChild(el);
      }
    }

    function renderCitations(citations) {
      const items = citations || [];
      if (!items.length) return '';
      let html = '<div class="cit"><div class="role">citations</div>';
      for (const c of items) {
        const meta = '[' + (c.n ?? '?') + '] ' + (c.uri || '') + (c.title ? (' | ' + c.title) : '') + ' | chunk_id=' + c.chunk_id;
        html += '<div class="c">' + escapeHtml(meta) + '</div>';
        if (c.excerpt) html += '<div class="c"><pre style="margin:6px 0 0; white-space:pre-wrap;">' + escapeHtml(c.excerpt) + '</pre></div>';
      }
      html += '</div>';
      return html;
    }

    async function sendChat() {
      const inp = document.getElementById('chat_text');
      const mode = document.getElementById('chat_mode').value;
      const q = inp.value.trim();
      if (!q) return;
      const sid = await ensureChatSession();
      const out = document.getElementById('chatlog');

      const u = document.createElement('div');
      u.className = 'msg user';
      u.innerHTML = '<div class="role">user</div><pre>' + escapeHtml(q) + '</pre>';
      out.appendChild(u);
      inp.value = '';

      const body = new URLSearchParams();
      body.set('text', q);
      body.set('mode', mode);
      const r = await fetch('/api/v1/chat/sessions/' + sid + '/message', { method: 'POST', body });
      if (!r.ok) {
        const e = document.createElement('div');
        e.className = 'msg assistant';
        e.innerHTML = '<div class="role">error</div><pre>' + escapeHtml(await r.text()) + '</pre>';
        out.appendChild(e);
        return;
      }
      const data = await r.json();

      const a = document.createElement('div');
      a.className = 'msg assistant';
      if (data.mode === 'search') {
        a.innerHTML = '<div class="role">assistant (search)</div><pre>Результаты retrieval (без LLM)</pre>' + renderCitations(data.results || []);
      } else {
        a.innerHTML = '<div class="role">assistant (' + escapeHtml(data.mode || 'rag') + ')</div><pre>' + escapeHtml((data.answer || {}).text || '') + '</pre>' + renderCitations(data.citations || []);
      }
      out.appendChild(a);
    }

    async function newChatSession() {
      localStorage.removeItem(CHAT_SID_KEY);
      await loadChat();
    }

    async function initChat() {
      if (chatInitDone) return;
      chatInitDone = true;
      document.getElementById('chat_send').addEventListener('click', (e) => { e.preventDefault(); sendChat(); });
      document.getElementById('chat_text').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); sendChat(); }
      });
      document.getElementById('chat_new').addEventListener('click', (e) => { e.preventDefault(); newChatSession(); });
      await loadChat();
    }

    window.addEventListener('load', () => {
      const tab = (location.hash || '#search').slice(1);
      setTab(tab);
      document.getElementById('q_btn').addEventListener('click', (e) => { e.preventDefault(); doSearch(); });
      document.getElementById('q').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); doSearch(); }});
      document.getElementById('t_btn').addEventListener('click', (e) => { e.preventDefault(); ingestTranscript(); });
    });
  </script>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <h1>KB-RING</h1>
      <div class="me">user_id: <b>"""
        + str(current_user.user_id)
        + """</b> | <a style="color: var(--accent)" href="/docs">OpenAPI</a></div>
    </div>

    <div class="tabs">
      <a class="tab" href="#search" data-tab="search">ПОИСК</a>
      <a class="tab" href="#ingest" data-tab="ingest">INGEST</a>
      <a class="tab" href="#chat" data-tab="chat" title="search = без LLM, rag = с LLM (нужен OPENAI_API_KEY)">CHAT (RAG)</a>
    </div>

    <div class="card" data-pane="search">
      <div class="row">
        <div>
          <label>Запрос</label>
          <input id="q" type="text" placeholder="например: diarization protocol" />
        </div>
        <button id="q_btn">Искать</button>
      </div>
      <div class="hint">Режим search-only: без LLM. (Чат (RAG) см. во вкладке CHAT.)</div>
      <div id="results" class="results"></div>
    </div>

    <div class="card" data-pane="ingest" style="display:none">
      <div class="row" style="grid-template-columns: 1fr 1fr auto;">
        <div>
          <label>Title</label>
          <input id="t_title" type="text" placeholder="Совещание 2026-02-13" />
        </div>
        <div>
          <label>Source ref (опционально)</label>
          <input id="t_ref" type="text" placeholder="transcription:task_id=..." />
        </div>
        <button id="t_btn">Загрузить</button>
      </div>
      <div style="margin-top: 10px">
        <label>Transcript text</label>
        <textarea id="t_text" placeholder="вставь сюда текст транскрипта"></textarea>
      </div>
      <div class="hint">После ingest создаётся job `index_document`: воркер нарежет чанки и запишет FTS.</div>
      <pre id="ingest_out" style="margin-top:10px; color: var(--muted)"></pre>
    </div>

    <div class="card" data-pane="chat" style="display:none">
      <div class="row" style="grid-template-columns: 1fr auto auto;">
        <div>
          <label>Сообщение (Ctrl+Enter для отправки)</label>
          <textarea id="chat_text" placeholder="например: где в проекте реализована индексация и какие таблицы БД используются?"></textarea>
        </div>
        <div>
          <label>Mode</label>
          <select id="chat_mode" style="width: 100%; box-sizing: border-box; border-radius: 10px; border: 1px solid rgba(255,255,255,0.12); background: rgba(0,0,0,0.15); color: var(--fg); padding: 10px 12px; outline: none;">
            <option value="search">search</option>
            <option value="rag">rag</option>
            <option value="analysis">analysis</option>
          </select>
          <div class="hint">rag вызывает LLM и вернёт инженерный ответ с источниками.</div>
        </div>
        <div style="display:grid; gap:10px;">
          <button id="chat_send">Отправить</button>
          <button id="chat_new" style="background: rgba(255,255,255,0.08); color: var(--fg); border: 1px solid rgba(255,255,255,0.12); font-weight: 700;">Новая сессия</button>
        </div>
      </div>
      <div id="chatlog" class="chatlog"></div>
    </div>
  </div>
</body>
</html>"""
    )


@app.post("/api/v1/chat/sessions", response_class=JSONResponse)
def chat_create_session(
    title: Optional[str] = Form(default=None),
    current_user: AuthUser = Depends(get_current_user),
):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat.sessions (user_id, title) VALUES (%s, %s) RETURNING id",
                (current_user.user_id, title),
            )
            session_id = int(cur.fetchone()[0])
    return {"session_id": session_id}


@app.get("/api/v1/chat/sessions/{session_id}", response_class=JSONResponse)
def chat_get_session(
    session_id: int,
    current_user: AuthUser = Depends(get_current_user),
):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM chat.sessions WHERE id=%s", (session_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="сессия не найдена")
            if int(row[0]) != int(current_user.user_id):
                raise HTTPException(status_code=403, detail="нет доступа")
            cur.execute(
                "SELECT id, role, content, created_at FROM chat.messages WHERE session_id=%s ORDER BY created_at, id",
                (session_id,),
            )
            rows = cur.fetchall()
    return {
        "session_id": session_id,
        "messages": [
            {
                "id": int(r[0]),
                "role": r[1],
                "content": r[2],
                "created_at": r[3].isoformat() if r[3] else None,
            }
            for r in rows
        ],
    }


@app.post("/api/v1/chat/sessions/{session_id}/message", response_class=JSONResponse)
async def chat_post_message(
    session_id: int,
    text: str = Form(...),
    mode: Literal["search", "rag", "analysis"] = Form(default="search"),
    current_user: AuthUser = Depends(get_current_user),
):
    q = (text or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="пустой текст")

    # Validate session ownership + save user message.
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM chat.sessions WHERE id=%s", (session_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="сессия не найдена")
            if int(row[0]) != int(current_user.user_id):
                raise HTTPException(status_code=403, detail="нет доступа")
            cur.execute(
                "INSERT INTO chat.messages (session_id, role, content) VALUES (%s, 'user', %s) RETURNING id",
                (session_id, q),
            )
            user_message_id = int(cur.fetchone()[0])

    # Retrieval (local): top-K chunks.
    with db_conn() as conn:
        retrieved = hybrid_retrieve(conn, current_user.user_id, q, top_k=15)

    def _display_uri(r) -> str:
        # Prefer canonical document URI; otherwise fall back to a stable pseudo-uri.
        uri = (r.uri or "").strip()
        if uri:
            return uri
        return f"chunk://{r.chunk_id}"

    citations = []
    for i, r in enumerate(retrieved, start=1):
        excerpt = (r.content or "").strip()
        if len(excerpt) > 500:
            excerpt = excerpt[:500] + "..."
        citations.append(
            {
                "n": i,
                "chunk_id": r.chunk_id,
                "doc_id": r.doc_id,
                "title": r.title,
                "uri": _display_uri(r),
                "excerpt": excerpt,
                "score": r.score,
            }
        )

    if mode == "search":
        return {"mode": "search", "results": citations, "user_message_id": user_message_id}

    # mode == "rag|analysis": strict answer based only on retrieved chunks.
    if not retrieved:
        answer_text = "данные не найдены"
        confidence = "low"

        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO chat.messages (session_id, role, content) VALUES (%s, 'assistant', %s) RETURNING id",
                    (session_id, answer_text),
                )
                assistant_message_id = int(cur.fetchone()[0])

        return {
            "mode": mode,
            "answer": {"text": answer_text, "confidence": confidence},
            "citations": [],
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
        }

    # Формируем контекст как нумерованный список источников, чтобы модель могла ссылаться [1], [2], ...
    context_parts = []
    for i, r in enumerate(retrieved, start=1):
        uri = _display_uri(r)
        hdr = f"[{i}] chunk_id={r.chunk_id} doc_id={r.doc_id}"
        if uri:
            hdr += f" uri={uri}"
        if r.title:
            hdr += f" title={r.title}"
        context_parts.append(hdr + "\n" + (r.content or ""))
    context = "\n\n".join(context_parts)
    # hard cap: avoid huge prompts; doc also caps <= 20 chunks
    if len(context) > 20000:
        context = context[:20000]

    system_common = (
        "Ты инженерный ассистент.\n"
        "Отвечай ТОЛЬКО на основании приведённых источников.\n"
        "Если информации недостаточно — скажи \"данные не найдены\".\n"
        "Не придумывай факты.\n"
        "\n"
        "Требования к формату инженерного ответа:\n"
        "- Резюме\n"
        "- Структурированный список (интерфейсы/компоненты/модули) с назначением, ключевыми методами/контрактами\n"
        "- Примеры команд/запросов (например curl), если применимо\n"
        "- Рекомендуется открыть (конкретные документы/файлы), если применимо\n"
        "- Итог (с чего начать)\n"
        "- Источники (обязательно) как список: [1] chunk_id=<id> <uri>, [2] chunk_id=<id> <uri>, ...\n"
        "\n"
        "Правило: внутри текста по возможности ссылайся на источники как [1], [2], ...\n"
    )

    if mode == "analysis":
        system = (
            system_common
            + "\n"
            + "Режим: ANALYSIS.\n"
            + "Сделай отчёт/сводку по найденным источникам: что они покрывают, где противоречат, какие пробелы.\n"
            + "Если есть несколько источников, сравни их и укажи расхождения.\n"
        )
        max_tokens = 900
    else:
        system = system_common + "\n" + "Режим: RAG ANSWER.\n"
        max_tokens = 700

    llm = await openai_chat_completion(system=system, user=q, context=context, temperature=0.1, max_tokens=max_tokens)
    answer_text = llm.text if llm else "данные не найдены"

    # Enforce sources section even if the model forgot to output it.
    if citations and "источники" not in (answer_text or "").lower():
        src_lines = [f"[{c['n']}] chunk_id={c['chunk_id']} {c['uri']}" for c in citations]
        answer_text = (answer_text or "").rstrip() + "\n\nИсточники (обязательно)\n" + "\n".join(src_lines)

    best_score = max((r.score for r in retrieved), default=0.0)
    confidence = "high" if best_score >= 0.25 else ("medium" if best_score >= 0.12 else "low")

    # Save assistant + citations.
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat.messages (session_id, role, content) VALUES (%s, 'assistant', %s) RETURNING id",
                (session_id, answer_text),
            )
            assistant_message_id = int(cur.fetchone()[0])
            for r in retrieved:
                cur.execute(
                    "INSERT INTO chat.message_citations (message_id, chunk_id, score) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (assistant_message_id, r.chunk_id, r.score),
                )

    return {
        "mode": mode,
        "answer": {"text": answer_text, "confidence": confidence},
        "citations": citations,
        "user_message_id": user_message_id,
        "assistant_message_id": assistant_message_id,
    }
