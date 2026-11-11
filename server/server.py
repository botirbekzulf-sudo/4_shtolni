"""Сервер «Четырёх Штолен»: комнаты, аккаунты, облачные сохранения, рейтинг и жалобы.

Только стандартная библиотека Python 3.10+. Запуск: python server.py
Переменные окружения:
  PORT       порт (по умолчанию 8787)
  DATA_DIR   папка для базы (по умолчанию ./data); на хостинге это должен быть постоянный диск
  ADMIN_KEY  ключ для просмотра жалоб: /api/reports?key=...
"""
import asyncio, base64, hashlib, hmac, json, os, secrets, struct, time

PORT = int(os.environ.get('PORT', '8787'))
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
ADMIN_KEY = os.environ.get('ADMIN_KEY', '')
DB_PATH = os.path.join(DATA_DIR, 'db.json')
MAX_MSG = 1 << 20
MAX_ROOM = 16
WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

# ---------- База ----------
db = {'accounts': {}, 'reports': []}
dirty = False

def load_db():
    global db
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(DB_PATH):
        with open(DB_PATH, encoding='utf-8') as f:
            db = json.load(f)
    db.setdefault('accounts', {}); db.setdefault('reports', [])

def save_db():
    global dirty
    if not dirty:
        return
    tmp = DB_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False)
    os.replace(tmp, DB_PATH)
    dirty = False

async def saver():
    while True:
        await asyncio.sleep(5)
        try:
            save_db()
        except Exception as e:
            print('save error', e)

def token_hash(t):
    return hashlib.sha256(t.encode()).hexdigest()

def auth(headers):
    h = headers.get('authorization', '')
    if not h.startswith('Bearer ') or ':' not in h:
        return None
    acc_id, tok = h[7:].split(':', 1)
    acc = db['accounts'].get(acc_id)
    if acc and hmac.compare_digest(acc['th'], token_hash(tok)):
        return acc_id
    return None

# Профиль хранит клиент, сервер ограничивает слишком резкий рост ценностей
def merge_profile(old, new):
    if not isinstance(new, dict):
        return old
    out = dict(new)
    o = old or {}
    for key, cap in (('coins', 4000), ('xp', 20000), ('seasonXp', 20000), ('kills', 400), ('wins', 20)):
        prev = o.get(key, 0) or 0
        val = new.get(key, 0)
        if not isinstance(val, (int, float)):
            val = prev
        out[key] = min(val, prev + cap) if o else min(val, cap)
    return out

def level_of(xp):
    lvl, need = 1, 100
    while xp >= need:
        xp -= need; lvl += 1; need = 100 * lvl
    return lvl

# ---------- HTTP ----------
rate = {}

def limited(ip, key, n, window):
    now = time.time()
    lst = [t for t in rate.get((ip, key), []) if now - t < window]
    if len(lst) >= n:
        rate[(ip, key)] = lst
        return True
    lst.append(now); rate[(ip, key)] = lst
    return False

async def http_reply(w, code, body, ctype='application/json'):
    if not isinstance(body, (bytes, bytearray)):
        body = json.dumps(body, ensure_ascii=False).encode()
    head = (f'HTTP/1.1 {code} OK\r\nContent-Type: {ctype}; charset=utf-8\r\nContent-Length: {len(body)}\r\n'
            'Access-Control-Allow-Origin: *\r\nAccess-Control-Allow-Headers: Content-Type, Authorization\r\n'
            'Access-Control-Allow-Methods: GET, POST, PUT, OPTIONS\r\nConnection: close\r\n\r\n')
    w.write(head.encode() + body)
    await w.drain()

