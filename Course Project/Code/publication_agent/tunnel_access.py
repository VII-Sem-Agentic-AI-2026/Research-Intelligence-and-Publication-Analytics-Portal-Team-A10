"""Exact, short-lived origin registration for the optional Quick Tunnel launcher."""
import json
import time
from urllib.parse import urlparse

def public_origin(root):
    try:
        config=json.loads((root/'cloudflare_origin.json').read_text(encoding='utf-8'))
        origin=config['origin'];parsed=urlparse(origin)
        if config['expires_at']<=time.time():return None
        if parsed.scheme!='https' or not parsed.hostname or not parsed.hostname.endswith('.trycloudflare.com'):return None
        if parsed.username or parsed.password or parsed.port or parsed.path or parsed.query or parsed.fragment:return None
        if origin!='https://'+parsed.hostname:return None
        return origin
    except (OSError,ValueError,KeyError,TypeError):return None

def validate_request(headers,root):
    from .accounts import Forbidden
    host=headers.get('Host','');origin=headers.get('Origin')
    parsed=urlparse('http://'+host);public=public_origin(root)
    local=parsed.hostname in {'localhost','127.0.0.1','::1'}
    if not local and (not public or host!=urlparse(public).netloc):raise Forbidden('Invalid portal host')
    permitted={'http://'+host} if local else set()
    if public:permitted.add(public)
    if origin and origin not in permitted:raise Forbidden('Cross-origin requests are forbidden')

def secure_cookie(headers,root):
    origin=public_origin(root)
    return bool(origin and (headers.get('Origin')==origin or headers.get('Host')==urlparse(origin).netloc))