async def handle_api(method, path, query, headers, body, ip, w):
    global dirty
    if method == 'OPTIONS':
        return await http_reply(w, 204, b'')
    if path in ('/', '/health'):
        return await http_reply(w, 200, {'ok': True, 'rooms': len(rooms)})
    data = {}
    if body:
        try:
            data = json.loads(body.decode('utf-8'))
        except Exception:
            return await http_reply(w, 400, {'error': 'bad json'})
    if path == '/api/register' and method == 'POST':
        if limited(ip, 'reg', 10, 3600):
            return await http_reply(w, 429, {'error': 'too many'})
        acc_id = secrets.token_hex(8); tok = secrets.token_urlsafe(24)
        db['accounts'][acc_id] = {'th': token_hash(tok), 'name': str(data.get('name', ''))[:14], 'profile': None, 'created': int(time.time()), 'updated': 0}
        dirty = True
        return await http_reply(w, 200, {'id': acc_id, 'token': tok})
    if path == '/api/profile':
        acc_id = auth(headers)
        if not acc_id:
            return await http_reply(w, 401, {'error': 'auth'})
        acc = db['accounts'][acc_id]
        if method == 'GET':
            return await http_reply(w, 200, {'profile': acc['profile'], 'updated': acc['updated'], 'name': acc['name']})
        if method == 'PUT':
            acc['profile'] = merge_profile(acc['profile'], data.get('profile'))
            acc['name'] = str(data.get('name', acc['name']))[:14]
            acc['updated'] = int(time.time() * 1000)
            dirty = True
            return await http_reply(w, 200, {'profile': acc['profile'], 'updated': acc['updated']})
    if path == '/api/top' and method == 'GET':
        rows = []
        for acc in db['accounts'].values():
            p = acc.get('profile') or {}
            if not p.get('matches'):
                continue
            rows.append({'name': acc['name'], 'level': level_of(p.get('xp', 0)), 'xp': p.get('xp', 0), 'kills': p.get('kills', 0), 'wins': p.get('wins', 0)})
        rows.sort(key=lambda r: (-r['xp'], -r['wins']))
        return await http_reply(w, 200, {'top': rows[:50]})
    if path == '/api/report' and method == 'POST':
        if limited(ip, 'rep', 20, 3600):
            return await http_reply(w, 429, {'error': 'too many'})
        rep = {k: str(data.get(k, ''))[:2000] for k in ('target', 'targetName', 'reason', 'text', 'room', 'chat')}
        rep['from'] = auth(headers) or ''
        rep['ip'] = hashlib.sha256(ip.encode()).hexdigest()[:12]
        rep['time'] = int(time.time())
        db['reports'].append(rep); db['reports'] = db['reports'][-5000:]
        dirty = True
        return await http_reply(w, 200, {'ok': True})
    if path == '/api/reports' and method == 'GET':
        if not ADMIN_KEY or not hmac.compare_digest(query.get('key', ''), ADMIN_KEY):
            return await http_reply(w, 403, {'error': 'forbidden'})
        return await http_reply(w, 200, {'reports': db['reports'][-500:]})
    return await http_reply(w, 404, {'error': 'not found'})

# ---------- WebSocket ----------
rooms = {}  # код -> {'host': Conn, 'clients': {id: Conn}}

class Conn:
    def __init__(self, r, w):
        self.r, self.w = r, w
        self.room = None; self.id = None; self.is_host = False; self.closed = False
        self.lock = asyncio.Lock()

    async def send(self, obj):
        if self.closed:
            return
        data = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode()
        n = len(data)
        if n < 126:
            hdr = struct.pack('!BB', 0x81, n)
        elif n < 65536:
            hdr = struct.pack('!BBH', 0x81, 126, n)
        else:
            hdr = struct.pack('!BBQ', 0x81, 127, n)
        try:
            async with self.lock:
                self.w.write(hdr + data)
                await self.w.drain()
        except Exception:
            self.closed = True

    async def recv(self):
        """Возвращает текст сообщения или None при закрытии."""
        buf = b''
        while True:
            h = await self.r.readexactly(2)
            fin, op = h[0] & 0x80, h[0] & 0x0F
            masked, ln = h[1] & 0x80, h[1] & 0x7F
            if ln == 126:
                ln = struct.unpack('!H', await self.r.readexactly(2))[0]
            elif ln == 127:
                ln = struct.unpack('!Q', await self.r.readexactly(8))[0]
            if ln > MAX_MSG:
                return None
            mask = await self.r.readexactly(4) if masked else b''
            payload = await self.r.readexactly(ln)
            if masked:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if op == 0x8:
                return None
            if op == 0x9:
                async with self.lock:
                    self.w.write(struct.pack('!BB', 0x8A, len(payload)) + payload)
                    await self.w.drain()
                continue
            if op == 0xA:
                continue
            buf += payload
            if len(buf) > MAX_MSG:
                return None
            if fin:
                return buf.decode('utf-8', 'replace')

async def ws_session(c):
    try:
        while True:
            txt = await c.recv()
            if txt is None:
                break
            try:
                m = json.loads(txt)
            except Exception:
                continue
            op = m.get('op')
            if op == 'host':
                code = str(m.get('code', ''))[:8]
                if code in rooms:
                    await c.send({'op': 'err', 'e': 'taken'}); continue
                rooms[code] = {'host': c, 'clients': {}}
                c.room, c.is_host = code, True
                await c.send({'op': 'hosted', 'code': code})
            elif op == 'join':
                code = str(m.get('code', ''))[:8]; cid = str(m.get('id', ''))[:64]
                room = rooms.get(code)
                if not room:
                    await c.send({'op': 'err', 'e': 'noroom'}); continue
                if len(room['clients']) >= MAX_ROOM or not cid or cid in room['clients']:
                    await c.send({'op': 'err', 'e': 'full'}); continue
                room['clients'][cid] = c
                c.room, c.id = code, cid
                await c.send({'op': 'joined'})
                await room['host'].send({'op': 'join', 'id': cid})
            elif op == 'up' and c.room and not c.is_host:
                room = rooms.get(c.room)
                if room:
                    await room['host'].send({'op': 'from', 'id': c.id, 'm': m.get('m')})
            elif op == 'to' and c.is_host:
                t = rooms[c.room]['clients'].get(str(m.get('id')))
                if t:
                    await t.send({'op': 'msg', 'm': m.get('m')})
            elif op == 'all' and c.is_host:
                for t in list(rooms[c.room]['clients'].values()):
                    await t.send({'op': 'msg', 'm': m.get('m')})
    except (asyncio.IncompleteReadError, ConnectionError):
        pass
    finally:
        c.closed = True
        room = rooms.get(c.room) if c.room else None
        if room:
            if c.is_host and room['host'] is c:
                for t in list(room['clients'].values()):
                    await t.send({'op': 'hostgone'})
                rooms.pop(c.room, None)
            elif room['clients'].get(c.id) is c:
                room['clients'].pop(c.id, None)
                await room['host'].send({'op': 'leave', 'id': c.id})
        try:
            c.w.close()
        except Exception:
            pass

# ---------- Приём соединений ----------
async def handle(r, w):
    ip = (w.get_extra_info('peername') or ('?',))[0]
    try:
        head = await asyncio.wait_for(r.readuntil(b'\r\n\r\n'), 15)
        lines = head.decode('latin-1').split('\r\n')
        method, target, _ = lines[0].split(' ', 2)
        headers = {}
        for ln in lines[1:]:
            if ':' in ln:
                k, v = ln.split(':', 1); headers[k.strip().lower()] = v.strip()
        ip = headers.get('x-forwarded-for', ip).split(',')[0].strip()
        path, _, qs = target.partition('?')
        query = dict(p.split('=', 1) for p in qs.split('&') if '=' in p)
        if path == '/ws' and headers.get('upgrade', '').lower() == 'websocket':
            acc = base64.b64encode(hashlib.sha1((headers['sec-websocket-key'] + WS_GUID).encode()).digest()).decode()
            w.write(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                     f'Sec-WebSocket-Accept: {acc}\r\n\r\n').encode())
            await w.drain()
            await ws_session(Conn(r, w))
            return
        n = int(headers.get('content-length', '0') or 0)
        if n > MAX_MSG:
            return await http_reply(w, 413, {'error': 'too large'})
        body = await r.readexactly(n) if n else b''
        await handle_api(method, path, query, headers, body, ip, w)
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass

async def main():
    load_db()
    asyncio.create_task(saver())
    srv = await asyncio.start_server(handle, '0.0.0.0', PORT)
    # Английский текст: консоль Windows может не уметь кириллицу
    print(f'Server listening on port {PORT}, database: {DB_PATH}', flush=True)
    async with srv:
        await srv.serve_forever()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        save_db()
