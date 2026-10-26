# -*- coding: utf-8 -*-
import telebot
import json
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import logging
import psutil
import sqlite3
import threading
import re
import sys
import atexit
import hmac
import hashlib
import requests

# --- Flask Keep Alive ---
import socket as _socket
from flask import Flask
from threading import Thread

app = Flask('')

# Silence Werkzeug's startup/request logs
import logging as _logging
_logging.getLogger('werkzeug').setLevel(_logging.ERROR)

@app.route('/')
def home():
    return "I'm FENIX HOSTING BOT"

def _is_port_free(port):
    """Return True if the port is available to bind."""
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
        s.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        try:
            s.bind(('0.0.0.0', port))
            return True
        except OSError:
            return False

def run_flask():
    base_port = int(os.environ.get("PORT", 8080))
    candidates = [base_port] + [p for p in range(8081, 8096) if p != base_port]
    for port in candidates:
        if _is_port_free(port):
            try:
                logger.info(f"Flask Keep-Alive starting on port {port}")
                app.run(host='0.0.0.0', port=port, use_reloader=False)
                break
            except Exception as e:
                logger.warning(f"Flask: failed on port {port}: {e}")
        else:
            logger.warning(f"Flask: port {port} in use, skipping...")
    else:
        logger.warning("Flask Keep-Alive: no free port found. Bot will run without keep-alive.")

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    logger.info("Flask Keep-Alive server started.")
# --- End Flask Keep Alive ---

# --- Configuration ---
TOKEN = os.environ.get('BOT_TOKEN', '8919104385:AAHQg4jfuk2Go010qs7Y6PjIht8es6-V9Gc')
OWNER_ID = int(os.environ.get('OWNER_ID', '8640994947'))
ADMIN_ID = int(os.environ.get('ADMIN_ID', '8640994947'))
YOUR_USERNAME = os.environ.get('YOUR_USERNAME', '@FENIX_ON_PRIME')
UPDATES_CHANNEL = os.environ.get('UPDATES_CHANNEL', '@AuraFire95')

# Folder setup
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
UPLOAD_BOTS_DIR = os.path.join(IROTECH_DIR, 'upload_bots')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')
PENDING_ZIPS_DIR = os.path.join(IROTECH_DIR, 'pending_zips')  # persisted zip files awaiting approval

# File upload limits
FREE_USER_LIMIT = 3          # set to 0 to force users to buy/claim a plan before uploading
SUBSCRIBED_USER_LIMIT = 15   # fallback when a subscription has no plan limit stored
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')


os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)
os.makedirs(PENDING_ZIPS_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN)

# ============================================================
# --- Colorful buttons (Bot API button "style": primary=blue, success=green, danger=red) ---
# ============================================================
_STYLE_BROKEN = False
_STYLE_NAMES = ('primary', 'success', 'danger')
_ST_NONE = ('back', 'main menu', 'home', 'close', '⬅️', '🔙', '🏠', 'next ➡️', 'prev')
_ST_PRIMARY_FIRST = ('restart', '🔄', 'refresh')
_ST_DANGER = ('hide', 'clean', 'pending', 'expired', 'block', 'kill', 'purge', 'logout', 'danger', 'warning', 'clear', 'delete', 'stop', 'remove', 'reject', 'reset', 'cancel', ' ban', 'ban ', 'clear', 'disable', 'lock bot', 'decline',
              'revoke', 'wipe', '🗑', '🔴', '⛔', '🚫', '❌', '➖', '🛑')
_ST_SUCCESS = ('automatic', 'auto-', 'push', 'allow', 'unban', 'resume', 'verify', 'recover', 'restore', 'new ', 'send', 'copy', 'download', 'generate', 'bulk', 'unlock', 'start', 'approve', 'confirm', 'buy', 'pay', 'claim', 'redeem', 'enable', 'unlock', 'upload', 'get started', 'run ',
               'give', 'save', 'apply', 'accept', 'create', 'add ', 'free', 'claim', 'daily', '✅', '🟢', '➕', '🎁', '🛒', '🆓', '▶️', '📤 share')
_ST_PRIMARY = ('plan', 'stat', 'info', 'leader', 'refer', 'live', 'log', 'admin', 'setting', 'panel', 'export', 'import', 'share', 'premium',
               'point', 'speed', 'manage', 'director', 'customize', 'tool', 'search', 'find', 'list', 'history', 'report', 'install',
               'check', 'update', 'contact', 'channel', 'broadcast', 'user', 'subscription', 'method', 'preview', 'download',
               'stars', '🌐', '📱', '🏆', '📊', '💎', '⚡', '👑', '⚙️', '📡', '🔗', '📜', '🧰', '🎛', '👥', '📋', '📥', '📂', '📦', '👤', '📢', '📞', '💳', '🔍')

def _style_enabled():
    if _STYLE_BROKEN: return False
    try: return str(get_setting('BTN_COLORS', '1')) != '0'
    except Exception: return True

def _auto_style(text, cb=None):
    t = (text or '').lower()
    if any(k in t for k in _ST_NONE) and not t.startswith(('✅', '❌')): return None
    if any(k in t for k in _ST_PRIMARY_FIRST): return 'primary'
    if t.startswith('unlock') or '🔓' in t: return 'success'
    if any(k in t for k in _ST_DANGER): return 'danger'
    if any(k in t for k in _ST_SUCCESS): return 'success'
    if any(k in t for k in _ST_PRIMARY): return 'primary'
    return None

def _patch_button_class(cls):
    try:
        orig = cls.to_dict
        if getattr(orig, '_styled', False): return
    except AttributeError:
        return
    def to_dict(self, *a, **k):
        d = orig(self, *a, **k)
        try:
            if isinstance(d, dict) and 'style' not in d and _style_enabled():
                st = getattr(self, 'style', None)
                st = st if st in _STYLE_NAMES else (None if st == 'none' else _auto_style(d.get('text', ''), d.get('callback_data')))
                if st: d['style'] = st
        except Exception:
            pass
        return d
    to_dict._styled = True
    cls.to_dict = to_dict

try:
    _patch_button_class(types.InlineKeyboardButton)
    _patch_button_class(types.KeyboardButton)
    from telebot import apihelper as _api
    _orig_make_request = _api._make_request
    def _strip_styles(markup_json):
        data = json.loads(markup_json)
        def walk(o):
            if isinstance(o, dict):
                o.pop('style', None)
                for v in o.values(): walk(v)
            elif isinstance(o, list):
                for v in o: walk(v)
        walk(data); return json.dumps(data)
    def _make_request_safe(token, method_name, method='get', params=None, files=None, **kw):
        global _STYLE_BROKEN
        try:
            return _orig_make_request(token, method_name, method, params, files, **kw)
        except Exception as e:
            msg = str(e).lower()
            if params and isinstance(params.get('reply_markup'), str) and '"style"' in params['reply_markup'] and 'style' in msg:
                logger.warning("Telegram rejected button styles - retrying without colors and disabling them.")
                params = dict(params); params['reply_markup'] = _strip_styles(params['reply_markup'])
                res = _orig_make_request(token, method_name, method, params, files, **kw)
                _STYLE_BROKEN = True
                return res
            raise
    _api._make_request = _make_request_safe
except Exception as _e:
    logging.getLogger(__name__).warning(f"Colored buttons unavailable: {_e}")


# ============================================================
# --- MESSAGE EDITOR: every key bot message editable by admins + global find/replace ---
# ============================================================
import html as _hmx

class _MStr(str):
    """Text coming from the message editor (HTML). Outgoing wrappers force parse_mode=HTML for it."""

MSG_REG = {   # key: (label, default HTML, variables, sample values)
    'welcome_tagline': ("👋 Welcome · tagline", "Premium Bot Hosting · 24/7", [], {}),
    'welcome_services': ("👋 Welcome · services list (one line = one bullet)",
                         "Python, Node.js &amp; ZIP projects\nRound-the-clock uptime with live logs\nSmart automatic package installation\nPremium plans for greater capacity", [], {}),
    'welcome_footer': ("👋 Welcome · footer line", "Select an option from the menu below.", [], {}),
    'welcome_back': ("🏠 Main-menu 'Welcome back' text",
                     "✦ <b>𝗪𝗘𝗟𝗖𝗢𝗠𝗘  𝗕𝗔𝗖𝗞</b> ✦\n<i>{name}</i>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n<blockquote>🆔 ID ▸ <code>{id}</code>\n🔰 Status ▸ <b>{status}</b>{expiry}\n📁 Projects ▸ <b>{files}</b></blockquote>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n<i>◇ Choose an option from the menu below.</i>",
                     ['name', 'id', 'status', 'expiry', 'files'], {'name': 'Aryan', 'id': 12345, 'status': '⭐ PRO', 'expiry': '\n⏳ Expires in: 12 days', 'files': '1 / 5'}),
    'banned': ("🚫 Banned user message", "🚫 You are banned from using this bot.", [], {}),
    'locked': ("🔒 Bot locked message", "🔒 <b>Bot Temporarily Locked</b>\n\nThe admin has disabled the bot. Please try again later.", [], {}),
    'locked_upload': ("🔒 Locked · uploads disabled", "🔒 <b>Bot Temporarily Locked</b>\n\nFile uploads are disabled. Please try again later.", [], {}),
    'reg_closed': ("🚪 Registrations closed", "🚪 <b>Registrations are currently closed.</b>\nPlease try again later.", [], {}),
    'upload_prompt': ("📤 'Upload Your Project' prompt",
                      '✦ <b>𝗣𝗥𝗢𝗝𝗘𝗖𝗧  𝗨𝗣𝗟𝗢𝗔𝗗</b> ✦\n<i>Premium 24/7 hosting for your bots</i>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n<b>◈ ACCEPTED FORMATS</b>\n<blockquote>🐍 <code>.py</code> — Python script\n🟨 <code>.js</code> — Node.js script\n🗜 <code>.zip</code> — Complete project</blockquote>\n<b>◈ YOUR ALLOWANCE</b>\n<blockquote>Projects ▸ <b>{used} / {limit}</b>\nMax size ▸ <b>{maxmb} MB</b></blockquote>\n<b>◈ DEPLOYMENT</b>\n<blockquote>① Send your file in this chat\n② Confirm a few details\n③ Go live — running 24/7</blockquote>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n<i>◇ Dependencies from</i> <code>requirements.txt</code> <i>&amp;</i> <code>package.json</code> <i>are installed automatically.</i>', ['used', 'limit', 'maxmb'], {'used': 1, 'limit': 3, 'maxmb': 20}),
    'upload_limit': ("⚠️ Project limit reached", "⚠️ Project limit reached (<code>{used}/{limit}</code>). Delete a project or upgrade your plan.", ['used', 'limit'], {'used': 3, 'limit': 3}),
    'upload_bad_type': ("⚠️ Unsupported file type", "⚠️ Unsupported type! Only <code>.py</code>, <code>.js</code>, <code>.zip</code> allowed.", [], {}),
    'upload_too_big': ("⚠️ File too large", "⚠️ File too large (Max: {max} MB).", ['max'], {'max': 20}),
    'up_username': ("🤖 Upload · ask bot username",
                    "🤖 <b>New Upload — Bot Username</b>\n\nSend the <b>username of the bot</b> you want to host:\n• Example: <code>@MyAwesomeBot</code>\n• It must end with <code>bot</code>\n\n/cancel to abort.", [], {}),
    'up_username_bad': ("🤖 Upload · bad username", "⚠️ That doesn't look like a bot username. It must look like <code>@MyBot</code> and end with <code>bot</code>.\nTry again or /cancel.", [], {}),
    'up_project': ("📁 Upload · ask project name",
                   "📁 <b>New Upload — Project Name</b>\n\nGive this upload a project name:\n• It will appear in your control panel\n• Example: <code>MyBot</code> or <code>NotificationBot</code>\n\n/cancel to abort.", [], {}),
    'up_cancelled': ("❌ Upload cancelled", "❌ Upload cancelled.", [], {}),
    'owner_file_note': ("⬆️ Owner note: file received", "⬆️ File <code>{file}</code> from <code>{user}</code>", ['file', 'user'], {'file': 'bot.py', 'user': 12345}),
    'queued': ("✅ Project queued for review", "✅ Project <code>{project}</code> queued for review. You'll be notified upon approval.", ['project'], {'project': 'MyBot'}),
    'approved_admin': ("✅ Approved · message to admin", "✅ Project <code>{project}</code> approved for user <code>{user}</code>.", ['project', 'user'], {'project': 'MyBot', 'user': 12345}),
    'approved_user': ("✅ Approved · message to user", "✅ Your project <code>{project}</code> has been approved and started!", ['project'], {'project': 'MyBot'}),
    'zip_approved_admin': ("✅ ZIP approved · to admin", "✅ Archive for project <code>{project}</code> approved for user <code>{user}</code>.", ['project', 'user'], {'project': 'MyBot', 'user': 12345}),
    'zip_approved_user': ("✅ ZIP approved · to user", "✅ Your project <code>{project}</code> archive has been approved and is being processed...", ['project'], {'project': 'MyBot'}),
    'started_py': ("🟢 Python project started", "✅ Project <code>{project}</code> started! (PID: {pid})", ['project', 'pid'], {'project': 'MyBot', 'pid': 4242}),
    'started_js': ("🟢 Node.js project started", "✅ JS project <code>{project}</code> started! (PID: {pid})", ['project', 'pid'], {'project': 'MyBot', 'pid': 4242}),
    'contact_owner': ("📞 Contact Owner text", "✦ <b>𝗖𝗢𝗡𝗧𝗔𝗖𝗧  𝗢𝗪𝗡𝗘𝗥</b> ✦\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n<blockquote>Have a question, an issue or a suggestion?\nThe owner personally reads every message.</blockquote>\n<i>◇ Tap the button below to start a private chat.</i>", [], {}),
    'updates_channel': ("📣 Updates Channel text", "✦ <b>𝗨𝗣𝗗𝗔𝗧𝗘𝗦  𝗖𝗛𝗔𝗡𝗡𝗘𝗟</b> ✦\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n<i>Stay ahead with the official announcements</i>\n<blockquote>🆕 New features &amp; updates\n🛠 Fixes &amp; improvements\n📢 Important announcements</blockquote>\n<i>◇ Tap the button below to join.</i>", [], {}),
}

class _SafeMap(dict):
    def __missing__(self, k): return '{' + k + '}'

def _mx_custom(key):
    try: return str(get_setting('MSG_' + key, '') or '')
    except Exception: return ''

def M(key, **kw):
    """Message text for `key` (admin-edited or default), variables HTML-escaped. Returns an _MStr (HTML)."""
    reg = MSG_REG[key]
    raw = kw.pop('_raw', ())
    vals = {k: (str(v) if k in raw else _hmx.escape(str(v))) for k, v in kw.items()}
    text = _mx_custom(key)
    if text.strip():
        try: return _MStr(text.format_map(_SafeMap(vals)))
        except Exception: pass
    return _MStr(reg[1].format_map(_SafeMap(vals)))

def M_plain(key, **kw):
    """Plain-text version (tags stripped) for callback alerts etc."""
    return _hmx.unescape(re.sub(r'<[^>]+>', '', str(M(key, **kw))))

_MX_CACHE = {}
def _mx_rules():
    c = _MX_CACHE.get('r')
    if c is None:
        try:
            on = str(get_setting('MX_FR_ON', '1')) != '0'
            c = json.loads(get_setting('MX_RULES', '') or '[]') if on else []
        except Exception: c = []
        _MX_CACHE['r'] = c
    return c

def _mx_apply(text):
    if not isinstance(text, str): return text
    html_flag = isinstance(text, _MStr)
    out = str(text)
    for f, r in _mx_rules():
        if f and f in out: out = out.replace(f, r)
    return _MStr(out) if html_flag else out

def _mx_kw(text, kw):
    if isinstance(text, _MStr): kw['parse_mode'] = 'HTML'
    return kw


# ---------------- luxury styling layer (applies to every HTML / Markdown message the bot sends) ----------------
_LUX_SEP = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
def _lux_bold(t):
    out = []
    for part in re.split(r'(&\w+;)', t):
        if part.startswith('&') and part.endswith(';'): out.append(part); continue
        out.append(''.join(chr(0x1D5D4 + ord(c) - 65) if 'A' <= c <= 'Z' else chr(0x1D5EE + ord(c) - 97) if 'a' <= c <= 'z' else c for c in part))
    return ''.join(out)
def _lux_md2html(t):
    out = []
    for p in re.split(r'(`[^`\n]*`)', t):
        if len(p) > 1 and p.startswith('`') and p.endswith('`'):
            out.append('<code>' + _hmx.escape(p[1:-1], quote=False) + '</code>'); continue
        p = _hmx.escape(p, quote=False)
        p = re.sub(r'\\([_*`\[])', lambda m: '\x00' + m.group(1), p)
        p = re.sub(r'\*([^*\n]+)\*', r'<b>\1</b>', p)
        p = re.sub(r'(?<![\w])_([^_\n]+)_(?![\w])', r'<i>\1</i>', p)
        p = re.sub(r'\[([^\]\n]+)\]\((https?://[^)\s]+)\)', r'<a href="\2">\1</a>', p)
        out.append(p.replace('\x00', ''))
    return ''.join(out)
def _lux_text(text, mode):
    """Return luxury-styled HTML for `text`, or None when it should be left alone."""
    if not isinstance(text, str) or len(text) < 25 or len(text) > 3400: return None
    if '✦' in text or '<pre' in text or 'tg-emoji' in text or 'tg-spoiler' in text: return None
    t = _lux_md2html(text) if mode in ('Markdown', 'markdown') else text
    lines = t.split('\n')
    m = re.match(r'^(?:(\S+)\s+)?<b>([^<>]{2,40}?)</b>(.{0,60})$', lines[0])
    if m:
        if m.group(2).rstrip().endswith(':') and m.group(3).strip(): return None
    else:
        m = re.match(r'^\s*(?:(\S+)\s+)?()([A-Za-z][^<>\n]{2,38}?)()$', lines[0])       # plain title that is followed by a separator line
        if not m or len(lines) < 2 or not re.fullmatch(r'[━─═▬]{8,}', lines[1].strip()): return None
        m = re.match(r'^\s*(?:(\S+)\s+)?(.+?)()$', lines[0])
    nxt = lines[1].strip() if len(lines) > 1 else ''
    if nxt and not re.fullmatch(r'[━─═▬]{8,}', nxt): nxt = ''; skip = 1
    else: skip = 2
    title, tail = re.sub(r'^[^A-Za-z0-9&]+', '', m.group(2).strip()).rstrip(':').strip(), m.group(3).strip(' ·-—')
    if len(title) < 2: return None
    head = [f"✦ <b>{_lux_bold(title.upper())}</b> ✦"]
    if tail: head.append(f"<i>{tail}</i>")
    head.append(_LUX_SEP)
    body = '\n'.join(lines[skip:]).strip('\n')
    body = re.sub(r'(?m)^[━─═▬]{8,}$', _LUX_SEP, body)
    body = re.sub(r'(?m)^((?:\S+ )?)<b>([^<>\n:]{2,28}):</b>[ \t]*', r'\1\2 ▸ ', body)
    if '<blockquote' not in body:
        segs = body.split(_LUX_SEP); res = []
        for sg in segs:
            sg = sg.strip('\n')
            res.append(f"<blockquote>{sg}</blockquote>" if sg.strip() else '')
        body = f"\n{_LUX_SEP}\n".join(r for r in res if r)
    return '\n'.join(head) + ('\n' + body if body.strip() else '')
def _lux_apply(text, k):
    mode = 'HTML' if isinstance(text, _MStr) else k.get('parse_mode')
    if mode not in ('HTML', 'Markdown', 'markdown'): return text, k, None
    try: new = _lux_text(str(text), mode)
    except Exception: new = None
    if not new: return text, k, None
    k2 = dict(k); k2['parse_mode'] = 'HTML'
    return _MStr(new), k2, (text, k)
def _lux_retry(e): return 'parse entities' in str(e) or "can't parse" in str(e).lower()

def _install_message_wrappers():
    _o_send, _o_edit, _o_alert, _o_cap = bot.send_message, bot.edit_message_text, bot.answer_callback_query, bot.edit_message_caption
    def send_message(chat_id, text, *a, **k):
        k = _mx_kw(text, k); t2 = _mx_apply(text); t3, k3, orig = _lux_apply(t2, k)
        if getattr(k3.get('reply_markup'), '_adm_panel', False) and chat_id in admin_ids and chat_id != OWNER_ID: k3['reply_markup'] = k['reply_markup'] = _adm_filter_markup(k3['reply_markup'], chat_id)
        try: return _o_send(chat_id, t3, *a, **k3)
        except Exception as e:
            if orig and _lux_retry(e): return _o_send(chat_id, t2, *a, **k)
            raise
    def edit_message_text(text, *a, **k):
        k = _mx_kw(text, k); t2 = _mx_apply(text); t3, k3, orig = _lux_apply(t2, k)
        _cid = k3.get('chat_id', a[0] if a else None)
        if getattr(k3.get('reply_markup'), '_adm_panel', False) and _cid in admin_ids and _cid != OWNER_ID: k3['reply_markup'] = k['reply_markup'] = _adm_filter_markup(k3['reply_markup'], _cid)
        try: return _o_edit(t3, *a, **k3)
        except Exception as e:
            if orig and _lux_retry(e): return _o_edit(t2, *a, **k)
            raise
    def answer_callback_query(callback_query_id, text=None, *a, **k):
        if text is not None:
            text = _mx_apply(text)
            if isinstance(text, _MStr): text = _hmx.unescape(re.sub(r'<[^>]+>', '', str(text)))
        return _o_alert(callback_query_id, text, *a, **k)
    bot.send_message, bot.edit_message_text, bot.answer_callback_query = send_message, edit_message_text, answer_callback_query
_install_message_wrappers()

# ---------------- admin UI ----------------
def _mx_home(page=0):
    keys = list(MSG_REG); per = 8; pages = (len(keys) + per - 1) // per
    page = max(0, min(page, pages - 1))
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
    for k in keys[page * per:(page + 1) * per]:
        edited = bool(_mx_custom(k).strip())
        m.add(B(("✏️ " if edited else "") + MSG_REG[k][0][:50], callback_data=f"mx_v_{k}"))
    nav = []
    if page > 0: nav.append(B("⬅️ Prev", callback_data=f"mx_p_{page - 1}"))
    if page < pages - 1: nav.append(B("Next ➡️", callback_data=f"mx_p_{page + 1}"))
    if nav: m.row(*nav)
    m.row(B("🔎 Find & Replace", callback_data="mx_fr"), B("♻️ Reset All", callback_data="mx_resetall"))
    m.add(B("🔙 Admin Panel", callback_data="admin_panel"))
    n = sum(1 for k in keys if _mx_custom(k).strip())
    return (f"✏️ <b>Message Editor</b>\n━━━━━━━━━━━━━━━━━━\n{len(keys)} editable messages · <b>{n}</b> customized (✏️)\n"
            f"Page {page + 1}/{pages}\n\nPick a message to edit. Texts use <b>HTML</b> (<code>&lt;b&gt;bold&lt;/b&gt;</code>, <code>&lt;i&gt;</code>, <code>&lt;code&gt;</code>) "
            f"and <code>{{variables}}</code>.\nUse <b>Find &amp; Replace</b> to change a word in <i>every</i> message the bot sends."), m

def _mx_view(key):
    label, default, vars_, _s = MSG_REG[key]
    cur = _mx_custom(key).strip()
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=2)
    m.row(B("✏️ Edit", callback_data=f"mx_e_{key}"), B("👁 Preview", callback_data=f"mx_pv_{key}"))
    m.row(B("♻️ Reset to default", callback_data=f"mx_r_{key}"), B("🔙 Back", callback_data="mx_p_0"))
    txt = (f"✏️ <b>{_hmx.escape(label)}</b>\n━━━━━━━━━━━━━━━━━━\n<b>Current text</b> ({'custom ✏️' if cur else 'default'}):\n"
           f"<pre>{_hmx.escape(cur or default)}</pre>\n"
           + (f"<b>Variables:</b> " + " ".join(f"<code>{{{v}}}</code>" for v in vars_) if vars_ else "<i>No variables for this message.</i>"))
    return txt, m

def _mx_sample(key): return M(key, **dict(MSG_REG[key][3]))

def _mx_edit_input(message, key):
    if message.from_user.id not in admin_ids: return
    t = (message.text or '')
    if t.strip().lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    if not t.strip(): bot.reply_to(message, "❌ Empty text — nothing saved."); return
    if len(t) > 3500: bot.reply_to(message, "❌ Too long (max 3500 characters)."); return
    # keep the admin's formatting if they sent it with Telegram styling (bold/italic/links…)
    try:
        t = message.html_text if getattr(message, 'entities', None) and hasattr(message, 'html_text') and isinstance(message.html_text, str) else t
    except Exception: pass
    try: t.format_map(_SafeMap({v: '' for v in MSG_REG[key][2]}))
    except Exception:
        bot.reply_to(message, "❌ Unbalanced <code>{ }</code> — use only the listed variables like <code>{project}</code>.", parse_mode='HTML'); return
    old = _mx_custom(key); set_setting('MSG_' + key, t)
    try:
        bot.send_message(message.chat.id, _mx_sample(key))          # test: Telegram must accept it
    except Exception as e:
        set_setting('MSG_' + key, old)
        bot.reply_to(message, f"❌ Telegram rejected this text, so it was NOT saved:\n<code>{_hmx.escape(str(e))[:300]}</code>\nCheck your HTML tags are closed.", parse_mode='HTML'); return
    bot.reply_to(message, "✅ Saved! The preview above is how users will see it.")

def _mx_rule_input(message):
    if message.from_user.id not in admin_ids: return
    t = (message.text or '').strip()
    if t.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    if '=>' not in t: bot.reply_to(message, "❌ Format: <code>find =&gt; replace</code>", parse_mode='HTML'); return
    f, r = t.split('=>', 1); f, r = f.strip(), r.strip()
    if not f or len(f) > 80 or len(r) > 200: bot.reply_to(message, "❌ Find 1–80 chars, replace up to 200."); return
    try: rules = json.loads(get_setting('MX_RULES', '') or '[]')
    except Exception: rules = []
    rules = [x for x in rules if x[0] != f]
    if len(rules) >= 50: bot.reply_to(message, "❌ Max 50 rules."); return
    rules.append([f, r]); set_setting('MX_RULES', json.dumps(rules, ensure_ascii=False)); _MX_CACHE.clear()
    bot.reply_to(message, f"✅ Every <code>{_hmx.escape(f)}</code> in bot messages will now read <code>{_hmx.escape(r)}</code>.", parse_mode='HTML')

def message_editor_callback(call):
    d, chat = call.data, call.message.chat.id
    if d == 'mx_home' or d.startswith('mx_p_'):
        bot.answer_callback_query(call.id); t, m = _mx_home(int(d[5:]) if d.startswith('mx_p_') else 0); return _rp_edit(call, t, m)
    if d.startswith('mx_v_'):
        k = d[5:]
        if k not in MSG_REG: bot.answer_callback_query(call.id); return
        bot.answer_callback_query(call.id); t, m = _mx_view(k); return _rp_edit(call, t, m)
    if d.startswith('mx_e_'):
        k = d[5:]
        if k not in MSG_REG: bot.answer_callback_query(call.id); return
        bot.answer_callback_query(call.id)
        vs = MSG_REG[k][2]
        msg = bot.send_message(chat, f"✏️ Send the new text for <b>{_hmx.escape(MSG_REG[k][0])}</b>.\nHTML allowed" + (" · variables: " + " ".join(f"<code>{{{v}}}</code>" for v in vs) if vs else "") + "\n\n/cancel to abort.", parse_mode='HTML')
        bot.register_next_step_handler(msg, _mx_edit_input, k); return
    if d.startswith('mx_pv_'):
        k = d[6:]; bot.answer_callback_query(call.id)
        try: bot.send_message(chat, _mx_sample(k))
        except Exception as e: bot.send_message(chat, f"⚠️ This text has an error: {e}")
        return
    if d.startswith('mx_r_'):
        k = d[5:]
        if k in MSG_REG: set_setting('MSG_' + k, '')
        bot.answer_callback_query(call.id, "Reset to default"); t, m = _mx_view(k); return _rp_edit(call, t, m)
    if d == 'mx_resetall':
        bot.answer_callback_query(call.id); m = types.InlineKeyboardMarkup()
        m.row(types.InlineKeyboardButton("✅ Yes, reset", callback_data="mx_resetc"), types.InlineKeyboardButton("❌ Cancel", callback_data="mx_home"))
        return _rp_edit(call, "♻️ Reset <b>all</b> messages to their defaults? (Find &amp; Replace rules are kept.)", m)
    if d == 'mx_resetc':
        for k in MSG_REG: set_setting('MSG_' + k, '')
        bot.answer_callback_query(call.id, "All reset"); t, m = _mx_home(0); return _rp_edit(call, t, m)
    if d == 'mx_fr' or d.startswith('mx_frd_') or d == 'mx_frt':
        if d == 'mx_frt': set_setting('MX_FR_ON', '0' if str(get_setting('MX_FR_ON', '1')) != '0' else '1'); _MX_CACHE.clear()
        try: rules = json.loads(get_setting('MX_RULES', '') or '[]')
        except Exception: rules = []
        if d.startswith('mx_frd_'):
            try: rules.pop(int(d[7:])); set_setting('MX_RULES', json.dumps(rules, ensure_ascii=False)); _MX_CACHE.clear()
            except Exception: pass
        bot.answer_callback_query(call.id)
        on = str(get_setting('MX_FR_ON', '1')) != '0'
        B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
        m.add(B(f"Find & Replace: {'ON ✅' if on else 'OFF ❌'}", callback_data="mx_frt"))
        for i, (f, r) in enumerate(rules): m.add(B(f"🗑 {f[:22]} ➜ {r[:22]}", callback_data=f"mx_frd_{i}"))
        m.add(B("➕ Add Rule", callback_data="mx_fra"), B("🔙 Back", callback_data="mx_home"))
        return _rp_edit(call, "🔎 <b>Find &amp; Replace</b>\n━━━━━━━━━━━━━━━━━━\nChanges text in <b>every</b> message, button alert and caption the bot sends "
                              "(e.g. rename a word everywhere). Case-sensitive. Tap a rule to delete it.", m)
    if d == 'mx_fra':
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat, "➕ Send: <code>find =&gt; replace</code>\ne.g. <code>Free User =&gt; Basic Member</code>\n\n/cancel to abort.", parse_mode='HTML')
        bot.register_next_step_handler(msg, _mx_rule_input); return
    bot.answer_callback_query(call.id)

# reply_to falls back to a plain message if the original message was deleted (e.g. cleaned-up upload prompts)
_orig_reply_to = bot.reply_to
def _safe_reply_to(message, text, **kwargs):
    if getattr(message, 'message_id', 1) is None:
        return bot.send_message(message.chat.id, text, **kwargs)
    try:
        return _orig_reply_to(message, text, **kwargs)
    except Exception as _e:
        if 'replied not found' in str(_e) or 'message to be replied' in str(_e):
            return bot.send_message(message.chat.id, text, **kwargs)
        raise
bot.reply_to = _safe_reply_to
BOT_START_TIME = time.time()

# --- Data structures ---
bot_scripts = {}
user_subscriptions = {}   # {user_id: {'expiry': datetime, 'plan_name': str, 'file_limit': int|None}}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
banned_users = set()
user_limits = {}
pending_zip_files = {}
pending_script_files = {}  # {user_id: {file_name: {'path', 'type', 'is_safe', 'security_msg', 'chat_id'}}}
pending_modules = {}         # {user_id: {module_name: package_name}}
# Holds in-progress upload state while asking user for project name / main file
pending_file_uploads = {}
bot_locked = False
force_join_channels = []  # list of channels users must join before using the bot

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Command Button Layouts ---
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["📦 Manual Install", "💎 View Plans"],
    ["📡 Live Logs", "👤 My Info"],
    ["📞 Contact Owner"]
]
ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["📦 Manual Install", "💎 View Plans"],
    ["📡 Live Logs", "👑 Admin Panel"],
    ["👤 My Info", "📞 Contact Owner"]
]

# ============================================================
# --- Database Setup ---
# ============================================================
DB_LOCK = threading.Lock()

def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        # Plan info stored with each subscription (safe to run repeatedly)
        for col_sql in ("ALTER TABLE subscriptions ADD COLUMN plan_name TEXT",
                        "ALTER TABLE subscriptions ADD COLUMN file_limit INTEGER"):
            try: c.execute(col_sql)
            except Exception: pass
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, project_name TEXT, main_file TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, project_name))''')
        try:
            c.execute('SELECT main_file FROM user_files LIMIT 1')
        except Exception:
            try:
                c.execute('ALTER TABLE user_files ADD COLUMN main_file TEXT')
                c.execute('UPDATE user_files SET main_file = file_name WHERE main_file IS NULL')
                conn.commit()
            except Exception as mig_e:
                logger.warning(f"Migration attempt: {mig_e}")
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY, join_date TEXT, last_seen TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS banned_users
                     (user_id INTEGER PRIMARY KEY, reason TEXT, banned_by INTEGER, ban_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_limits
                     (user_id INTEGER PRIMARY KEY, file_limit INTEGER, set_by INTEGER, set_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS install_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      module_name TEXT,
                      package_name TEXT,
                      status TEXT,
                      log TEXT,
                      install_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings
                     (key TEXT PRIMARY KEY, value TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS force_join_channels
                     (channel TEXT PRIMARY KEY, title TEXT, invite_link TEXT, added_by INTEGER, added_at TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pending_scripts
                     (user_id INTEGER, project_name TEXT, file_path TEXT, file_type TEXT,
                      is_safe INTEGER, security_msg TEXT, chat_id INTEGER, main_file TEXT,
                      queued_at TEXT,
                      PRIMARY KEY (user_id, project_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS pending_zips
                     (user_id INTEGER, project_name TEXT, zip_path TEXT, file_name_zip TEXT,
                      main_file TEXT, patterns TEXT, queued_at TEXT,
                      PRIMARY KEY (user_id, project_name))''')
        # ---- Plans / payments (from the Plans system) ----
        c.execute('''CREATE TABLE IF NOT EXISTS plans
                     (plan_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, file_limit INTEGER,
                      price TEXT, duration INTEGER, features TEXT DEFAULT '')''')
        c.execute('''CREATE TABLE IF NOT EXISTS free_plan_claimed (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pending_payments
                     (user_id INTEGER, plan_id INTEGER, paid_amount REAL, PRIMARY KEY (user_id, plan_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS used_txids (tx_id TEXT PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS payment_methods
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, number TEXT, instructions TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS project_meta
                     (user_id INTEGER, project_name TEXT, bot_username TEXT, uploaded_at TEXT,
                      PRIMARY KEY (user_id, project_name))''')
        for _alt in ("ALTER TABLE active_users ADD COLUMN first_name TEXT", "ALTER TABLE active_users ADD COLUMN username TEXT"):
            try: c.execute(_alt)
            except sqlite3.OperationalError: pass
        c.execute('''CREATE TABLE IF NOT EXISTS button_clicks (id TEXT PRIMARY KEY, n INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS coupons
                     (code TEXT PRIMARY KEY, percent REAL, max_uses INTEGER DEFAULT 0, used INTEGER DEFAULT 0, active INTEGER DEFAULT 1)''')
        c.execute('''CREATE TABLE IF NOT EXISTS payments
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_id INTEGER, plan_name TEXT,
                      method TEXT, amount_base REAL, currency TEXT, ref TEXT, created_at TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS manual_payments
                     (rid INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_id INTEGER,
                      method_name TEXT, amount TEXT, txid TEXT, status TEXT DEFAULT 'pending',
                      created_at TEXT)''')
        for _alt in ("ALTER TABLE payment_methods ADD COLUMN kind TEXT DEFAULT 'manual'",
                     "ALTER TABLE manual_payments ADD COLUMN amount_base REAL DEFAULT 0",
                     "ALTER TABLE manual_payments ADD COLUMN photo TEXT DEFAULT ''",
                     "ALTER TABLE manual_payments ADD COLUMN coupon TEXT DEFAULT ''"):
            try: c.execute(_alt)
            except sqlite3.OperationalError: pass
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)

def load_data():
    logger.info("Loading data from database...")
    try:
        import json as _json
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT user_id, expiry, plan_name, file_limit FROM subscriptions')
        for user_id, expiry, plan_name, file_limit in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry),
                                               'plan_name': plan_name or 'PREMIUM',
                                               'file_limit': file_limit}
            except ValueError:
                logger.warning(f"⚠️ Invalid expiry for user {user_id}: {expiry}. Skipping.")
        c.execute('SELECT user_id, project_name, main_file, file_type FROM user_files')
        for user_id, project_name, main_file, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((project_name, main_file or project_name, file_type))
        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())
        try:
            c.execute('SELECT user_id FROM banned_users')
            banned_users.update(user_id for (user_id,) in c.fetchall())
        except Exception: pass
        try:
            c.execute('SELECT user_id, file_limit FROM user_limits')
            for user_id, file_limit in c.fetchall():
                user_limits[user_id] = file_limit
        except Exception: pass
        try:
            global force_join_channels
            c.execute("SELECT channel, title, invite_link FROM force_join_channels")
            force_join_channels = [
                {'channel': row[0], 'title': row[1] or row[0], 'invite_link': row[2]}
                for row in c.fetchall()
            ]
            logger.info(f"Loaded {len(force_join_channels)} force-join channel(s).")
        except Exception: pass
        try:
            c.execute('SELECT user_id, project_name, file_path, file_type, is_safe, security_msg, chat_id, main_file FROM pending_scripts')
            for uid, pname, fpath, ftype, is_safe, sec_msg, chat_id, main_file in c.fetchall():
                if not os.path.exists(fpath):
                    logger.warning(f"Pending script file missing on disk, skipping: {fpath}")
                    continue
                if uid not in pending_script_files:
                    pending_script_files[uid] = {}
                pending_script_files[uid][pname] = {
                    'path': fpath, 'type': ftype, 'is_safe': bool(is_safe),
                    'security_msg': sec_msg or '', 'chat_id': chat_id,
                    'project_name': pname, 'main_file': main_file or pname,
                }
            logger.info(f"Loaded {sum(len(v) for v in pending_script_files.values())} pending script(s) from DB.")
        except Exception as e:
            logger.warning(f"Could not load pending_scripts: {e}")
        try:
            c.execute('SELECT user_id, project_name, zip_path, file_name_zip, main_file, patterns FROM pending_zips')
            for uid, pname, zip_path, fname_zip, main_file, patterns_json in c.fetchall():
                if not os.path.exists(zip_path):
                    logger.warning(f"Pending zip file missing on disk, skipping: {zip_path}")
                    continue
                with open(zip_path, 'rb') as zf:
                    file_content = zf.read()
                patterns = _json.loads(patterns_json) if patterns_json else []
                if uid not in pending_zip_files:
                    pending_zip_files[uid] = {}
                pending_zip_files[uid][pname] = {
                    'content': file_content, 'patterns': patterns,
                    'file_name_zip': fname_zip or f"{pname}.zip",
                    'project_name': pname, 'main_file': main_file,
                }
            logger.info(f"Loaded {sum(len(v) for v in pending_zip_files.values())} pending zip(s) from DB.")
        except Exception as e:
            logger.warning(f"Could not load pending_zips: {e}")
        conn.close()
        logger.info(f"Data loaded: {len(active_users)} users, {len(user_subscriptions)} subs, {len(admin_ids)} admins, {len(banned_users)} banned.")
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}", exc_info=True)

# ============================================================
# --- Small DB helpers (used by the Plans system) ---
# ============================================================
def _db_q(sql, params=(), one=False):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            c = conn.cursor()
            c.execute(sql, params)
            return c.fetchone() if one else c.fetchall()
        finally:
            conn.close()

def _db_exec(sql, params=()):
    """Run a write query. Returns (rowcount, lastrowid)."""
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            c = conn.cursor()
            c.execute(sql, params)
            conn.commit()
            return c.rowcount, c.lastrowid
        finally:
            conn.close()

def get_setting(key, default=None):
    row = _db_q("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return row[0] if row else default

def set_setting(key, value):
    _db_exec("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

# ============================================================
# --- Helper Functions ---
# ============================================================
def md_escape(text):
    """Escape special Markdown v1 characters in dynamic text before sending."""
    for ch in ['\\', '`', '*', '_', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        text = str(text).replace(ch, f'\\{ch}')
    return text

def _md(text):
    """Escape only the characters that matter for legacy Markdown (user-provided text)."""
    s = str(text)
    for ch in ('_', '*', '`', '['):
        s = s.replace(ch, '\\' + ch)
    return s

def get_user_folder(user_id, project_name=None):
    if project_name:
        user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id), str(project_name))
    else:
        user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def has_active_sub(user_id):
    sub = user_subscriptions.get(user_id)
    return bool(sub and sub.get('expiry') and sub['expiry'] > datetime.now())

def get_plan_label(user_id):
    """Name of the user's active plan (falls back to 'Premium')."""
    sub = user_subscriptions.get(user_id) or {}
    return str(sub.get('plan_name') or 'Premium')

def get_user_file_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_limits: return user_limits[user_id]
    if has_active_sub(user_id):
        return user_subscriptions[user_id].get('file_limit') or SUBSCRIBED_USER_LIMIT
    return get_free_limit()

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def is_user_banned(user_id):
    return user_id in banned_users

# ============================================================
# --- Force Join Channel Helpers ---
# ============================================================
def add_force_join_channel_db(channel, title, invite_link, added_by):
    """Add a channel to the mandatory join list."""
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO force_join_channels (channel, title, invite_link, added_by, added_at) VALUES (?, ?, ?, ?, ?)",
                (channel, title, invite_link, added_by, datetime.now().isoformat())
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Error adding force_join channel {channel}: {e}")
        finally:
            conn.close()

def remove_force_join_channel_db(channel):
    """Remove a specific channel from the mandatory join list."""
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            conn.execute("DELETE FROM force_join_channels WHERE channel = ?", (channel,))
            conn.commit()
        except Exception as e:
            logger.error(f"Error removing force_join channel {channel}: {e}")
        finally:
            conn.close()

def is_user_in_channel(user_id, channel):
    """Return True if user has joined the given channel."""
    try:
        member = bot.get_chat_member(channel, user_id)
        return member.status in ('member', 'administrator', 'creator')
    except Exception:
        return False

def check_force_join(message):
    """
    Check that the user has joined ALL mandatory channels.
    Returns False if the user fails the check, True otherwise.
    Only the Owner is exempt.
    """
    if not force_join_channels:
        return True
    user_id = message.from_user.id
    if user_id == OWNER_ID:
        return True

    unjoined = [e for e in force_join_channels if not is_user_in_channel(user_id, e['channel'])]
    if not unjoined:
        return True

    markup = types.InlineKeyboardMarkup(row_width=1)
    for e in unjoined:
        url = e.get('invite_link') or (f"https://t.me/{e['channel'].lstrip('@')}" if e['channel'].startswith('@') else None)
        if url:
            markup.add(types.InlineKeyboardButton(f"📢 Join {e['title']}", url=url))
        else:
            markup.add(types.InlineKeyboardButton(f"📢 {e['title']} (contact admin for link)", callback_data='noop'))
    markup.add(types.InlineKeyboardButton("✅ I've Joined All", callback_data="check_joined"))

    if len(unjoined) == 1:
        text = (f"⚠️ *Access Restricted!*\n\n"
                f"You must join this channel to use this bot:\n"
                f"› *{unjoined[0]['title']}*\n\n"
                f"👇 Join and press *I've Joined All*:")
    else:
        ch_list = '\n'.join(f"› *{e['title']}*" for e in unjoined)
        text = (f"⚠️ *Access Restricted!*\n\n"
                f"You must join *all* of these channels to use this bot:\n\n"
                f"{ch_list}\n\n"
                f"👇 Join all and press *I've Joined All*:")

    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)
    return False

def is_bot_running(script_owner_id, project_name):
    script_key = f"{script_owner_id}_{project_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            is_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            if not is_running:
                if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                    try: script_info['log_file'].close()
                    except Exception: pass
                if script_key in bot_scripts: del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                try: script_info['log_file'].close()
                except Exception: pass
            if script_key in bot_scripts: del bot_scripts[script_key]
            return False
        except Exception as e:
            logger.error(f"Error checking process status for {script_key}: {e}")
            return False
    return False

def kill_process_tree(process_info):
    pid = None
    script_key = process_info.get('script_key', 'N/A')
    try:
        if 'log_file' in process_info and hasattr(process_info['log_file'], 'close') and not process_info['log_file'].closed:
            try: process_info['log_file'].close()
            except Exception as log_e: logger.error(f"Error closing log file for {script_key}: {log_e}")
        process = process_info.get('process')
        if process and hasattr(process, 'pid'):
            pid = process.pid
            if pid:
                try:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                    for child in children:
                        try: child.terminate()
                        except psutil.NoSuchProcess: pass
                        except Exception:
                            try: child.kill()
                            except Exception: pass
                    gone, alive = psutil.wait_procs(children, timeout=1)
                    for p in alive:
                        try: p.kill()
                        except Exception: pass
                    try:
                        parent.terminate()
                        try: parent.wait(timeout=1)
                        except psutil.TimeoutExpired: parent.kill()
                    except psutil.NoSuchProcess: pass
                    except Exception:
                        try: parent.kill()
                        except Exception: pass
                except psutil.NoSuchProcess: pass
    except Exception as e:
        logger.error(f"❌ Unexpected error killing process tree for PID {pid} ({script_key}): {e}", exc_info=True)

# ============================================================
# --- Security / Dangerous Pattern Detection ---
# ============================================================
SECURITY_SCORE_THRESHOLD = 10

CRITICAL_PATTERNS = [
    (r'\bos\.system\s*\(',                              10, "os.system() shell execution"),
    (r'\bsubprocess\.(Popen|call|run|check_output|getoutput|getstatusoutput)\s*\(', 10, "subprocess shell execution"),
    (r'\beval\s*\(',                                    10, "eval() code execution"),
    (r'\bexec\s*\(',                                    10, "exec() code execution"),
    (r'\b__import__\s*\(',                              10, "dynamic __import__()"),
    (r'rm\s+-rf\s+[/~\.\*]',                            10, "destructive rm -rf"),
    (r'/bin/(sh|bash|zsh|dash)',                        10, "shell binary reference"),
    (r'nc\s+-[elp]',                                    10, "netcat flag (reverse shell)"),
    (r'\bnetcat\b',                                     10, "netcat usage"),
    (r'\bshellcode\b',                                  10, "shellcode reference"),
    (r'\bmetasploit\b',                                 10, "metasploit framework"),
    (r'\brootkit\b',                                    10, "rootkit reference"),
    (r'\bbackdoor\b',                                   10, "backdoor reference"),
    (r'/etc/shadow',                                    10, "shadow password file"),
    (r'/etc/passwd',                                    10, "passwd file access"),
    (r'\bid_rsa\b',                                     10, "SSH private key"),
    (r'\bauthorized_keys\b',                            10, "SSH authorized_keys"),
    (r'\bdd\s+(if=/dev/(zero|random)|of=/dev/sda)',     10, "disk destruction"),
    (r'wget\s+.*\|\s*(bash|sh)',                        10, "remote code exec via wget"),
    (r'curl\s+.*\|\s*(bash|sh)',                        10, "remote code exec via curl"),
    (r'\bos\.(remove|unlink)\s*\(',                     10, "file deletion via os"),
    (r'\bos\.(popen|fork|execv|execvp|spawnl)\s*\(',    10, "os process spawning"),
    (r'shutil\.rmtree\s*\(',                            10, "recursive directory removal"),
    (r'\bwin32api\b|\bwin32com\b|\bwin32process\b',     10, "Windows API abuse"),
    (r'\bGetAsyncKeyState\b|\bSetWindowsHookEx\b',      10, "Windows keystroke hook"),
]

OBFUSCATION_PATTERNS = [
    (r'base64\.b64decode',   8, "base64 decode (obfuscation)"),
    (r'(?<!re\.)(?<!pattern\.)(?<!\.)(?<![a-zA-Z_]re)\bcompile\s*\(', 8, "dynamic compile() call"),
    (r'marshal\.loads',      8, "marshal deserialization"),
    (r'zlib\.decompress',    8, "zlib decompression (obfuscation)"),
]

HIGH_RISK_PATTERNS = [
    (r'\bparamiko\b',                   5, "SSH/SFTP library"),
    (r'\bnmap\b',                       5, "network scanner"),
    (r'\bscapy\b',                      5, "packet manipulation"),
    (r'\bpynput\b',                     5, "keylogger library"),
    (r'\bpyautogui\b',                  5, "screen automation/capture"),
    (r'\bpyscreenshot\b|\bImageGrab\b', 5, "screen capture"),
    (r'\bptrace\b',                     5, "process tracing (anti-debug)"),
    (r'\bmmap\b',                       5, "memory mapping"),
    (r'VirtualAlloc|VirtualProtect|HeapAlloc', 5, "memory manipulation"),
    (r'\bimportlib\b',                  5, "dynamic module loading"),
    (r'\bpickle\.loads\b',              5, "unsafe pickle deserialization"),
    (r'\bcPickle\b',                    5, "unsafe cPickle"),
    (r'\bftplib\b',                     5, "FTP library"),
    (r'nc\s+.*\s+-[0-9]',              5, "netcat connection"),
    (r'\bschtasks\b|\btaskkill\b',      5, "Windows task manipulation"),
    (r'\bchattr\b',                     5, "file attribute manipulation"),
]

MEDIUM_RISK_PATTERNS = [
    (r'\bsocket\.socket\s*\(',  2, "raw socket creation"),
    (r'\bos\.environ\b',        2, "environment variable access"),
    (r'\.ssh/',                 2, "SSH directory reference"),
    (r'\bgetpass\b',            2, "password input"),
    (r'\bcrontab\b',            2, "crontab manipulation"),
    (r'\bsystemctl\b',          2, "systemctl service control"),
    (r'chmod\s+777|chmod\s+\+x',2, "permissive chmod"),
    (r'\bwhoami\b',             2, "system identity query"),
    (r'/proc/',                 2, "procfs access"),
    (r'\bsudo\b',               2, "sudo privilege escalation"),
    (r'\busermod\b|\badduser\b|\bdeluser\b', 2, "user account manipulation"),
]

DANGEROUS_PATTERNS = (
    [p for p, _, _ in CRITICAL_PATTERNS] +
    [p for p, _, _ in OBFUSCATION_PATTERNS] +
    [p for p, _, _ in HIGH_RISK_PATTERNS] +
    [p for p, _, _ in MEDIUM_RISK_PATTERNS]
)

_ALL_SCORED_PATTERNS = CRITICAL_PATTERNS + OBFUSCATION_PATTERNS + HIGH_RISK_PATTERNS + MEDIUM_RISK_PATTERNS

def scan_code_security(content):
    """Scored security scan. Returns (matched_labels, total_score)."""
    matched_labels = []
    total_score = 0
    seen_patterns = set()
    for pattern, score, label in _ALL_SCORED_PATTERNS:
        if pattern in seen_patterns:
            continue
        if re.search(pattern, content, re.IGNORECASE):
            seen_patterns.add(pattern)
            matched_labels.append(label)
            total_score += score
    return matched_labels, total_score

def check_code_security(file_path, file_type='py'):
    """Scan a script file. Returns (is_safe, message)."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        labels, score = scan_code_security(content)
        if score >= SECURITY_SCORE_THRESHOLD:
            logger.warning(f"🚨 Security score {score} in {file_path}: {labels[:5]}")
            return False, f"⚠️ Risk score: {score}/10 — Detected: {', '.join(labels[:3])}"
        return True, "✅ Code passed security scan"
    except Exception as e:
        logger.error(f"Error in security check: {e}")
        return False, f"Security check error: {str(e)}"

def scan_zip_file(zip_path):
    """Deep scan all .py/.js files inside a ZIP. Returns list of (filename, labels, score)."""
    findings = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            for file in z.namelist():
                if file.endswith(('.py', '.js')):
                    try:
                        content = z.read(file).decode('utf-8', errors='ignore')
                    except Exception:
                        continue
                    labels, score = scan_code_security(content)
                    if score >= SECURITY_SCORE_THRESHOLD:
                        findings.append((file, labels, score))
    except Exception as e:
        logger.error(f"Error in ZIP deep scan: {e}")
    return findings

def scan_zip_security(zip_path):
    """Scan ZIP contents. Returns (is_safe, message)."""
    try:
        findings = scan_zip_file(zip_path)
        if findings:
            first_file, labels, score = findings[0]
            return False, (f"⚠️ '{first_file}' — Risk score: {score} — "
                           f"Detected: {', '.join(labels[:3])}")
        return True, "✅ Archive passed security scan"
    except Exception as e:
        return False, f"Error scanning archive: {str(e)}"

# ============================================================
# --- Sandboxed Environment for User Scripts ---
# ============================================================
def get_clean_env():
    env = os.environ.copy()
    env["HOME"] = os.environ.get("HOME", "/data/data/com.termux/files/home")
    env["LANG"] = "en_US.UTF-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env

# ============================================================
# --- Manual Module Installation System ---
# ============================================================
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI', 'telegram': 'python-telegram-bot',
    'python_telegram_bot': 'python-telegram-bot', 'aiogram': 'aiogram',
    'pyrogram': 'pyrogram', 'telethon': 'telethon', 'telethon.sync': 'telethon',
    'telepot': 'telepot', 'tgcrypto': 'tgcrypto', 'telegram_upload': 'telegram-upload',
    'telegram_send': 'telegram-send', 'tl': 'telethon',
    'bs4': 'beautifulsoup4', 'requests': 'requests', 'pillow': 'Pillow', 'PIL': 'Pillow',
    'cv2': 'opencv-python', 'yaml': 'PyYAML', 'dotenv': 'python-dotenv',
    'dateutil': 'python-dateutil', 'pandas': 'pandas', 'numpy': 'numpy', 'flask': 'Flask',
    'django': 'Django', 'sqlalchemy': 'SQLAlchemy', 'aiohttp': 'aiohttp', 'httpx': 'httpx',
    'psutil': 'psutil', 'pymongo': 'pymongo', 'redis': 'redis', 'celery': 'celery',
    'pydantic': 'pydantic', 'fastapi': 'fastapi', 'uvicorn': 'uvicorn',
    'cryptography': 'cryptography', 'paramiko': 'paramiko', 'qrcode': 'qrcode',
    'barcode': 'python-barcode', 'schedule': 'schedule', 'apscheduler': 'APScheduler',
    'pytz': 'pytz', 'motor': 'motor', 'aiosqlite': 'aiosqlite',
}
# Core modules — value None means "skip installation"
_CORE_MODULES = (
    'asyncio json datetime os sys re time math random logging threading subprocess zipfile '
    'tempfile shutil sqlite3 atexit pathlib collections itertools functools typing abc copy io '
    'struct hashlib hmac base64 urllib http socket ssl uuid enum dataclasses contextlib traceback '
    'inspect gc weakref signal platform glob fnmatch stat pickle csv configparser argparse string '
    'textwrap unicodedata html xml'
).split()
TELEGRAM_MODULES.update({m: None for m in _CORE_MODULES})

def save_install_log(user_id, module_name, package_name, status, log):
    """Save installation log to database."""
    try:
        _db_exec('INSERT INTO install_logs (user_id, module_name, package_name, status, log, install_date) VALUES (?, ?, ?, ?, ?, ?)',
                 (user_id, module_name, package_name, status, log, datetime.now().isoformat()))
    except Exception as e:
        logger.error(f"❌ Error saving install log: {e}")

def attempt_install_pip(module_name, message, manual_request=False):
    """Install a Python package via pip."""
    package_name = TELEGRAM_MODULES.get(module_name.lower(), module_name)
    if package_name is None:
        bot.reply_to(message, f"ℹ️ `{module_name}` is a core Python module — no installation needed.", parse_mode='Markdown')
        return False, "Core module"
    try:
        prefix = "🔄 Manual install" if manual_request else "🐍 Auto-installing"
        bot.reply_to(message, f"{prefix}: `{module_name}` → `{package_name}`...", parse_mode='Markdown')
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', package_name],
                                capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            log_msg = f"Installed {package_name}.\n{result.stdout}"
            bot.reply_to(message, f"✅ `{package_name}` installed successfully!", parse_mode='Markdown')
            save_install_log(message.from_user.id, module_name, package_name, "success", log_msg)
            return True, log_msg
        else:
            err = (result.stderr or result.stdout)[:3000]
            error_msg = f"❌ Failed to install `{package_name}`.\n```\n{err}\n```"
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            save_install_log(message.from_user.id, module_name, package_name, "failed", error_msg)
            return False, error_msg
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        bot.reply_to(message, error_msg)
        save_install_log(message.from_user.id, module_name, package_name, "error", error_msg)
        return False, error_msg

def attempt_install_npm(module_name, user_folder, message, manual_request=False):
    """Install a Node.js package via npm."""
    try:
        prefix = "🔄 Manual install" if manual_request else "🟠 Auto-installing"
        bot.reply_to(message, f"{prefix} Node package: `{module_name}`...", parse_mode='Markdown')
        result = subprocess.run(['npm', 'install', module_name], capture_output=True, text=True,
                                check=False, cwd=user_folder, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            log_msg = f"Installed {module_name}.\n{result.stdout}"
            bot.reply_to(message, f"✅ Node package `{module_name}` installed!", parse_mode='Markdown')
            save_install_log(message.from_user.id, module_name, module_name, "success", log_msg)
            return True, log_msg
        else:
            err = (result.stderr or result.stdout)[:3000]
            error_msg = f"❌ Failed to install `{module_name}`.\n```\n{err}\n```"
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            save_install_log(message.from_user.id, module_name, module_name, "failed", error_msg)
            return False, error_msg
    except FileNotFoundError:
        error_msg = "❌ `npm` not found. Make sure Node.js is installed."
        bot.reply_to(message, error_msg, parse_mode='Markdown')
        save_install_log(message.from_user.id, module_name, module_name, "error", error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        bot.reply_to(message, error_msg)
        save_install_log(message.from_user.id, module_name, module_name, "error", error_msg)
        return False, error_msg

# ============================================================
# --- Dependency Auto-Install Helpers ---
# ============================================================
def _dep_file_hash(file_path):
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()

def _dep_marker_path(user_folder, marker_name):
    folder_key = hashlib.sha256(user_folder.encode()).hexdigest()[:16]
    marker_dir = os.path.join(user_folder, ".deps_cache", folder_key)
    os.makedirs(marker_dir, exist_ok=True)
    return os.path.join(marker_dir, marker_name)

def _dep_read_marker(marker_path):
    try:
        with open(marker_path, 'r') as f:
            return f.read().strip()
    except Exception:
        return None

def _dep_write_marker(marker_path, hash_value):
    try:
        with open(marker_path, 'w') as f:
            f.write(hash_value)
    except Exception as e:
        logger.warning(f"Could not write dep marker {marker_path}: {e}")

def install_requirements_if_present(user_folder, user_id, message_obj):
    """Install packages from requirements.txt if present (skips when unchanged)."""
    req_path = os.path.join(user_folder, 'requirements.txt')
    if not os.path.exists(req_path):
        return True
    current_hash = _dep_file_hash(req_path)
    marker_path = _dep_marker_path(user_folder, 'pip_deps_hash')
    if _dep_read_marker(marker_path) == current_hash:
        logger.info(f"pip deps unchanged for user {user_id} – skipping install.")
        return True
    try:
        bot.reply_to(message_obj, "🔄 Installing dependencies from `requirements.txt`...", parse_mode='Markdown')
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-r', req_path],
            capture_output=True, text=True, check=False,
            encoding='utf-8', errors='ignore', env=get_clean_env()
        )
        if result.returncode == 0:
            _dep_write_marker(marker_path, current_hash)
            bot.reply_to(message_obj, "✅ Dependencies from `requirements.txt` installed successfully.", parse_mode='Markdown')
            return True
        err = (result.stderr or result.stdout)[:1500]
        bot.reply_to(message_obj, f"❌ Failed to install `requirements.txt` dependencies:\n```\n{err}\n```", parse_mode='Markdown')
        return False
    except Exception as e:
        logger.error(f"install_requirements_if_present error for {user_id}: {e}")
        bot.reply_to(message_obj, f"❌ Error installing `requirements.txt` dependencies: {e}", parse_mode='Markdown')
        return False

def install_package_json_if_present(user_folder, user_id, message_obj):
    """Run npm install if package.json is present (skips when unchanged)."""
    pkg_path = os.path.join(user_folder, 'package.json')
    if not os.path.exists(pkg_path):
        return True
    current_hash = _dep_file_hash(pkg_path)
    marker_path = _dep_marker_path(user_folder, 'npm_deps_hash')
    if _dep_read_marker(marker_path) == current_hash:
        logger.info(f"npm deps unchanged for user {user_id} – skipping install.")
        return True
    try:
        bot.reply_to(message_obj, "🔄 Installing Node.js dependencies from `package.json`...", parse_mode='Markdown')
        result = subprocess.run(
            ['npm', 'install'],
            capture_output=True, text=True, check=False,
            cwd=user_folder, encoding='utf-8', errors='ignore', env=get_clean_env()
        )
        if result.returncode == 0:
            _dep_write_marker(marker_path, current_hash)
            bot.reply_to(message_obj, "✅ Node.js dependencies installed successfully.", parse_mode='Markdown')
            return True
        err = (result.stderr or result.stdout)[:1500]
        bot.reply_to(message_obj, f"❌ Failed to install Node.js dependencies:\n```\n{err}\n```", parse_mode='Markdown')
        return False
    except FileNotFoundError:
        bot.reply_to(message_obj, "❌ `npm` not found. Install Node.js on the server.", parse_mode='Markdown')
        return False
    except Exception as e:
        logger.error(f"install_package_json_if_present error for {user_id}: {e}")
        bot.reply_to(message_obj, f"❌ Error installing Node.js dependencies: {e}", parse_mode='Markdown')
        return False

def auto_install_py_imports(script_path, user_folder, user_id, message_obj):
    """Scan a .py file for imports, install missing third-party packages and persist requirements.txt."""
    try:
        with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return

    import_names = set()
    for m in re.finditer(r'^\s*import\s+([\w\.]+)', content, re.MULTILINE):
        import_names.add(m.group(1).split('.')[0])
    for m in re.finditer(r'^\s*from\s+([\w\.]+)\s+import', content, re.MULTILINE):
        name = m.group(1).split('.')[0]
        if name not in ('__future__',):
            import_names.add(name)

    all_packages = []
    to_install = []
    for mod in import_names:
        if mod in TELEGRAM_MODULES:
            if TELEGRAM_MODULES[mod] is None:
                continue
            pkg = TELEGRAM_MODULES[mod]
        else:
            pkg = mod
        if not pkg:
            continue
        if pkg not in all_packages:
            all_packages.append(pkg)
        try:
            __import__(mod)
        except ImportError:
            if pkg not in to_install:
                to_install.append(pkg)
        except Exception:
            pass

    if all_packages:
        req_path = os.path.join(user_folder, 'requirements.txt')
        try:
            existing = set()
            if os.path.exists(req_path):
                with open(req_path, 'r', encoding='utf-8') as f:
                    existing = {line.strip() for line in f if line.strip()}
            merged = sorted(existing | set(all_packages))
            with open(req_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(merged) + '\n')
            logger.info(f"requirements.txt written for user {user_id} in {user_folder}: {merged}")
        except Exception as e:
            logger.warning(f"Could not write requirements.txt for user {user_id}: {e}")

    if not to_install:
        return

    bot.reply_to(message_obj, f"📦 *Auto-installing missing packages:* `{', '.join(to_install)}`...", parse_mode='Markdown')
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install'] + to_install,
            capture_output=True, text=True, check=False,
            encoding='utf-8', errors='ignore', env=get_clean_env()
        )
        if result.returncode == 0:
            bot.reply_to(message_obj, f"✅ Auto-installed: `{', '.join(to_install)}`", parse_mode='Markdown')
        else:
            err = (result.stderr or result.stdout)[:1000]
            bot.reply_to(message_obj, f"⚠️ Some packages may not have installed:\n```\n{err}\n```", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"auto_install_py_imports error for {user_id}: {e}")

def auto_install_js_requires(script_path, user_folder, user_id, message_obj):
    """Scan a .js file for require() calls, write package.json and install missing npm packages."""
    import json as _json
    NODE_BUILTINS = set((
        'fs path readline stream string_decoder tty buffer http http2 https net dgram dns tls url '
        'querystring punycode process os child_process cluster worker_threads timers perf_hooks '
        'trace_events sys signal crypto util assert events module repl vm v8 domain console '
        'constants zlib'
    ).split())
    try:
        with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return

    requires = set()
    for m in re.finditer(r'''require\s*\(\s*['"](@?[^'"./][^'"]*)['"]\s*\)''', content):
        raw = m.group(1)
        if raw.startswith('@'):
            parts = raw.split('/')
            pkg = '/'.join(parts[:2]) if len(parts) >= 2 else parts[0]
        else:
            pkg = raw.split('/')[0]
        if pkg not in NODE_BUILTINS:
            requires.add(pkg)

    if not requires:
        return

    pkg_json_path = os.path.join(user_folder, 'package.json')
    try:
        if os.path.exists(pkg_json_path):
            with open(pkg_json_path, 'r', encoding='utf-8') as f:
                pkg_data = _json.load(f)
        else:
            pkg_data = {
                "name": re.sub(r'[^\w\-]', '_', os.path.basename(user_folder))[:40],
                "version": "1.0.0",
                "description": "Auto-generated by FENIX HOSTING BOT",
                "dependencies": {}
            }
        deps = pkg_data.setdefault('dependencies', {})
        for pkg in requires:
            if pkg not in deps:
                deps[pkg] = "*"
        with open(pkg_json_path, 'w', encoding='utf-8') as f:
            _json.dump(pkg_data, f, indent=2)
        logger.info(f"package.json written for user {user_id} in {user_folder}: {list(requires)}")
    except Exception as e:
        logger.warning(f"Could not write package.json for user {user_id}: {e}")

    to_install = []
    for pkg in requires:
        check = subprocess.run(['node', '-e', f'require("{pkg}")'],
                               capture_output=True, cwd=user_folder, env=get_clean_env())
        if check.returncode != 0:
            to_install.append(pkg)

    if not to_install:
        return

    bot.reply_to(message_obj, f"📦 *Auto-installing npm packages:* `{', '.join(to_install)}`...", parse_mode='Markdown')
    try:
        result = subprocess.run(
            ['npm', 'install'] + to_install,
            capture_output=True, text=True, check=False,
            cwd=user_folder, encoding='utf-8', errors='ignore', env=get_clean_env()
        )
        if result.returncode == 0:
            bot.reply_to(message_obj, f"✅ Auto-installed npm: `{', '.join(to_install)}`", parse_mode='Markdown')
        else:
            err = (result.stderr or result.stdout)[:1000]
            bot.reply_to(message_obj, f"⚠️ Some npm packages may not have installed:\n```\n{err}\n```", parse_mode='Markdown')
    except FileNotFoundError:
        bot.reply_to(message_obj, "❌ `npm` not found. Install Node.js on the server.", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"auto_install_js_requires error for {user_id}: {e}")

def manual_install_module_init(message):
    """Entry point for the 📦 Manual Install feature."""
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, M('banned')); return
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot is locked by admin. Try again later."); return
    msg = bot.reply_to(message,
        "✦ <b>𝗠𝗔𝗡𝗨𝗔𝗟  𝗜𝗡𝗦𝗧𝗔𝗟𝗟𝗘𝗥</b> ✦\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "<i>Send the name of the module you want to install.</i>\n"
        "<blockquote>🐍 <b>Python</b> ▸ <code>requests</code> · <code>pillow</code> · <code>numpy</code>\n"
        "🟨 <b>Node.js</b> ▸ <code>npm:express</code> · <code>npm:axios</code></blockquote>\n"
        "<i>◇ Send /cancel to abort.</i>",
        parse_mode='HTML')
    bot.register_next_step_handler(msg, process_manual_install_module)

def process_manual_install_module(message):
    """Process the module name sent by user and run installation."""
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned."); return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Installation cancelled."); return
    module_name = (message.text or '').strip()
    if not module_name:
        bot.reply_to(message, "⚠️ Please send a valid module name."); return
    if not re.fullmatch(r'(npm:)?[A-Za-z0-9_.\-\[\]=<>~!,@/]+', module_name):
        # looks like a menu button / command, not a module name -> leave install mode and handle it normally
        try: bot.process_new_messages([message])
        except Exception as e: logger.warning(f"manual install redispatch failed: {e}")
        return
    if module_name.lower().startswith('npm:'):
        module_name = module_name[4:].strip()
        user_folder = get_user_folder(user_id)
        attempt_install_npm(module_name, user_folder, message, manual_request=True)
    else:
        attempt_install_pip(module_name, message, manual_request=True)

def _logic_manual_install(message):
    manual_install_module_init(message)

# ============================================================
# --- Database Operations ---
# ============================================================
def save_user_file(user_id, project_name, main_file, file_type='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files (user_id, project_name, main_file, file_type) VALUES (?, ?, ?, ?)',
                      (user_id, project_name, main_file, file_type))
            conn.commit()
            if user_id not in user_files: user_files[user_id] = []
            user_files[user_id] = [(pn, mf, ft) for pn, mf, ft in user_files[user_id] if pn != project_name]
            user_files[user_id].append((project_name, main_file, file_type))
        except Exception as e: logger.error(f"❌ Error saving file for {user_id}: {e}")
        finally: conn.close()

def remove_user_file_db(user_id, project_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id = ? AND project_name = ?', (user_id, project_name))
            c.execute('DELETE FROM project_meta WHERE user_id = ? AND project_name = ?', (user_id, project_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != project_name]
                if not user_files[user_id]: del user_files[user_id]
        except Exception as e: logger.error(f"❌ Error removing file for {user_id}: {e}")
        finally: conn.close()

def update_main_file_db(user_id, project_name, new_main_file):
    """Update the main file for an existing project."""
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('UPDATE user_files SET main_file = ? WHERE user_id = ? AND project_name = ?',
                      (new_main_file, user_id, project_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [
                    (pn, new_main_file if pn == project_name else mf, ft)
                    for pn, mf, ft in user_files[user_id]
                ]
            return True
        except Exception as e:
            logger.error(f"❌ Error updating main file for {user_id}/{project_name}: {e}")
            return False
        finally:
            conn.close()

def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            join_date = datetime.now().isoformat()
            c.execute('INSERT OR REPLACE INTO active_users (user_id, join_date, last_seen) VALUES (?, ?, ?)',
                      (user_id, join_date, join_date))
            conn.commit()
        except Exception as e: logger.error(f"❌ Error adding active user {user_id}: {e}")
        finally: conn.close()

def save_subscription(user_id, expiry, plan_name=None, file_limit=None):
    """Save a subscription. Plan name / limit are kept from the old record when not given."""
    cur = user_subscriptions.get(user_id) or {}
    if plan_name is None: plan_name = cur.get('plan_name') or 'PREMIUM'
    if file_limit is None: file_limit = cur.get('file_limit')
    try:
        _db_exec('INSERT OR REPLACE INTO subscriptions (user_id, expiry, plan_name, file_limit) VALUES (?, ?, ?, ?)',
                 (user_id, expiry.isoformat(), plan_name, file_limit))
        user_subscriptions[user_id] = {'expiry': expiry, 'plan_name': plan_name, 'file_limit': file_limit}
    except Exception as e: logger.error(f"❌ Error saving sub for {user_id}: {e}")

def remove_subscription_db(user_id):
    try:
        _db_exec('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
        if user_id in user_subscriptions: del user_subscriptions[user_id]
    except Exception as e: logger.error(f"❌ Error removing sub for {user_id}: {e}")

def add_admin_db(admin_id):
    try:
        _db_exec('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (admin_id,))
        admin_ids.add(admin_id)
    except Exception as e: logger.error(f"❌ Error adding admin {admin_id}: {e}")
    return True

def remove_admin_db(admin_id):
    if admin_id == OWNER_ID:
        logger.warning("Attempted to remove OWNER_ID from admins.")
        return False
    try:
        row = _db_q('SELECT 1 FROM admins WHERE user_id = ?', (admin_id,), one=True)
        if row:
            rc, _ = _db_exec('DELETE FROM admins WHERE user_id = ?', (admin_id,))
            if rc > 0: admin_ids.discard(admin_id)
            return rc > 0
        admin_ids.discard(admin_id)
        return False
    except Exception as e: logger.error(f"❌ Error removing admin {admin_id}: {e}"); return False

def ban_user_db(user_id, reason, banned_by):
    try:
        _db_exec('INSERT OR REPLACE INTO banned_users (user_id, reason, banned_by, ban_date) VALUES (?, ?, ?, ?)',
                 (user_id, reason, banned_by, datetime.now().isoformat()))
        banned_users.add(user_id)
        logger.info(f"Banned user {user_id} by {banned_by}. Reason: {reason}")
        return True
    except Exception as e: logger.error(f"❌ Error banning user {user_id}: {e}"); return False

def unban_user_db(user_id):
    try:
        _db_exec('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
        banned_users.discard(user_id)
        logger.info(f"Unbanned user {user_id}")
        return True
    except Exception as e: logger.error(f"❌ Error unbanning user {user_id}: {e}"); return False

def set_user_limit_db(user_id, file_limit, set_by):
    try:
        _db_exec('INSERT OR REPLACE INTO user_limits (user_id, file_limit, set_by, set_date) VALUES (?, ?, ?, ?)',
                 (user_id, file_limit, set_by, datetime.now().isoformat()))
        user_limits[user_id] = file_limit
        return True
    except Exception as e: logger.error(f"❌ Error setting limit for {user_id}: {e}"); return False

def remove_user_limit_db(user_id):
    try:
        _db_exec('DELETE FROM user_limits WHERE user_id = ?', (user_id,))
        user_limits.pop(user_id, None)
        return True
    except Exception as e: logger.error(f"❌ Error removing limit for {user_id}: {e}"); return False

# ============================================================
# --- Pending Files DB Helpers ---
# ============================================================
def save_pending_script_db(user_id, project_name, entry):
    """Persist a pending script entry to DB so it survives restarts."""
    try:
        _db_exec('''INSERT OR REPLACE INTO pending_scripts
                    (user_id, project_name, file_path, file_type, is_safe, security_msg, chat_id, main_file, queued_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (user_id, project_name, entry['path'], entry['type'],
                  1 if entry.get('is_safe') else 0, entry.get('security_msg', ''),
                  entry.get('chat_id', 0), entry.get('main_file', project_name),
                  datetime.now().isoformat()))
    except Exception as e:
        logger.error(f"❌ Error saving pending script for {user_id}/{project_name}: {e}")

def remove_pending_script_db(user_id, project_name):
    try:
        _db_exec('DELETE FROM pending_scripts WHERE user_id = ? AND project_name = ?', (user_id, project_name))
    except Exception as e:
        logger.error(f"❌ Error removing pending script for {user_id}/{project_name}: {e}")

def save_pending_zip_db(user_id, project_name, entry):
    """Persist a pending zip entry (raw bytes go to PENDING_ZIPS_DIR)."""
    import json as _json
    zip_disk_path = os.path.join(PENDING_ZIPS_DIR, f"{user_id}_{project_name}.zip")
    try:
        with open(zip_disk_path, 'wb') as f:
            f.write(entry['content'])
    except Exception as e:
        logger.error(f"❌ Could not save pending zip to disk for {user_id}/{project_name}: {e}")
        return
    try:
        _db_exec('''INSERT OR REPLACE INTO pending_zips
                    (user_id, project_name, zip_path, file_name_zip, main_file, patterns, queued_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (user_id, project_name, zip_disk_path,
                  entry.get('file_name_zip', f"{project_name}.zip"),
                  entry.get('main_file'), _json.dumps(entry.get('patterns', [])),
                  datetime.now().isoformat()))
    except Exception as e:
        logger.error(f"❌ Error saving pending zip for {user_id}/{project_name}: {e}")

def remove_pending_zip_db(user_id, project_name):
    zip_disk_path = os.path.join(PENDING_ZIPS_DIR, f"{user_id}_{project_name}.zip")
    try:
        if os.path.exists(zip_disk_path):
            os.remove(zip_disk_path)
    except Exception as e:
        logger.warning(f"Could not delete pending zip file {zip_disk_path}: {e}")
    try:
        _db_exec('DELETE FROM pending_zips WHERE user_id = ? AND project_name = ?', (user_id, project_name))
    except Exception as e:
        logger.error(f"❌ Error removing pending zip for {user_id}/{project_name}: {e}")

# ============================================================
# --- PLANS SYSTEM (View Plans, Buy, Deposit, Free plan) ---
# ============================================================
def get_base_curr():
    return (str(get_setting("BASE_CURRENCY", "INR")).strip().upper() or "INR")

def get_local_curr():
    return (str(get_setting("LOCAL_CURRENCY", "INR")).strip().upper() or "INR")

def get_rate():
    if get_base_curr() == get_local_curr():
        return 1.0          # same currency (e.g. INR/INR): never convert
    try:
        r = float(get_setting("EXCHANGE_RATE", "90"))
        return r if r > 0 else 90.0
    except Exception:
        return 90.0

def parse_price_to_base(price_str):
    """Return (price_in_base_currency, pretty_text)."""
    base_curr, local_curr = get_base_curr(), get_local_curr()
    p = str(price_str).upper().strip()
    nums = re.findall(r"\d*\.\d+|\d+", p)
    if not nums:
        return 0.0, str(price_str)
    val = float(nums[0])
    if val == 0:
        return 0.0, "FREE"
    if local_curr in p or "TAKA" in p or "TK" in p or "৳" in p or "₹" in p or re.search(r"\bRS\b|\bRUPEES?\b", p):
        b = round(val / get_rate(), 2)
        if base_curr == local_curr: return b, f"{b:g} {base_curr}"
        return b, f"{price_str} (~{b:g} {base_curr})"
    return round(val, 2), f"{round(val, 2):g} {base_curr}"

def is_free_plan(name, price):
    base_price, _ = parse_price_to_base(price)
    return base_price == 0.0 or "FREE" in str(name).upper()

def add_plan_db(name, file_limit, price, duration, features=""):
    _db_exec("INSERT INTO plans (name, file_limit, price, duration, features) VALUES (?, ?, ?, ?, ?)",
             (name, file_limit, price, duration, features))

def get_all_plans():
    return _db_q("SELECT plan_id, name, file_limit, price, duration, features FROM plans ORDER BY plan_id")

def get_plan_by_id(plan_id):
    return _db_q("SELECT plan_id, name, file_limit, price, duration, features FROM plans WHERE plan_id = ?",
                 (plan_id,), one=True)

def delete_plan_db(plan_id):
    _db_exec("DELETE FROM plans WHERE plan_id = ?", (plan_id,))

def get_pending_payment(user_id, plan_id):
    row = _db_q("SELECT paid_amount FROM pending_payments WHERE user_id=? AND plan_id=?", (user_id, plan_id), one=True)
    return row[0] if row else 0.0

def update_pending_payment(user_id, plan_id, amount):
    _db_exec("INSERT OR REPLACE INTO pending_payments (user_id, plan_id, paid_amount) VALUES (?, ?, ?)",
             (user_id, plan_id, amount))

def clear_pending_payment(user_id, plan_id):
    _db_exec("DELETE FROM pending_payments WHERE user_id=? AND plan_id=?", (user_id, plan_id))

def is_txid_used(tx_id):
    return _db_q("SELECT 1 FROM used_txids WHERE tx_id=?", (str(tx_id).strip(),), one=True) is not None

def claim_txid(tx_id):
    """Atomically mark a transaction id as used. True if it was free."""
    rc, _ = _db_exec("INSERT OR IGNORE INTO used_txids (tx_id) VALUES (?)", (str(tx_id).strip(),))
    return rc > 0

def activate_plan(user_id, plan):
    """Give the user this plan. Renewing the same plan extends the remaining time."""
    _, name, flimit, _, duration, _ = plan
    now = datetime.now()
    start = now
    cur = user_subscriptions.get(user_id)
    if _flag('STACK_RENEWALS') and cur and cur.get('plan_name') == name and cur['expiry'] > now:
        start = cur['expiry']
    expiry = start + timedelta(days=int(duration))
    save_subscription(user_id, expiry, name, flimit)
    return expiry

import html as _hh
import csv as _csv
import math as _math

def _h(x):
    return _hh.escape(str(x if x is not None else ''))

# ============================================================
# --- Payment settings registry (every entry is used by the code) ---
# kind: toggle | num | text.   cat = index into PCATS
# ============================================================
PCATS = ["💱 Pricing", "🔌 Methods & Access", "🛡️ Verification", "📣 Notifications", "🧾 Display"]
PSET = [
    # --- Pricing ---
    ('BASE_CURRENCY',      'Base currency',            'text',   'INR', 0, 'Prices are calculated in this currency (INR, USD...)'),
    ('LOCAL_CURRENCY',     'Local currency',           'text',   'INR',  0, 'Currency users pay in with PhonePe / UPI / etc.'),
    ('EXCHANGE_RATE',      'Exchange rate',            'num',    '1',   0, '1 base currency = ? local currency'),
    ('TAX_PERCENT',        'Tax / GST %',              'num',    '0',    0, 'Added on top of every price (0-100)'),
    ('GLOBAL_DISCOUNT',    'Sale discount %',          'num',    '0',    0, 'Discount applied to every plan (0-100)'),
    ('ROUND_LOCAL',        'Round local amount up',    'toggle', '1',    0, 'Round the local amount up to a whole number'),
    ('SHOW_LOCAL_PRICE',   'Show local price',         'toggle', '1',    0, 'Show the local-currency price next to the base price'),
    ('STARS_RATE',         'Stars per 1 base unit',    'num',    '0.6',   0, 'Telegram Stars charged per 1 base currency unit'),
    # --- Methods & Access ---
    ('PAYMENTS_ENABLED',   'Accept payments',          'toggle', '1',    1, 'Master switch - turn OFF to pause all purchases'),
    ('MANUAL_ENABLED',     'Manual methods',           'toggle', '1',    1, 'PhonePe / UPI / bank etc. (admin approval)'),
    ('GATEWAY_ENABLED',    'Payment gateways',         'toggle', '1',    1, 'Link-based payment gateways (admin approval)'),
    ('STARS_ENABLED',      'Telegram Stars',           'toggle', '1',    1, 'Automatic payment with Telegram Stars'),
    ('FREE_PLAN_ENABLED',  'Free plan visible',        'toggle', '1',    1, 'Show/hide free plans in the store'),
    ('COUPONS_ENABLED',    'Coupons',                  'toggle', '1',    1, 'Let users apply coupon codes'),
    # --- Verification ---
    ('AUTO_APPROVE',       'Auto-approve manual',      'toggle', '0',    2, 'Activate manual payments instantly (risky!)'),
    ('REQUIRE_SCREENSHOT', 'Require screenshot',       'toggle', '0',    2, 'Users must send a payment screenshot'),
    ('PAYMENT_TIMEOUT_MIN','Request timeout (min)',    'num',    '120',  2, 'Pending requests expire after this (0 = never)'),
    ('MAX_PENDING_PER_USER','Max pending / user',      'num',    '3',    2, 'Open payment requests allowed per user'),
    ('TXID_MIN_LEN',       'Min TXID length',          'num',    '6',    2, 'Shortest transaction ID accepted'),
    ('PAY_COOLDOWN_SEC',   'Submit cooldown (sec)',    'num',    '30',   2, 'Wait time between payment submissions'),
    ('STACK_RENEWALS',     'Stack renewals',           'toggle', '1',    2, 'Renewing the same plan adds time to the remaining days'),
    # --- Notifications ---
    ('ADMIN_NOTIFY_SALES', 'Notify admins on sales',   'toggle', '1',    3, 'Message admins after every successful sale'),
    ('OWNER_ONLY_NOTIFY',  'Owner-only alerts',        'toggle', '0',    3, 'Send payment alerts only to the owner'),
    ('LOG_CHANNEL',        'Sales log channel',        'text',   '',     3, 'Channel/group ID or @name that receives sale logs'),
    ('EXPIRY_REMINDER_DAYS','Expiry reminder (days)',  'num',    '3',    3, 'Remind users this many days before expiry (0 = off)'),
    ('USER_RECEIPT',       'Send receipts',            'toggle', '1',    3, 'Send the user a receipt after payment'),
    ('SUCCESS_MESSAGE',    'Success message',          'text',   '',     3, 'Extra text added to the purchase receipt'),
    ('NOTIFY_USER_ON_REJECT','Tell user on reject',    'toggle', '1',    3, 'Message the user when a payment is rejected'),
    # --- Display ---
    ('SUPPORT_CONTACT',    'Support contact',          'text',   '',     4, 'Shown on payment screens (default: owner username)'),
    ('PAYMENT_NOTE',       'Payment note',             'text',   '',     4, 'Footer note on the plans page'),
    ('PLANS_TITLE',        'Store title',              'text',   'PLANS',4, 'Heading of the plans page'),
    ('SHOW_FEATURES',      'Show plan features',       'toggle', '1',    4, 'Show the features list on each plan'),
]
PDEF = {k: d for k, _, _, d, _, _ in PSET}
PINFO = {k: (label, kind, cat, hlp) for k, label, kind, _, cat, hlp in PSET}

def _sv(key):
    v = get_setting(key, None)
    return PDEF.get(key, '') if v is None else v

def _flag(key):
    return str(_sv(key)).strip() == '1'

def _num(key):
    try: return float(_sv(key))
    except Exception:
        try: return float(PDEF.get(key, 0))
        except Exception: return 0.0

def _support():
    return (str(_sv('SUPPORT_CONTACT')).strip() or YOUR_USERNAME)

def _admin_targets():
    return [OWNER_ID] if _flag('OWNER_ONLY_NOTIFY') else list(admin_ids)

# ============================================================
# --- Pricing (discount, coupon, tax) ---
# ============================================================
COUPON_APPLIED = {}      # user_id -> coupon code
LAST_PAY_SUBMIT = {}     # user_id -> timestamp
STARS_PAY_MSG = {}

def get_valid_coupon(code):
    if not _flag('COUPONS_ENABLED') or not code: return None
    row = _db_q("SELECT code, percent, max_uses, used, active FROM coupons WHERE code=?", (str(code).strip().upper(),), one=True)
    if not row: return None
    c, pct, mx, used, active = row
    if not active or (mx and used >= mx): return None
    return c, float(pct)

def calc_price(user_id, plan):
    base, _ = parse_price_to_base(plan[3])
    disc = max(0.0, min(100.0, _num('GLOBAL_DISCOUNT')))
    after = base * (1 - disc / 100)
    cp = get_valid_coupon(COUPON_APPLIED.get(user_id))
    coupon, cpct = (cp if cp else ('', 0.0))
    after = after * (1 - cpct / 100)
    tax_pct = max(0.0, min(100.0, _num('TAX_PERCENT')))
    tax_amt = after * tax_pct / 100
    total = round(after + tax_amt, 2)
    return {'base': base, 'disc': disc, 'coupon': coupon, 'cpct': cpct,
            'tax_pct': tax_pct, 'tax_amt': round(tax_amt, 2), 'total': total}

def local_amount(base_total):
    v = base_total * get_rate()
    return float(_math.ceil(v - 1e-9)) if _flag('ROUND_LOCAL') else round(v, 2)

def fmt_money(base_total):
    b, l = get_base_curr(), get_local_curr()
    if base_total <= 0: return "FREE"
    s = f"{base_total:g} {b}"
    if _flag('SHOW_LOCAL_PRICE') and l != b:
        s += f" (~{local_amount(base_total):g} {l})"
    return s

def stars_for(base_total):
    return max(1, int(_math.ceil(base_total * _num('STARS_RATE') - 1e-9)))

def price_breakdown_html(pr):
    lines = [f"💰 Plan price: <b>{pr['base']:g} {get_base_curr()}</b>"]
    if pr['disc']: lines.append(f"🏷️ Sale discount: <b>-{pr['disc']:g}%</b>")
    if pr['coupon']: lines.append(f"🎟️ Coupon <code>{_h(pr['coupon'])}</code>: <b>-{pr['cpct']:g}%</b>")
    if pr['tax_pct']: lines.append(f"🧾 Tax {pr['tax_pct']:g}%: <b>+{pr['tax_amt']:g}</b>")
    lines.append(f"✅ <b>Total: {_h(fmt_money(pr['total']))}</b>")
    return "\n".join(lines)

# ============================================================
# --- Payments log / purchase completion ---
# ============================================================
def record_payment(user_id, plan, method, amount_base, ref):
    _, rid = _db_exec(
        "INSERT INTO payments (user_id, plan_id, plan_name, method, amount_base, currency, ref, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, plan[0], plan[1], method, float(amount_base), get_base_curr(), str(ref), datetime.now().isoformat()))
    return rid

def _log_channel_send(text):
    ch = str(_sv('LOG_CHANNEL')).strip()
    if not ch: return
    try: bot.send_message(int(ch) if ch.lstrip('-').isdigit() else ch, text, parse_mode='HTML')
    except Exception as e: logger.warning(f"Sales log channel error: {e}")

def complete_purchase(user_id, plan, method, paid_text, amount_base, ref, coupon=''):
    """Activate the plan, log it, use the coupon, send receipt and notify admins."""
    expiry = activate_plan(user_id, plan)
    inv = record_payment(user_id, plan, method, amount_base, ref)
    if coupon:
        try: _db_exec("UPDATE coupons SET used = used + 1 WHERE code=?", (coupon,))
        except Exception: pass
    COUPON_APPLIED.pop(user_id, None)
    if _flag('USER_RECEIPT'):
        extra = str(_sv('SUCCESS_MESSAGE')).strip()
        txt = (f"🧾 <b>PAYMENT RECEIPT</b>\n━━━━━━━━━━━━━━━━━━\n"
               f"🔖 Invoice: <code>#{inv}</code>\n📦 Plan: <b>{_h(plan[1])}</b>\n"
               f"💳 Method: {_h(method)}\n💵 Paid: <b>{_h(paid_text)}</b>\n"
               f"📅 Active until: <b>{expiry:%d-%m-%Y}</b>\n━━━━━━━━━━━━━━━━━━\n🚀 You can now upload projects!")
        if extra: txt += f"\n\n{_h(extra)}"
        try: bot.send_message(user_id, txt, parse_mode='HTML')
        except Exception: pass
    sale = (f"💰 <b>New sale</b> #{inv}\n👤 <code>{user_id}</code>\n📦 {_h(plan[1])}\n💳 {_h(method)} • {_h(paid_text)}")
    if _flag('ADMIN_NOTIFY_SALES'):
        for aid in _admin_targets():
            try: bot.send_message(aid, sale, parse_mode='HTML')
            except Exception: pass
    _log_channel_send(sale)
    return expiry, inv

# ============================================================
# --- Store pages ---
# ============================================================
def _send_or_edit(chat_id, text, markup=None, message_id=None, parse='HTML'):
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode=parse)
            return
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" in str(e):
                return
            logger.warning(f"edit failed, sending new message: {e}")
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode=parse)

def visible_plans():
    plans = get_all_plans()
    if not _flag('FREE_PLAN_ENABLED'):
        plans = [p for p in plans if not is_free_plan(p[1], p[3])]
    return plans

def send_plan_page(chat_id, user_id, page=0, message_id=None):
    plans = visible_plans()
    if not plans:
        _send_or_edit(chat_id, "ℹ️ <b>No plans are available at the moment.</b>\n\nPlease check back later or contact the owner.", None, message_id)
        return
    total = len(plans)
    page = max(0, min(int(page), total - 1))
    plan_id, name, flimit, price, duration, features = plans[page]
    free = is_free_plan(name, price)
    pr = calc_price(user_id, (plan_id, name, flimit, price, duration, features))

    feature_text = ""
    if _flag('SHOW_FEATURES'):
        if features and features.strip():
            lines = []
            for feat in features.split(","):
                feat = feat.strip()
                if not feat: continue
                lines.append(_h(feat) if feat.startswith(("✅", "❌")) else f"✅ {_h(feat)}")
            feature_text = "\n".join(lines)
        else:
            feature_text = "✅ 24/7 Hosting\n✅ Auto Package Install\n✅ Log Viewer\n✅ File Manager"
        feature_text += "\n\n"

    if free:
        price_line = "<b>FREE</b>"
    else:
        shown = fmt_money(pr['total'])
        if pr['total'] + 0.005 < pr['base']:
            price_line = f"<s>{pr['base']:g} {get_base_curr()}</s> → <b>{_h(shown)}</b>"
        else:
            price_line = f"<b>{_h(shown)}</b>"
        if pr['tax_pct']: price_line += f"  <i>(incl. {pr['tax_pct']:g}% tax)</i>"

    text = (f"🛍️ <b>{_h(str(_sv('PLANS_TITLE')).upper())} [{page + 1}/{total}]</b>\n──────────────────────\n\n"
            f"{'🆓' if free else '🚀'} <b>{_h(str(name).upper())}</b>\n\n"
            f"⚙️ <b>Host up to {flimit} project(s)</b>\n"
            f"⏱️ <b>Duration:</b> {duration} days\n\n"
            f"{feature_text}"
            f"──────────────────────\n"
            f"💰 <b>Price:</b> {price_line}")
    if pr['coupon'] and not free:
        text += f"\n🎟️ Coupon <code>{_h(pr['coupon'])}</code> applied (-{pr['cpct']:g}%)"
    if not free: text += _pb_plan_line(user_id, (plan_id, name, flimit, price, duration, features))
    if has_active_sub(user_id) and user_id not in admin_ids:
        days_left = (user_subscriptions[user_id]['expiry'] - datetime.now()).days
        text += f"\n\n✅ <b>Your plan:</b> {_h(get_plan_label(user_id))} ({days_left} days left)"
    note = str(_sv('PAYMENT_NOTE')).strip()
    if note: text += f"\n\n📌 <i>{_h(note)}</i>"

    markup = types.InlineKeyboardMarkup(row_width=2)
    if free:
        markup.add(types.InlineKeyboardButton("🆓 Get Started Free", callback_data=f"claim_free_{plan_id}"))
    else:
        markup.add(types.InlineKeyboardButton("🛒 Buy Now", callback_data=f"plbuy_{plan_id}"))
    nav = []
    if page > 0: nav.append(types.InlineKeyboardButton("⬅️ Back", callback_data=f"page_plan_{page - 1}"))
    if page < total - 1: nav.append(types.InlineKeyboardButton("Next ➡️", callback_data=f"page_plan_{page + 1}"))
    if nav: markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main"))
    _send_or_edit(chat_id, text, markup, message_id)

def _logic_view_plans(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, M('banned')); return
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, M('locked')); return
    send_plan_page(message.chat.id, user_id, 0)

def _is_cancel(message):
    return bool(message.text and message.text.strip().lower() == '/cancel')

def _clean_amount(text):
    try:
        v = float(str(text).strip().replace(',', ''))
        return v if v > 0 else None
    except Exception:
        return None

# ---- coupons (user side) ----
def process_coupon_input(message, plan_id, page):
    uid = message.from_user.id
    if not message.text or _is_cancel(message):
        bot.reply_to(message, "🚫 Cancelled."); return
    code = message.text.strip().upper()
    if code in ('REMOVE', 'NONE', 'OFF'):
        COUPON_APPLIED.pop(uid, None)
        bot.reply_to(message, "🗑️ Coupon removed.")
    elif get_valid_coupon(code):
        COUPON_APPLIED[uid] = code
        bot.reply_to(message, f"✅ Coupon <code>{_h(code)}</code> applied!", parse_mode='HTML')
    else:
        bot.reply_to(message, "❌ Invalid, expired or fully used coupon code."); return
    send_plan_page(message.chat.id, uid, int(page))

# ---- buying ----
def _methods_for_user():
    rows = _db_q("SELECT id, name, number, instructions, COALESCE(kind,'manual') FROM payment_methods ORDER BY id")
    out = []
    for r in rows:
        if r[4] == 'gateway' and _flag('GATEWAY_ENABLED'): out.append(r)
        elif r[4] != 'gateway' and _flag('MANUAL_ENABLED'): out.append(r)
    return out

def show_buy_methods(chat_id, uid, plan_id, message_id=None):
    plan = get_plan_by_id(plan_id)
    if not plan:
        bot.send_message(chat_id, "❌ This plan no longer exists."); return
    if not _flag('PAYMENTS_ENABLED'):
        bot.send_message(chat_id, "⏸️ <b>Payments are temporarily paused.</b>\nPlease try again later.", parse_mode='HTML'); return
    pr = calc_price(uid, plan)
    methods = _methods_for_user()
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = []
    if _flag('STARS_ENABLED'):
        btns.append(types.InlineKeyboardButton(f"⭐ Telegram Stars ({stars_for(pr['total'])})", callback_data=f"plpm_{plan_id}_stars"))
    for mid, mname, _n, _i, kind in methods:
        icon = "🌐" if kind == 'gateway' else "📱"
        btns.append(types.InlineKeyboardButton(f"{icon} {str(mname)[:24]}", callback_data=f"plpm_{plan_id}_{mid}"))
    if not btns and not _pb_cost(uid, plan):
        bot.send_message(chat_id, f"ℹ️ No payment method is available right now. Contact {_h(_support())}.", parse_mode='HTML'); return
    markup.add(*btns)
    _pc = _pb_cost(uid, plan)
    if _pc: markup.add(types.InlineKeyboardButton(f"⭐ Pay with Points ({_pc} pts)", callback_data=f"pbuy_{plan_id}"))
    markup.add(types.InlineKeyboardButton("🔙 Back to Plans", callback_data="view_plans_cb"),
               types.InlineKeyboardButton("🏠 Back to Main", callback_data="back_to_main"))
    text = (f"🛒 <b>ORDER SUMMARY</b>\n──────────────────────\n\n📦 <b>{_h(plan[1])}</b> • {plan[4]} days • {plan[2]} project(s)\n\n"
            f"{price_breakdown_html(pr)}\n\n──────────────────────\n💳 <b>Choose a payment method:</b>")
    _send_or_edit(chat_id, text, markup, message_id)

def send_stars_invoice(chat_id, uid, plan_id):
    plan = get_plan_by_id(plan_id)
    if not plan: return
    if not (_flag('PAYMENTS_ENABLED') and _flag('STARS_ENABLED')):
        bot.send_message(chat_id, "⏸️ Telegram Stars payments are currently disabled."); return
    pr = calc_price(uid, plan)
    stars = stars_for(pr['total'])
    payload = f"plan|{plan_id}|{uid}|{pr['coupon']}"
    try:
        bot.send_invoice(chat_id, title=f"{plan[1]} plan", description=f"{plan[4]} days • up to {plan[2]} project(s)",
                         invoice_payload=payload, provider_token="", currency="XTR",
                         prices=[types.LabeledPrice(label=str(plan[1])[:30], amount=stars)])
    except Exception as e:
        logger.error(f"send_invoice failed: {e}")
        bot.send_message(chat_id, f"❌ Could not create the Stars invoice. Contact {_support()}.")

def show_method_screen(chat_id, uid, plan_id, mid):
    plan = get_plan_by_id(plan_id)
    m = _db_q("SELECT id, name, number, instructions, COALESCE(kind,'manual') FROM payment_methods WHERE id=?", (mid,), one=True)
    if not plan or not m:
        bot.send_message(chat_id, "❌ Payment method or plan not found."); return
    _, mname, number, instr, kind = m
    pr = calc_price(uid, plan)
    local = local_amount(pr['total'])
    lc = get_local_curr()
    markup = types.InlineKeyboardMarkup(row_width=1)
    if kind == 'gateway':
        head = f"🌐 <b>{_h(str(mname).upper())}</b>"
        pay_line = f"1️⃣ Open the payment link and pay <b>{local:g} {_h(lc)}</b>."
        if str(number).lower().startswith(('http://', 'https://')):
            markup.add(types.InlineKeyboardButton("💳 Pay Now", url=str(number)))
        else:
            pay_line += f"\n🔗 <code>{_h(number)}</code>"
        step2 = "2️⃣ After paying, press <b>I've Paid</b> and send your transaction / reference ID."
    else:
        head = f"📱 <b>{_h(str(mname).upper())}</b>"
        pay_line = f"1️⃣ Send exactly <b>{local:g} {_h(lc)}</b> to:\n📲 <code>{_h(number)}</code>"
        step2 = "2️⃣ Press <b>I've Paid</b> and send your transaction ID (UTR / TXN ID)."
    markup.add(types.InlineKeyboardButton("✅ I've Paid", callback_data=f"plpaid_{plan_id}_{mid}"),
               types.InlineKeyboardButton("🔙 Back", callback_data=f"plbuy_{plan_id}"))
    markup.add(types.InlineKeyboardButton("🏠 Back to Main", callback_data="back_to_main"))
    text = (f"{head}\n──────────────────────\n\n📦 Plan: <b>{_h(plan[1])}</b>\n{price_breakdown_html(pr)}\n\n"
            f"{pay_line}\n{step2}\n")
    if instr: text += f"\n📝 {_h(instr)}\n"
    if _flag('REQUIRE_SCREENSHOT'): text += "\n📸 You will also need to send a screenshot of the payment."
    text += f"\n❓ Need help? {_h(_support())}"
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML')

def start_paid_flow(chat_id, uid, plan_id, mid):
    cd = _num('PAY_COOLDOWN_SEC')
    left = cd - (time.time() - LAST_PAY_SUBMIT.get(uid, 0))
    if left > 0:
        bot.send_message(chat_id, f"⏳ Please wait {int(left)+1}s before submitting another payment."); return
    mx = int(_num('MAX_PENDING_PER_USER'))
    if mx > 0:
        pend = _db_q("SELECT COUNT(*) FROM manual_payments WHERE user_id=? AND status='pending'", (uid,), one=True)[0]
        if pend >= mx:
            bot.send_message(chat_id, f"⚠️ You already have {pend} pending payment request(s). Please wait for admin approval."); return
    msg = bot.send_message(chat_id, "📩 <b>Send your transaction ID / reference number:</b>\n\n/cancel to abort.", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_pay_txid, plan_id, mid)

def process_pay_txid(message, plan_id, mid):
    if not message.text:
        bot.reply_to(message, "⚠️ Send the transaction ID as text."); return
    if _is_cancel(message):
        bot.reply_to(message, "🚫 Cancelled."); return
    txid = message.text.strip()
    if len(txid) < int(_num('TXID_MIN_LEN')) or len(txid) > 100:
        msg = bot.reply_to(message, "⚠️ That doesn't look like a valid transaction ID. Try again or /cancel.")
        bot.register_next_step_handler(msg, process_pay_txid, plan_id, mid); return
    dup = _db_q("SELECT 1 FROM manual_payments WHERE txid=? AND status IN ('pending','approved')", (txid,), one=True)
    if dup or is_txid_used(txid):
        bot.reply_to(message, "❌ This transaction ID has already been submitted."); return
    if _flag('REQUIRE_SCREENSHOT'):
        msg = bot.reply_to(message, "📸 <b>Now send a screenshot of your payment</b> (as a photo).\n\n/cancel to abort.", parse_mode='HTML')
        bot.register_next_step_handler(msg, process_pay_photo, plan_id, mid, txid)
    else:
        submit_payment(message, plan_id, mid, txid, None)

def process_pay_photo(message, plan_id, mid, txid):
    if _is_cancel(message):
        bot.reply_to(message, "🚫 Cancelled."); return
    if not message.photo:
        msg = bot.reply_to(message, "⚠️ Please send the screenshot as a <b>photo</b>, or /cancel.", parse_mode='HTML')
        bot.register_next_step_handler(msg, process_pay_photo, plan_id, mid, txid); return
    submit_payment(message, plan_id, mid, txid, message.photo[-1].file_id)

def submit_payment(message, plan_id, mid, txid, photo_id):
    uid = message.from_user.id
    plan = get_plan_by_id(plan_id)
    m = _db_q("SELECT name FROM payment_methods WHERE id=?", (mid,), one=True)
    if not plan or not m:
        bot.reply_to(message, "❌ Plan or payment method no longer exists."); return
    LAST_PAY_SUBMIT[uid] = time.time()
    pr = calc_price(uid, plan)
    local = f"{local_amount(pr['total']):g} {get_local_curr()}"
    _, rid = _db_exec(
        "INSERT INTO manual_payments (user_id, plan_id, method_name, amount, txid, created_at, amount_base, photo, coupon) VALUES (?,?,?,?,?,?,?,?,?)",
        (uid, plan_id, m[0], local, txid, datetime.now().isoformat(), pr['total'], photo_id or '', pr['coupon']))
    if _flag('AUTO_APPROVE'):
        res = process_payment_decision(rid, True, None)
        bot.reply_to(message, "✅ Payment received and plan activated automatically.")
        return
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_pay_{rid}"),
               types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_pay_{rid}"))
    uname = message.from_user.username or "no username"
    caption = (f"🔔 <b>New payment request</b> #{rid}\n\n👤 User: <code>{uid}</code> (@{_h(uname)})\n"
               f"📦 Plan: <b>{_h(plan[1])}</b>\n💳 Method: {_h(m[0])}\n💵 Amount due: <b>{_h(local)}</b> ({pr['total']:g} {get_base_curr()})\n"
               f"🎟️ Coupon: {_h(pr['coupon'] or '—')}\n📑 TXID: <code>{_h(txid)}</code>\n\nVerify the payment, then choose:")
    for aid in _admin_targets():
        try:
            if photo_id: bot.send_photo(aid, photo_id, caption=caption, reply_markup=markup, parse_mode='HTML')
            else: bot.send_message(aid, caption, reply_markup=markup, parse_mode='HTML')
        except Exception as e: logger.warning(f"Could not notify admin {aid}: {e}")
    bot.reply_to(message, f"⏳ <b>Your payment request #{rid} was sent to the admin.</b>\n\nYour plan will be activated after verification.", parse_mode='HTML')

def process_payment_decision(rid, approve, admin_id):
    """Approve/reject a manual payment atomically. Returns (ok, text)."""
    row = _db_q("SELECT user_id, plan_id, txid, method_name, amount, COALESCE(amount_base,0), COALESCE(coupon,'') FROM manual_payments WHERE rid=?", (rid,), one=True)
    if not row: return False, "Request not found."
    target, plan_id, txid, mname, amount, abase, coupon = row
    new_status = 'approved' if approve else 'rejected'
    rc, _ = _db_exec("UPDATE manual_payments SET status=? WHERE rid=? AND status='pending'", (new_status, rid))
    if rc == 0: return False, "Already handled."
    if approve:
        plan = get_plan_by_id(plan_id)
        if not plan:
            _db_exec("UPDATE manual_payments SET status='pending' WHERE rid=?", (rid,))
            return False, "Plan was deleted."
        claim_txid(txid)
        expiry, inv = complete_purchase(target, plan, mname, amount, abase, txid, coupon)
        return True, f"✅ Payment #{rid} approved — user {target}, {plan[1]} until {expiry:%d-%m-%Y} (invoice #{inv})"
    if _flag('NOTIFY_USER_ON_REJECT'):
        try: bot.send_message(target, f"❌ <b>Your payment request #{rid} was rejected.</b>\nPlease check the details and try again, or contact {_h(_support())}.", parse_mode='HTML')
        except Exception: pass
    return True, f"❌ Payment #{rid} rejected — user {target}"

# ---- successful Telegram Stars payments ----
@bot.pre_checkout_query_handler(func=lambda q: True)
def _pre_checkout(q):
    ok, err = True, None
    try:
        parts = q.invoice_payload.split('|')
        plan = get_plan_by_id(int(parts[1]))
        if not plan or int(parts[2]) != q.from_user.id or not (_flag('PAYMENTS_ENABLED') and _flag('STARS_ENABLED')):
            ok, err = False, "This plan is no longer available."
    except Exception:
        ok, err = False, "Invalid order."
    try: bot.answer_pre_checkout_query(q.id, ok=ok, error_message=err)
    except Exception as e: logger.error(f"pre_checkout error: {e}")

@bot.message_handler(content_types=['successful_payment'])
def _stars_paid(message):
    sp = message.successful_payment
    uid = message.from_user.id
    try:
        parts = sp.invoice_payload.split('|')
        plan = get_plan_by_id(int(parts[1]))
        coupon = parts[3] if len(parts) > 3 else ''
        ref = sp.telegram_payment_charge_id
        if not claim_txid(ref): return
        if not plan:
            for aid in _admin_targets():
                try: bot.send_message(aid, f"⚠️ Stars payment from {uid} ({sp.total_amount} ⭐, ref {ref}) but the plan no longer exists. Refund manually.")
                except Exception: pass
            return
        base = round(sp.total_amount / max(_num('STARS_RATE'), 0.0001), 2)
        complete_purchase(uid, plan, "Telegram Stars", f"{sp.total_amount} ⭐", base, ref, coupon)
    except Exception as e:
        logger.error(f"Stars payment handling failed: {e}", exc_info=True)

# ============================================================
# --- Admin: plans / methods / settings / tools ---
# ============================================================
MASTER_PRESETS = ["PhonePe", "Google Pay", "Paytm", "UPI", "bKash", "Nagad", "Rocket", "PayPal", "Bank Transfer", "Other"]

def _mask(v):
    v = str(v or '')
    return '—' if not v else (v[:3] + '…' + v[-3:] if len(v) > 8 else '•••')

def process_add_plan(message):
    if message.from_user.id not in admin_ids: return
    if not message.text or _is_cancel(message):
        bot.reply_to(message, "❌ Cancelled."); return
    try:
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) < 4: raise ValueError("format")
        name, limit, price, duration = parts[0], int(parts[1]), parts[2], int(parts[3])
        features = parts[4] if len(parts) > 4 else ""
        if not name or limit <= 0 or duration <= 0: raise ValueError("values")
        add_plan_db(name, limit, price, duration, features)
        bot.reply_to(message, f"✅ Plan *{_md(name)}* added.", parse_mode='Markdown')
    except ValueError:
        bot.reply_to(message, "❌ Invalid format. Use:\n`NAME | PROJECT LIMIT | PRICE | DAYS | FEATURES`\n"
                              "File limit and days must be numbers.", parse_mode='Markdown')

def process_edit_plan_price(message, plan_id):
    if message.from_user.id not in admin_ids: return
    if not message.text or _is_cancel(message):
        bot.reply_to(message, "❌ Cancelled."); return
    price = message.text.strip()
    if not re.search(r"\d", price):
        bot.reply_to(message, "❌ Price must contain a number, e.g. `499 INR` or `₹499` or `0` or `0`.", parse_mode='Markdown'); return
    _db_exec("UPDATE plans SET price=? WHERE plan_id=?", (price, plan_id))
    bot.reply_to(message, f"✅ Price updated to <code>{_h(price)}</code>.", parse_mode='HTML')

def process_add_manual_method(message, preset):
    if message.from_user.id not in admin_ids: return
    if not message.text or _is_cancel(message):
        bot.reply_to(message, "❌ Cancelled."); return
    parts = [p.strip() for p in message.text.split("|")]
    if preset == 'Other':
        if len(parts) < 2 or not parts[0] or not parts[1]:
            bot.reply_to(message, "❌ Use `NAME | NUMBER/ID | INSTRUCTIONS`.", parse_mode='Markdown'); return
        name, number, instr = parts[0], parts[1], (parts[2] if len(parts) > 2 else '')
    else:
        if not parts or not parts[0]:
            bot.reply_to(message, "❌ Use `NUMBER/ID | INSTRUCTIONS`.", parse_mode='Markdown'); return
        name, number, instr = preset, parts[0], (parts[1] if len(parts) > 1 else '')
    _db_exec("INSERT INTO payment_methods (name, number, instructions, kind) VALUES (?, ?, ?, 'manual')", (name, number, instr))
    bot.reply_to(message, f"✅ Payment method <b>{_h(name)}</b> added.", parse_mode='HTML')

def process_add_gateway(message):
    if message.from_user.id not in admin_ids: return
    if not message.text or _is_cancel(message):
        bot.reply_to(message, "❌ Cancelled."); return
    parts = [p.strip() for p in message.text.split("|")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        bot.reply_to(message, "❌ Use `NAME | PAYMENT LINK | INSTRUCTIONS`.", parse_mode='Markdown'); return
    _db_exec("INSERT INTO payment_methods (name, number, instructions, kind) VALUES (?, ?, ?, 'gateway')",
             (parts[0], parts[1], parts[2] if len(parts) > 2 else ''))
    bot.reply_to(message, f"✅ Payment gateway <b>{_h(parts[0])}</b> added.", parse_mode='HTML')

def process_set_value(message, key):
    if message.from_user.id not in admin_ids: return
    if not message.text or _is_cancel(message):
        bot.reply_to(message, "❌ Cancelled."); return
    label, kind, _, _ = PINFO[key]
    val = message.text.strip()
    if kind == 'num':
        try: n = float(val.replace(',', ''))
        except Exception:
            bot.reply_to(message, "❌ Send a number."); return
        if n < 0 or (key == 'EXCHANGE_RATE' and n <= 0) or (key == 'STARS_RATE' and n <= 0):
            bot.reply_to(message, "❌ Value out of range."); return
        if key in ('TAX_PERCENT', 'GLOBAL_DISCOUNT') and n > 100:
            bot.reply_to(message, "❌ Percent must be 0-100."); return
        val = f"{n:g}"
    else:
        if val in ('-', 'off', 'none', 'clear'): val = ''
        if key in ('BASE_CURRENCY', 'LOCAL_CURRENCY'): val = val.upper()
        if key in ('BASE_CURRENCY', 'LOCAL_CURRENCY') and not val:
            bot.reply_to(message, "❌ Currency can't be empty."); return
    set_setting(key, val)
    bot.send_message(message.chat.id, f"✅ <b>{_h(label)}</b> updated: <code>{_h(val or '—')}</code>", parse_mode='HTML')

def process_new_coupon(message):
    if message.from_user.id not in admin_ids: return
    if not message.text or _is_cancel(message):
        bot.reply_to(message, "❌ Cancelled."); return
    try:
        code, pct, mx = [p.strip() for p in message.text.split("|")][:3]
        code = code.upper(); pct = float(pct); mx = int(mx)
        if not re.fullmatch(r"[A-Z0-9_\-]{3,20}", code) or not (0 < pct <= 100) or mx < 0: raise ValueError
    except Exception:
        bot.reply_to(message, "❌ Use `CODE | PERCENT | MAX USES` e.g. `WELCOME10 | 10 | 100` (0 = unlimited).", parse_mode='Markdown'); return
    _db_exec("INSERT OR REPLACE INTO coupons (code, percent, max_uses, used, active) VALUES (?,?,?,0,1)", (code, pct, mx))
    bot.reply_to(message, f"✅ Coupon <code>{_h(code)}</code> created: {pct:g}% off, max uses {mx or 'unlimited'}.", parse_mode='HTML')

def process_reset_free(message):
    if message.from_user.id not in admin_ids: return
    if not message.text or _is_cancel(message):
        bot.reply_to(message, "❌ Cancelled."); return
    try: target = int(message.text.strip())
    except Exception:
        bot.reply_to(message, "❌ Send a numeric user ID."); return
    rc, _ = _db_exec("DELETE FROM free_plan_claimed WHERE user_id=?", (target,))
    bot.reply_to(message, "✅ Free-plan claim reset. The user can claim it again." if rc else "ℹ️ That user hasn't claimed the free plan.")

def _admin_pay_methods_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("➕ Add Method", callback_data="add_pay_method"))
    for mid, mname, kind in _db_q("SELECT id, name, COALESCE(kind,'manual') FROM payment_methods ORDER BY id"):
        icon = "🌐" if kind == 'gateway' else "📱"
        markup.add(types.InlineKeyboardButton(f"🗑️ {icon} {mname}", callback_data=f"del_pay_{mid}"))
    markup.add(types.InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel"))
    return markup

def _pay_methods_text():
    stars = "ON ✅" if _flag('STARS_ENABLED') else "OFF ❌"
    return (f"💳 <b>Payment methods</b>\n\n⭐ Telegram Stars: <b>{stars}</b> (built-in)\n"
            f"📱 Manual (PhonePe, UPI, bank...) and 🌐 gateways you add below. Tap one to delete it.")

def _settings_home_markup():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(*[types.InlineKeyboardButton(c, callback_data=f"pps_c{i}") for i, c in enumerate(PCATS)])
    m.row(types.InlineKeyboardButton("📜 History", callback_data="ppt_history"),
          types.InlineKeyboardButton("⏳ Pending", callback_data="ppt_pending"))
    m.row(types.InlineKeyboardButton("💹 Revenue", callback_data="ppt_revenue"),
          types.InlineKeyboardButton("📤 Export CSV", callback_data="ppt_export"))
    m.row(types.InlineKeyboardButton("🎟️ Coupons", callback_data="ppt_coupons"),
          types.InlineKeyboardButton("🔁 Reset Free Claim", callback_data="ppt_resetfree"))
    m.add(types.InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel"))
    return m

def _settings_home_text():
    return (f"⚙️ <b>Payment Settings</b>\n\n{len(PSET)} options in 5 groups + 6 tools.\n"
            f"Methods: ⭐ Stars {'✅' if _flag('STARS_ENABLED') else '❌'} • 📱 Manual {'✅' if _flag('MANUAL_ENABLED') else '❌'} • 🌐 Gateway {'✅' if _flag('GATEWAY_ENABLED') else '❌'}\n"
            f"Currency: 1 {_h(get_base_curr())} = {get_rate():g} {_h(get_local_curr())}\n\nChoose a group:")

def _settings_cat_view(ci):
    lines = [f"⚙️ <b>{_h(PCATS[ci])}</b>\n"]
    m = types.InlineKeyboardMarkup(row_width=1)
    for key, label, kind, _d, cat, hlp in PSET:
        if cat != ci: continue
        v = _sv(key)
        if kind == 'toggle':
            on = str(v) == '1'
            lines.append(f"{'✅' if on else '❌'} <b>{_h(label)}</b> — <i>{_h(hlp)}</i>")
            m.add(types.InlineKeyboardButton(f"{'✅' if on else '❌'} {label}", callback_data=f"pps_t_{key}"))
        else:
            lines.append(f"✏️ <b>{_h(label)}:</b> <code>{_h(v or '—')}</code>\n     <i>{_h(hlp)}</i>")
            m.add(types.InlineKeyboardButton(f"✏️ {label}: {str(v)[:18] or '—'}", callback_data=f"pps_s_{key}"))
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_pay_settings"))
    return "\n".join(lines), m

def _pending_list_send(chat_id):
    rows = _db_q("SELECT m.rid, m.user_id, p.name, m.method_name, m.amount, m.txid FROM manual_payments m LEFT JOIN plans p ON p.plan_id=m.plan_id WHERE m.status='pending' ORDER BY m.rid LIMIT 10")
    if not rows:
        bot.send_message(chat_id, "✅ No pending payment requests."); return
    for rid, uid, pname, mname, amount, txid in rows:
        mk = types.InlineKeyboardMarkup()
        mk.row(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_pay_{rid}"),
               types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_pay_{rid}"))
        bot.send_message(chat_id, f"⏳ <b>Request #{rid}</b>\n👤 <code>{uid}</code>\n📦 {_h(pname)}\n💳 {_h(mname)} • {_h(amount)}\n📑 <code>{_h(txid)}</code>",
                         reply_markup=mk, parse_mode='HTML')

def _history_send(chat_id):
    rows = _db_q("SELECT id, user_id, plan_name, method, amount_base, currency, created_at FROM payments ORDER BY id DESC LIMIT 15")
    if not rows:
        bot.send_message(chat_id, "ℹ️ No payments recorded yet."); return
    lines = ["📜 <b>Last payments</b>\n"]
    for i, uid, pn, meth, amt, cur, ts in rows:
        lines.append(f"#{i} • <code>{uid}</code> • {_h(pn)} • {amt:g} {_h(cur)} • {_h(meth)} • {str(ts)[:16].replace('T',' ')}")
    bot.send_message(chat_id, "\n".join(lines), parse_mode='HTML')

def _revenue_send(chat_id):
    now = datetime.now()
    def agg(since):
        r = _db_q("SELECT COUNT(*), COALESCE(SUM(amount_base),0) FROM payments WHERE created_at >= ?", (since.isoformat(),), one=True)
        return r[0], r[1]
    cur = get_base_curr()
    t = agg(now.replace(hour=0, minute=0, second=0, microsecond=0))
    w = agg(now - timedelta(days=7)); mth = agg(now - timedelta(days=30)); a = agg(datetime(2000, 1, 1))
    by = _db_q("SELECT method, COUNT(*), SUM(amount_base) FROM payments GROUP BY method ORDER BY SUM(amount_base) DESC LIMIT 6")
    top = _db_q("SELECT plan_name, COUNT(*) FROM payments GROUP BY plan_name ORDER BY COUNT(*) DESC LIMIT 5")
    txt = (f"💹 <b>Revenue</b> ({_h(cur)})\n\n📅 Today: <b>{t[1]:g}</b> ({t[0]} sales)\n🗓️ 7 days: <b>{w[1]:g}</b> ({w[0]})\n"
           f"📆 30 days: <b>{mth[1]:g}</b> ({mth[0]})\n🏦 All time: <b>{a[1]:g}</b> ({a[0]})\n")
    if by: txt += "\n<b>By method</b>\n" + "\n".join(f"• {_h(m)}: {s:g} ({c})" for m, c, s in by)
    if top: txt += "\n\n<b>Top plans</b>\n" + "\n".join(f"• {_h(n)}: {c} sold" for n, c in top)
    bot.send_message(chat_id, txt, parse_mode='HTML')

def _export_send(chat_id):
    rows = _db_q("SELECT id, user_id, plan_name, method, amount_base, currency, ref, created_at FROM payments ORDER BY id")
    if not rows:
        bot.send_message(chat_id, "ℹ️ No payments to export."); return
    path = os.path.join(tempfile.gettempdir(), f"payments_{int(time.time())}.csv")
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = _csv.writer(f); w.writerow(["invoice", "user_id", "plan", "method", "amount", "currency", "reference", "date"]); w.writerows(rows)
    with open(path, 'rb') as f: bot.send_document(chat_id, f, caption=f"📤 {len(rows)} payments")
    try: os.remove(path)
    except Exception: pass

def _coupons_view():
    rows = _db_q("SELECT code, percent, max_uses, used, active FROM coupons ORDER BY code")
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("➕ New Coupon", callback_data="ppt_cadd"))
    lines = ["🎟️ <b>Coupons</b>\n"] if rows else ["🎟️ <b>Coupons</b>\n\nNo coupons yet."]
    for code, pct, mx, used, active in rows:
        lines.append(f"<code>{_h(code)}</code> • {pct:g}% • used {used}/{mx or '∞'} • {'🟢' if active else '🔴'}")
        m.row(types.InlineKeyboardButton(f"{'⏸' if active else '▶️'} {code}", callback_data=f"ppt_ctog_{code}"),
              types.InlineKeyboardButton(f"🗑️ {code}", callback_data=f"ppt_cdel_{code}"))
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_pay_settings"))
    return "\n".join(lines), m

# ---- background: expire old requests + expiry reminders ----
_REMINDED = set()
def payments_housekeeping():
    while True:
        try:
            tmo = _num('PAYMENT_TIMEOUT_MIN')
            if tmo > 0:
                cutoff = (datetime.now() - timedelta(minutes=tmo)).isoformat()
                for rid, uid in _db_q("SELECT rid, user_id FROM manual_payments WHERE status='pending' AND created_at < ?", (cutoff,)):
                    rc, _ = _db_exec("UPDATE manual_payments SET status='expired' WHERE rid=? AND status='pending'", (rid,))
                    if rc:
                        try: bot.send_message(uid, f"⌛ Your payment request #{rid} expired without verification. If you paid, contact {_support()}.")
                        except Exception: pass
            days = int(_num('EXPIRY_REMINDER_DAYS'))
            if days > 0:
                now = datetime.now()
                for uid, sub in list(user_subscriptions.items()):
                    exp = sub.get('expiry')
                    if not exp or exp <= now or uid in admin_ids: continue
                    if (exp - now) <= timedelta(days=days) and (uid, exp.date().isoformat()) not in _REMINDED:
                        _REMINDED.add((uid, exp.date().isoformat()))
                        mk = types.InlineKeyboardMarkup()
                        mk.add(types.InlineKeyboardButton("💎 Renew Now", callback_data="view_plans_cb"))
                        try: bot.send_message(uid, f"⏰ <b>Your plan expires on {exp:%d-%m-%Y}</b> ({(exp-now).days+1} day(s) left). Renew to keep your bots running!", reply_markup=mk, parse_mode='HTML')
                        except Exception: pass
        except Exception as e:
            logger.error(f"payments_housekeeping error: {e}")
        time.sleep(300)

def handle_plan_callbacks(call):
    """Handle every Plans/Payments callback. Returns True when handled."""
    data = call.data
    uid = call.from_user.id
    chat_id = call.message.chat.id
    mid_msg = call.message.message_id
    is_admin = uid in admin_ids
    try:
        if data == 'view_plans_cb':
            bot.answer_callback_query(call.id)
            send_plan_page(chat_id, uid, 0); return True

        if data.startswith('page_plan_'):
            bot.answer_callback_query(call.id)
            send_plan_page(chat_id, uid, int(data.split('_')[2]), mid_msg); return True

        if data.startswith('claim_free_'):
            plan = get_plan_by_id(int(data.split('_')[2]))
            if not plan or not is_free_plan(plan[1], plan[3]) or not _flag('FREE_PLAN_ENABLED'):
                bot.answer_callback_query(call.id, "Plan not available.", show_alert=True); return True
            rc, _ = _db_exec("INSERT OR IGNORE INTO free_plan_claimed (user_id) VALUES (?)", (uid,))
            if rc == 0:
                bot.answer_callback_query(call.id, "❌ You have already claimed the free plan once.", show_alert=True); return True
            activate_plan(uid, plan)
            bot.answer_callback_query(call.id, "Free plan activated!", show_alert=True)
            bot.send_message(chat_id, f"🎉 *{_md(plan[1])}* activated! You can now upload projects.", parse_mode='Markdown')
            return True

        if data.startswith('plcoupon_'):
            _, plan_id, page = data.split('_')
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "🎟️ <b>Send your coupon code</b> (or <code>remove</code> to clear it):\n\n/cancel to abort.", parse_mode='HTML')
            bot.register_next_step_handler(msg, process_coupon_input, int(plan_id), int(page)); return True

        if data.startswith('plbuy_'):
            bot.answer_callback_query(call.id)
            show_buy_methods(chat_id, uid, int(data.split('_')[1]), mid_msg); return True

        if data.startswith('plpm_'):
            _, plan_id, mid = data.split('_')
            bot.answer_callback_query(call.id)
            if mid == 'stars': send_stars_invoice(chat_id, uid, int(plan_id))
            else: show_method_screen(chat_id, uid, int(plan_id), int(mid))
            return True

        if data.startswith('plpaid_'):
            _, plan_id, mid = data.split('_')
            bot.answer_callback_query(call.id)
            start_paid_flow(chat_id, uid, int(plan_id), int(mid)); return True

        # ---------- admin only below ----------
        admin_prefixes = ('approve_pay_', 'reject_pay_', 'del_plan_', 'del_pay_', 'pps_', 'ppt_')
        admin_exact = ('add_plan_init', 'manage_plans', 'admin_pay_methods', 'add_pay_method', 'admin_pay_settings')
        if data in admin_exact or data.startswith(admin_prefixes):
            if not is_admin:
                bot.answer_callback_query(call.id, "⚠️ Admin permissions required.", show_alert=True); return True

            if data.startswith(('approve_pay_', 'reject_pay_')):
                approve = data.startswith('approve_pay_')
                ok, result = process_payment_decision(int(data.split('_')[2]), approve, uid)
                bot.answer_callback_query(call.id, "Done" if ok else result, show_alert=not ok)
                if ok:
                    try:
                        if call.message.content_type == 'photo':
                            bot.edit_message_caption(result, chat_id, mid_msg)
                        else:
                            bot.edit_message_text(result, chat_id, mid_msg)
                    except Exception: pass
                else:
                    try: bot.edit_message_reply_markup(chat_id, mid_msg, reply_markup=None)
                    except Exception: pass
                return True

            bot.answer_callback_query(call.id)

            if data == 'add_plan_init':
                msg = bot.send_message(chat_id,
                    "📝 *Add a plan* — send in this format:\n"
                    "`NAME | PROJECT LIMIT | PRICE | DAYS | FEATURES`\n\n"
                    "*Examples:*\n`BASIC | 5 | 99 INR | 30 | 1GB RAM, Priority Support`\n"
                    "`PRO | 15 | 499 INR | 30 | 2GB RAM`\n"
                    "`FREE TRIAL | 2 | 0 | 7 | Basic hosting`\n\n"
                    "Price: a number with a currency (base or local). `0` or a name containing FREE makes a one-time free plan.\n\n/cancel to abort.",
                    parse_mode='Markdown')
                bot.register_next_step_handler(msg, process_add_plan)
            elif data == 'manage_plans':
                plans = get_all_plans()
                if not plans:
                    bot.send_message(chat_id, "ℹ️ No plans yet. Use ➕ Add Plan."); return True
                markup = types.InlineKeyboardMarkup(row_width=2)
                for p in plans:
                    markup.row(types.InlineKeyboardButton(f"✏️ {p[1]} ({p[3]})", callback_data=f"ppt_ep_{p[0]}"),
                               types.InlineKeyboardButton("🗑️ Delete", callback_data=f"del_plan_{p[0]}"))
                bot.send_message(chat_id, "🛠️ *Manage plans* — edit a price or delete:", reply_markup=markup, parse_mode='Markdown')
            elif data.startswith('del_plan_'):
                delete_plan_db(int(data.split('_')[2]))
                bot.send_message(chat_id, "✅ Plan deleted. (Users who already bought it keep their subscription.)")
            elif data == 'admin_pay_methods':
                _send_or_edit(chat_id, _pay_methods_text(), _admin_pay_methods_markup(), mid_msg)
            elif data == 'add_pay_method':
                m = types.InlineKeyboardMarkup(row_width=2)
                m.add(*[types.InlineKeyboardButton(f"📱 {p}", callback_data=f"ppt_apm_{i}") for i, p in enumerate(MASTER_PRESETS)])
                m.add(types.InlineKeyboardButton("🌐 Payment Gateway", callback_data="ppt_apg"))
                m.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_pay_methods"))
                _send_or_edit(chat_id, "➕ <b>Add a payment method</b>\n\nPick a type. (⭐ Telegram Stars is built in — switch it on/off in Payment Settings.)", m, mid_msg)
            elif data.startswith('del_pay_'):
                _db_exec("DELETE FROM payment_methods WHERE id=?", (int(data.split('_')[2]),))
                _send_or_edit(chat_id, "✅ Method deleted.\n\n" + _pay_methods_text(), _admin_pay_methods_markup(), mid_msg)
            elif data == 'admin_pay_settings':
                _send_or_edit(chat_id, _settings_home_text(), _settings_home_markup(), mid_msg)
            elif data.startswith('pps_c'):
                ci = int(data[5:])
                txt, mk = _settings_cat_view(ci); _send_or_edit(chat_id, txt, mk, mid_msg)
            elif data.startswith('pps_t_'):
                key = data[6:]
                if key in PINFO and PINFO[key][1] == 'toggle':
                    set_setting(key, '0' if _flag(key) else '1')
                    txt, mk = _settings_cat_view(PINFO[key][2]); _send_or_edit(chat_id, txt, mk, mid_msg)
            elif data.startswith('pps_s_'):
                key = data[6:]
                if key in PINFO:
                    label, kind, _, hlp = PINFO[key]
                    hint = "a number" if kind == 'num' else "text (send <code>-</code> to clear)"
                    msg = bot.send_message(chat_id, f"✏️ <b>{_h(label)}</b>\n<i>{_h(hlp)}</i>\n\nCurrent: <code>{_h(_sv(key) or '—')}</code>\nSend {hint}:\n\n/cancel to abort.", parse_mode='HTML')
                    bot.register_next_step_handler(msg, process_set_value, key)
            elif data == 'ppt_history': _history_send(chat_id)
            elif data == 'ppt_pending': _pending_list_send(chat_id)
            elif data == 'ppt_revenue': _revenue_send(chat_id)
            elif data == 'ppt_export': _export_send(chat_id)
            elif data == 'ppt_coupons':
                txt, mk = _coupons_view(); _send_or_edit(chat_id, txt, mk, mid_msg)
            elif data == 'ppt_cadd':
                msg = bot.send_message(chat_id, "🎟️ Send: `CODE | PERCENT | MAX USES`\nExample: `WELCOME10 | 10 | 100` (0 = unlimited)\n\n/cancel to abort.", parse_mode='Markdown')
                bot.register_next_step_handler(msg, process_new_coupon)
            elif data.startswith('ppt_cdel_'):
                _db_exec("DELETE FROM coupons WHERE code=?", (data[9:],))
                txt, mk = _coupons_view(); _send_or_edit(chat_id, txt, mk, mid_msg)
            elif data.startswith('ppt_ctog_'):
                _db_exec("UPDATE coupons SET active = 1 - active WHERE code=?", (data[9:],))
                txt, mk = _coupons_view(); _send_or_edit(chat_id, txt, mk, mid_msg)
            elif data == 'ppt_resetfree':
                msg = bot.send_message(chat_id, "🔁 Send the *user ID* whose free-plan claim should be reset:\n\n/cancel to abort.", parse_mode='Markdown')
                bot.register_next_step_handler(msg, process_reset_free)
            elif data.startswith('ppt_ep_'):
                pid = int(data[7:])
                msg = bot.send_message(chat_id, "✏️ Send the new price (e.g. `99 INR`, `499 INR`, or `0`):\n\n/cancel to abort.", parse_mode='Markdown')
                bot.register_next_step_handler(msg, process_edit_plan_price, pid)
            elif data.startswith('ppt_apm_'):
                preset = MASTER_PRESETS[int(data[8:])]
                if preset == 'Other':
                    txt = "Send: `NAME | NUMBER/ID | INSTRUCTIONS`\nExample: `Amazon Pay | 98XXXXXXXX@apl | Send & share UTR`"
                else:
                    txt = f"Send: `NUMBER/ID | INSTRUCTIONS` for *{preset}*\nExample: `98XXXXXXXX@ybl | Pay as Friends & Family, then send the UTR`"
                msg = bot.send_message(chat_id, f"➕ {txt}\n\n/cancel to abort.", parse_mode='Markdown')
                bot.register_next_step_handler(msg, process_add_manual_method, preset)
            elif data == 'ppt_apg':
                msg = bot.send_message(chat_id, "🌐 Send: `NAME | PAYMENT LINK | INSTRUCTIONS`\nExample: `Razorpay | https://rzp.io/l/yourlink | Pay then send the payment ID`\n\n/cancel to abort.", parse_mode='Markdown')
                bot.register_next_step_handler(msg, process_add_gateway)
            return True
    except (ValueError, IndexError) as e:
        logger.error(f"Plan callback parse error for '{data}': {e}")
        try: bot.answer_callback_query(call.id, "Invalid action.", show_alert=True)
        except Exception: pass
        return True
    return False


# ============================================================
# --- Menus ---
# ============================================================
def create_main_menu_inline(user_id):
    """Inline main-menu buttons are disabled - the bottom keyboard already has every option."""
    return None
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton('📢 Updates Channel', url=f'https://t.me/{UPDATES_CHANNEL.replace("@", "")}'),
        types.InlineKeyboardButton('📤 Upload File', callback_data='upload'),
        types.InlineKeyboardButton('📂 Check Files', callback_data='check_files'),
        types.InlineKeyboardButton('⚡ Bot Speed', callback_data='speed'),
        types.InlineKeyboardButton('📊 Statistics', callback_data='stats'),
        types.InlineKeyboardButton('📦 Manual Install', callback_data='manual_install'),
        types.InlineKeyboardButton('👤 My Info', callback_data='my_info'),
        types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'),
        types.InlineKeyboardButton('💎 View Plans', callback_data='view_plans_cb'),
        types.InlineKeyboardButton('📡 Live Logs', callback_data='live_menu'),
    ]
    if user_id in admin_ids:
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3], buttons[4])
        markup.add(buttons[5], buttons[8])
        markup.add(buttons[9], types.InlineKeyboardButton('👑 Admin Panel', callback_data='admin_panel'))
        markup.add(buttons[6], buttons[7])
    else:
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3], buttons[4])
        markup.add(buttons[5], buttons[8])
        markup.add(buttons[9], buttons[6])
        markup.add(buttons[7])
    return markup

def create_reply_keyboard_main_menu(user_id):
    return _btn_build_keyboard(user_id)

def create_control_buttons(script_owner_id, project_name, is_running=True, back_callback='check_files'):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{script_owner_id}_{project_name}'),
            types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{script_owner_id}_{project_name}')
        )
        markup.row(
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{project_name}'),
            types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{script_owner_id}_{project_name}')
        )
        markup.row(
            types.InlineKeyboardButton("📡 Live Logs", callback_data=f'live_{script_owner_id}_{project_name}')
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{script_owner_id}_{project_name}'),
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{project_name}')
        )
        markup.row(
            types.InlineKeyboardButton("📜 View Logs", callback_data=f'logs_{script_owner_id}_{project_name}')
        )
    markup.row(
        types.InlineKeyboardButton("📤 Export Data", callback_data=f'exp_{script_owner_id}_{project_name}'),
        types.InlineKeyboardButton("📥 Import Data", callback_data=f'imp_{script_owner_id}_{project_name}')
    )
    markup.row(
        types.InlineKeyboardButton("✏️ Change Main File", callback_data=f'changemain_{script_owner_id}_{project_name}')
    )
    back_label = "🔙 Back to Projects" if back_callback == 'check_files' else "🔙 Back to User's Projects"
    markup.add(types.InlineKeyboardButton(back_label, callback_data=back_callback))
    return markup

def _extract_back_callback(call):
    """Read the back button's callback_data from the current message's inline keyboard."""
    try:
        keyboard = call.message.reply_markup
        if keyboard:
            for row in keyboard.keyboard:
                for btn in row:
                    if btn.callback_data and btn.callback_data.startswith('admin_user_files_'):
                        return btn.callback_data
    except Exception:
        pass
    return 'check_files'

def create_admin_panel():
    B = types.InlineKeyboardButton
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(B('💳 Subscriptions', callback_data='subscription'), B('📢 Broadcast', callback_data='broadcast'))
    markup.row(B('👥 User Management', callback_data='user_management'), B('📋 Pending Files', callback_data='pending_files'))
    markup.row(B('🔓 Unlock Bot' if bot_locked else '🔒 Lock Bot', callback_data='unlock_bot' if bot_locked else 'lock_bot'),
               B('🟢 Run All Scripts', callback_data='run_all_scripts'))
    markup.row(B('📢 Channel Add', callback_data='channel_add'), B('📊 Statistics', callback_data='stats'))
    markup.row(B('➕ Add Admin', callback_data='add_admin'), B('➖ Remove Admin', callback_data='remove_admin'))
    markup.row(B('📋 List Admins', callback_data='list_admins'), B('🛡 Admin Roles', callback_data='ar_home'), B('🔑 My Access', callback_data='ar_me'))
    markup.row(B('➕ Add Plan', callback_data='add_plan_init'), B('🗑️ Manage Plans', callback_data='manage_plans'))
    markup.row(B('💳 Pay Methods', callback_data='admin_pay_methods'), B('⚙️ Payment Settings', callback_data='admin_pay_settings'))
    markup.row(B('🧰 Admin Tools (33)', callback_data='adm_home'), B('🎛️ Customize Buttons', callback_data='bc_home'))
    markup.row(B('👥 Users Directory', callback_data='ud_home'), B('🏆 Leaderboard', callback_data='lb_a_home'))
    markup.row(B('🔗 Refer & Points', callback_data='rp_a_home'), B('🎟 Redeem Codes', callback_data='cd_home'))
    markup.row(B('✏️ Edit Messages', callback_data='mx_home'), B(f'🧩 Admin Toolbox ({len(AP_OPTS)})', callback_data='ap_h'))
    markup.row(B('🖥 System Monitor (RAM/Storage)', callback_data='sm_home'), B('💾 Backup & Restore', callback_data='bkp_home'))
    markup.row(B('⭐ Telegram Stars: ' + ('ON ✅' if _flag('STARS_ENABLED') else 'OFF ❌'), callback_data='cd_stars'),
               B('🎨 Colors: ' + ('ON ✅' if _style_enabled() else 'OFF ❌'), callback_data='bk_t_ap'))
    markup.row(B('⚙️ Button Color Settings', callback_data='bk_home'))
    markup.row(B('🛂 Upload Approval: ' + ('🤖 Auto' if _upload_mode() == 'auto' else '✋ Manual'), callback_data='ua_home'))
    markup.row(B('🔙 Back to Main', callback_data='back_to_main'))
    markup._adm_panel = True
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Subscription', callback_data='add_subscription'),
        types.InlineKeyboardButton('➖ Remove Subscription', callback_data='remove_subscription')
    )
    markup.row(types.InlineKeyboardButton('🔍 Check Subscription', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_user_management_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('🚫 Ban User', callback_data='ban_user'),
        types.InlineKeyboardButton('✅ Unban User', callback_data='unban_user')
    )
    markup.row(
        types.InlineKeyboardButton('👤 User Info', callback_data='user_info'),
        types.InlineKeyboardButton('👥 All Users', callback_data='all_users')
    )
    markup.row(
        types.InlineKeyboardButton('🔧 Set User Limit', callback_data='set_user_limit'),
        types.InlineKeyboardButton('🗑️ Remove User Limit', callback_data='remove_user_limit')
    )
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

# ============================================================
# --- Script Running ---
# ============================================================
def run_script(script_path, script_owner_id, user_folder, project_name, message_obj_for_reply, attempt=1, skip_deps_install=False):
    if attempt == 1 and not _ap_run_gate(script_owner_id, message_obj_for_reply, project_name): return
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed to run project `{project_name}` after {max_attempts} attempts.", parse_mode='Markdown')
        return
    script_key = f"{script_owner_id}_{project_name}"
    logger.info(f"Attempt {attempt} to run: {script_path} (Key: {script_key})")
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj_for_reply, f"❌ Script for `{project_name}` not found!", parse_mode='Markdown')
            remove_user_file_db(script_owner_id, project_name)
            return
        if attempt == 1:
            if not skip_deps_install:
                if not install_requirements_if_present(user_folder, script_owner_id, message_obj_for_reply):
                    return
            check_proc = None
            try:
                check_proc = subprocess.Popen([sys.executable, script_path], cwd=user_folder,
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                              text=True, encoding='utf-8', errors='ignore',
                                              env=get_clean_env())
                stdout, stderr = check_proc.communicate(timeout=5)
                rc = check_proc.returncode
                if rc != 0 and stderr:
                    match = re.search(r"ModuleNotFoundError: No module named '(.+?)'", stderr)
                    if match:
                        module_name = match.group(1).strip()
                        if attempt_install_pip(module_name, message_obj_for_reply):
                            bot.reply_to(message_obj_for_reply, f"🔄 Package installed. Retrying `{project_name}`...", parse_mode='Markdown')
                            time.sleep(2)
                            threading.Thread(target=run_script,
                                             args=(script_path, script_owner_id, user_folder, project_name,
                                                   message_obj_for_reply, attempt + 1, True)).start()
                            return
                        else:
                            bot.reply_to(message_obj_for_reply, f"❌ Package install failed for `{project_name}`.", parse_mode='Markdown')
                            return
                    err_summary = stderr[:500]
                    bot.reply_to(message_obj_for_reply, f"❌ Error in `{project_name}`:\n```\n{err_summary}\n```", parse_mode='Markdown')
                    return
            except subprocess.TimeoutExpired:
                logger.info("Python pre-check timed out. Proceeding to long run.")
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()
            except FileNotFoundError:
                bot.reply_to(message_obj_for_reply, "❌ Python interpreter not found!")
                return
            except Exception as e:
                bot.reply_to(message_obj_for_reply, f"❌ Pre-check error: {e}")
                return
            finally:
                if check_proc and check_proc.poll() is None:
                    check_proc.kill(); check_proc.communicate()

        log_file_path = os.path.join(user_folder, f"{project_name}.log")
        log_file = None
        try:
            log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            bot.reply_to(message_obj_for_reply, f"❌ Failed to open log file: {e}")
            return
        try:
            startupinfo = None; creationflags = 0
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                [sys.executable, script_path], cwd=user_folder,
                stdout=log_file, stderr=log_file, stdin=subprocess.PIPE,
                startupinfo=startupinfo, creationflags=creationflags,
                encoding='utf-8', errors='ignore',
                env=get_clean_env()
            )
            bot_scripts[script_key] = {
                'process': process, 'log_file': log_file, 'project_name': project_name,
                'chat_id': message_obj_for_reply.chat.id, 'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder,
                'type': 'py', 'script_key': script_key
            }
            bot.reply_to(message_obj_for_reply, M('started_py', project=project_name, pid=process.pid))
        except Exception as e:
            if log_file and not log_file.closed: log_file.close()
            bot.reply_to(message_obj_for_reply, f"❌ Error starting `{project_name}`: {md_escape(e)}", parse_mode='Markdown')
            if script_key in bot_scripts: del bot_scripts[script_key]
    except Exception as e:
        bot.reply_to(message_obj_for_reply, f"❌ Unexpected error running `{project_name}`: {md_escape(e)}", parse_mode='Markdown')
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]

def run_js_script(script_path, script_owner_id, user_folder, project_name, message_obj_for_reply, attempt=1, skip_deps_install=False):
    if attempt == 1 and not _ap_run_gate(script_owner_id, message_obj_for_reply, project_name): return
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed to run `{project_name}` after {max_attempts} attempts.", parse_mode='Markdown')
        return
    script_key = f"{script_owner_id}_{project_name}"
    logger.info(f"Attempt {attempt} to run JS: {script_path} (Key: {script_key})")
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj_for_reply, f"❌ Script `{project_name}` not found!", parse_mode='Markdown')
            remove_user_file_db(script_owner_id, project_name)
            return
        if attempt == 1:
            if not skip_deps_install:
                if not install_package_json_if_present(user_folder, script_owner_id, message_obj_for_reply):
                    return
            check_proc = None
            try:
                check_proc = subprocess.Popen(['node', script_path], cwd=user_folder,
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                              text=True, encoding='utf-8', errors='ignore',
                                              env=get_clean_env())
                stdout, stderr = check_proc.communicate(timeout=5)
                rc = check_proc.returncode
                if rc != 0 and stderr:
                    match_js = re.search(r"Cannot find module '(.+?)'", stderr)
                    if match_js:
                        module_name = match_js.group(1).strip().strip("'\"")
                        if not module_name.startswith('.') and not module_name.startswith('/'):
                            if attempt_install_npm(module_name, user_folder, message_obj_for_reply):
                                bot.reply_to(message_obj_for_reply, f"🔄 NPM Install OK. Retrying `{project_name}`...", parse_mode='Markdown')
                                time.sleep(2)
                                threading.Thread(target=run_js_script,
                                                 args=(script_path, script_owner_id, user_folder, project_name,
                                                       message_obj_for_reply, attempt + 1, True)).start()
                                return
                            else:
                                bot.reply_to(message_obj_for_reply, f"❌ NPM Install failed for `{project_name}`.", parse_mode='Markdown')
                                return
                    err_summary = stderr[:500]
                    bot.reply_to(message_obj_for_reply, f"❌ JS error in `{project_name}`:\n```\n{err_summary}\n```", parse_mode='Markdown')
                    return
            except subprocess.TimeoutExpired:
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()
            except FileNotFoundError:
                bot.reply_to(message_obj_for_reply, "❌ `node` not found. Install Node.js.", parse_mode='Markdown')
                return
            except Exception as e:
                bot.reply_to(message_obj_for_reply, f"❌ JS pre-check error: {e}")
                return
            finally:
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()

        log_file_path = os.path.join(user_folder, f"{project_name}.log")
        log_file = None
        try:
            log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            bot.reply_to(message_obj_for_reply, f"❌ Failed to open log file: {e}")
            return
        try:
            startupinfo = None; creationflags = 0
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                ['node', script_path], cwd=user_folder,
                stdout=log_file, stderr=log_file, stdin=subprocess.PIPE,
                startupinfo=startupinfo, creationflags=creationflags,
                encoding='utf-8', errors='ignore',
                env=get_clean_env()
            )
            bot_scripts[script_key] = {
                'process': process, 'log_file': log_file, 'project_name': project_name,
                'chat_id': message_obj_for_reply.chat.id, 'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder,
                'type': 'js', 'script_key': script_key
            }
            bot.reply_to(message_obj_for_reply, M('started_js', project=project_name, pid=process.pid))
        except FileNotFoundError:
            if log_file and not log_file.closed: log_file.close()
            bot.reply_to(message_obj_for_reply, "❌ `node` not found for long run.", parse_mode='Markdown')
            if script_key in bot_scripts: del bot_scripts[script_key]
        except Exception as e:
            if log_file and not log_file.closed: log_file.close()
            bot.reply_to(message_obj_for_reply, f"❌ Error starting `{project_name}`: {md_escape(e)}", parse_mode='Markdown')
            if script_key in bot_scripts: del bot_scripts[script_key]
    except Exception as e:
        bot.reply_to(message_obj_for_reply, f"❌ Unexpected error running `{project_name}`: {md_escape(e)}", parse_mode='Markdown')
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]

# ============================================================
# --- File Handling ---
# ============================================================
def process_zip_file(file_content, file_name_zip, user_id, user_folder, message, project_name=None, main_file_override=None):
    """Extract and run a pre-approved ZIP. Called after admin approval — no security scan."""
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_run_")
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as f: f.write(file_content)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.infolist():
                member_path = os.path.abspath(os.path.join(temp_dir, member.filename))
                if not member_path.startswith(os.path.abspath(temp_dir)):
                    raise zipfile.BadZipFile(f"Unsafe path: {member.filename}")
            zip_ref.extractall(temp_dir)

        extracted_items = [f for f in os.listdir(temp_dir) if f != file_name_zip]
        py_files = [f for f in extracted_items if f.endswith('.py')]
        js_files = [f for f in extracted_items if f.endswith('.js')]
        req_file = 'requirements.txt' if 'requirements.txt' in extracted_items else None
        pkg_json = 'package.json' if 'package.json' in extracted_items else None

        if req_file:
            req_path = os.path.join(temp_dir, req_file)
            bot.send_message(user_id, f"🔄 Installing Python deps from `{req_file}`...", parse_mode='Markdown')
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', req_path],
                               capture_output=True, text=True, check=True, encoding='utf-8',
                               env=get_clean_env())
                bot.send_message(user_id, f"✅ Python deps from `{req_file}` installed.", parse_mode='Markdown')
            except subprocess.CalledProcessError as e:
                bot.send_message(user_id, f"❌ Failed to install Python deps.\n```\n{(e.stderr or e.stdout)[:2000]}\n```", parse_mode='Markdown'); return
            except Exception as e:
                bot.send_message(user_id, f"❌ Error installing Python deps: {e}"); return

        if pkg_json:
            bot.send_message(user_id, f"🔄 Installing Node deps from `{pkg_json}`...", parse_mode='Markdown')
            try:
                subprocess.run(['npm', 'install'], capture_output=True, text=True,
                               check=True, cwd=temp_dir, encoding='utf-8',
                               env=get_clean_env())
                bot.send_message(user_id, f"✅ Node deps from `{pkg_json}` installed.", parse_mode='Markdown')
            except FileNotFoundError:
                bot.send_message(user_id, "❌ `npm` not found.", parse_mode='Markdown'); return
            except subprocess.CalledProcessError as e:
                bot.send_message(user_id, f"❌ Failed Node deps.\n```\n{(e.stderr or e.stdout)[:2000]}\n```", parse_mode='Markdown'); return
            except Exception as e:
                bot.send_message(user_id, f"❌ Error installing Node deps: {e}"); return

        if main_file_override:
            main_script_name = main_file_override
            file_type = 'py' if main_script_name.endswith('.py') else 'js'
        else:
            main_script_name = None; file_type = None
            preferred_py = ['main.py', 'bot.py', 'app.py']
            preferred_js = ['index.js', 'main.js', 'bot.js', 'app.js']
            for p in preferred_py:
                if p in py_files: main_script_name = p; file_type = 'py'; break
            if not main_script_name:
                for p in preferred_js:
                    if p in js_files: main_script_name = p; file_type = 'js'; break
            if not main_script_name:
                if py_files: main_script_name = py_files[0]; file_type = 'py'
                elif js_files: main_script_name = js_files[0]; file_type = 'js'
        if not main_script_name:
            bot.send_message(user_id, "❌ No `.py` or `.js` script found in archive!", parse_mode='Markdown'); return

        if not project_name:
            project_name = os.path.splitext(file_name_zip)[0]
        project_folder = get_user_folder(user_id, project_name)

        for item_name in extracted_items:
            src = os.path.join(temp_dir, item_name)
            dst = os.path.join(project_folder, item_name)
            if os.path.isdir(dst): shutil.rmtree(dst)
            elif os.path.exists(dst): os.remove(dst)
            shutil.move(src, dst)

        save_user_file(user_id, project_name, main_script_name, file_type)
        main_script_path = os.path.join(project_folder, main_script_name)
        bot.send_message(user_id, f"✅ Project `{project_name}` extracted. Starting `{main_script_name}`...", parse_mode='Markdown')
        if file_type == 'py':
            threading.Thread(target=run_script, args=(main_script_path, user_id, project_folder, project_name, message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(main_script_path, user_id, project_folder, project_name, message)).start()

    except zipfile.BadZipFile as e:
        bot.send_message(user_id, f"❌ Invalid/corrupted ZIP: {e}")
    except Exception as e:
        logger.error(f"❌ Error processing approved zip for {user_id}: {e}", exc_info=True)
        bot.send_message(user_id, f"❌ Error processing zip: {str(e)}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir)
            except Exception: pass

def handle_js_file(file_path, script_owner_id, user_folder, file_name, message, project_name=None):
    if not project_name:
        project_name = os.path.splitext(file_name)[0]
    try:
        save_user_file(script_owner_id, project_name, file_name, 'js')
        auto_install_js_requires(file_path, user_folder, script_owner_id, message)
        threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, project_name, message, 1, True)).start()
    except Exception as e:
        bot.reply_to(message, f"❌ Error processing JS file: {e}")

def handle_py_file(file_path, script_owner_id, user_folder, file_name, message, project_name=None):
    if not project_name:
        project_name = os.path.splitext(file_name)[0]
    try:
        save_user_file(script_owner_id, project_name, file_name, 'py')
        auto_install_py_imports(file_path, user_folder, script_owner_id, message)
        threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, project_name, message, 1, True)).start()
    except Exception as e:
        bot.reply_to(message, f"❌ Error processing Python file: {e}")

# ============================================================
# --- Logic Functions ---
# ============================================================
def _user_rank(user_id):
    """Return (rank_text, expiry_info) for welcome / profile screens."""
    if user_id == OWNER_ID: return "👑 Owner", ""
    if user_id in admin_ids: return _adm_rank(user_id), ""
    if user_id in user_subscriptions:
        expiry_date = user_subscriptions[user_id].get('expiry')
        if expiry_date and expiry_date > datetime.now():
            days_left = (expiry_date - datetime.now()).days
            return f"⭐ {_md(get_plan_label(user_id))}", f"\n⏳ Subscription expires in: *{days_left} days*"
        remove_subscription_db(user_id)
    return "🆓 Free User", ""

def _logic_send_welcome(message):
    user_id = message.from_user.id
    touch_user(message.from_user)
    chat_id = message.chat.id
    user_name = message.from_user.first_name
    user_username = message.from_user.username
    photo_file_id = None

    if is_user_banned(user_id):
        bot.send_message(chat_id, M('banned'))
        return

    if not check_force_join(message):
        return

    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, M('locked'))
        return

    if user_id not in active_users and str(get_setting('REG_OPEN', '1')) != '1' and user_id not in admin_ids:
        bot.send_message(chat_id, M('reg_closed'))
        return

    if user_id not in active_users:
        add_active_user(user_id)
        if user_id not in user_files and str(get_setting('NOTIFY_NEW_USERS', '1')) == '1':
            user_bio = "No bio"
            photo_file_id = None
            try: user_bio = bot.get_chat(user_id).bio or "No bio"
            except Exception: pass
            try:
                photos = bot.get_user_profile_photos(user_id, limit=1)
                if photos.photos: photo_file_id = photos.photos[0][-1].file_id
            except Exception: pass
            try:
                def _md_escape(text):
                    for ch in ['\\', '_', '*', '`', '[']:
                        text = text.replace(ch, '\\' + ch)
                    return text
                safe_name = _md_escape(str(user_name))
                safe_username = _md_escape(str(user_username)) if user_username else 'N/A'
                safe_bio = _md_escape(str(user_bio))
                notif = (
                    f"🎉 *New User Joined!*\n"
                    f"──────────────────────\n\n"
                    f"👤 *Name:* {safe_name}\n"
                    f"✳️ *Username:* @{safe_username}\n"
                    f"🆔 *ID:* `{user_id}`\n"
                    f"📝 *Bio:* {safe_bio}\n"
                    f"──────────────────────")
                bot.send_message(OWNER_ID, notif, parse_mode='Markdown')
                if photo_file_id: bot.send_photo(OWNER_ID, photo_file_id, caption=f"New user {user_id}")
            except Exception as e: logger.error(f"Failed to notify owner: {e}")

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    user_status, expiry_info = _user_rank(user_id)

    import html as _hw
    if user_id == OWNER_ID: _rank = "👑 Owner"
    elif user_id in admin_ids: _rank = _adm_rank(user_id)
    elif has_active_sub(user_id):
        _dl = (user_subscriptions[user_id]['expiry'] - datetime.now()).days
        _rank = f"⭐ {_hw.escape(get_plan_label(user_id))} • {_dl}d left"
    else: _rank = "🆓 Free User"
    _limit = "∞" if limit_str == "Unlimited" else limit_str
    _bar_total = 10 if _limit == "∞" else max(1, int(file_limit))
    _filled = 0 if _limit == "∞" else min(10, round(10 * current_files / _bar_total))
    _usage = ("▰" * _filled + "▱" * (10 - _filled)) if _limit != "∞" else "▰▰▰▰▰▰▰▰▰▰"
    _hr = (datetime.utcnow() + timedelta(hours=5, minutes=30)).hour
    _greet = "Good Morning" if 5 <= _hr < 12 else ("Good Afternoon" if 12 <= _hr < 17 else ("Good Evening" if 17 <= _hr < 21 else "Good Night"))
    _user_line = f"@{_hw.escape(user_username)}" if user_username else "—"
    _bn = _hw.escape(" ".join(str(get_setting('BOT_NAME', BOT_NAME_DEFAULT))))
    _wn = str(get_setting('WELCOME_NOTE', '') or '').strip()

    def _build(premium):
        e = (lambda slot: pe(slot, premium))
        t = (
            f"{e('logo')} <b>{_bn}</b> {e('logo')}\n"
            f"<i>{M('welcome_tagline')}</i>\n"
            "◆━━━━━━━━━━━━━━━━━━━◆\n\n"
            f"<i>{_greet},</i> <b>{_hw.escape(str(user_name))}</b>\n\n"
            f"{e('account')} <b>ACCOUNT</b>\n"
            f"┣ {e('id')} ID · <code>{user_id}</code>\n"
            f"┣ {e('user')} Username · {_user_line}\n"
            f"┣ {e('rank')} Membership · <b>{_rank}</b>\n"
            f"┗ {e('projects')} Projects · <b>{current_files}</b> / <b>{_limit}</b>  <code>{_usage}</code>\n\n"
            f"{e('services')} <b>SERVICES</b>\n"
            + "".join(f"{e('bullet')} {ln.strip()}\n" for ln in str(M('welcome_services')).split("\n") if ln.strip()) + "\n"
            f"{e('footer')} <i>{M('welcome_footer')}</i>"
        )
        if _wn: t += f"\n\n📌 {_hw.escape(_wn)}"
        return t

    main_reply_markup = create_reply_keyboard_main_menu(user_id)
    texts = [_build(True), _build(False)] if _has_premium_emoji() else [_build(False)]
    sent_photo = False
    _wphoto = _btn_cfg().get('welcome_photo')
    if _wphoto:
        try: bot.send_photo(chat_id, _wphoto); sent_photo = True
        except Exception as e: logger.warning(f"Welcome photo failed, using default welcome: {e}")
    for t in texts:
        try:
            if sent_photo or not photo_file_id:
                bot.send_message(chat_id, t, reply_markup=main_reply_markup, parse_mode='HTML')
            else:
                bot.send_photo(chat_id, photo_file_id, caption=t, reply_markup=main_reply_markup, parse_mode='HTML')
            return
        except Exception as e:
            logger.warning(f"Welcome variant failed ({'premium emoji' if t is texts[0] and len(texts) > 1 else 'plain'}): {e}")
    try: bot.send_message(chat_id, re.sub(r"<[^>]+>", "", texts[-1]).replace("&amp;", "&"), reply_markup=main_reply_markup)
    except Exception as fe: logger.error(f"Fallback welcome failed: {fe}")

def _logic_updates_channel(message):
    bot.reply_to(
        message,
        M('updates_channel'),
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("🚀 Join Updates Channel", url=f'https://t.me/{UPDATES_CHANNEL.replace("@", "")}')
        )
    )

def _limit_reached_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💎 View Plans", callback_data='view_plans_cb'))
    return markup

def _upl_vars(uid):
    lim = get_user_file_limit(uid)
    return {'used': get_user_file_count(uid), 'limit': ('Unlimited' if lim == float('inf') else lim), 'maxmb': get_max_upload_bytes() // 1048576}

def _logic_upload_file(message):
    user_id = message.from_user.id
    if not _ap_upload_gate(message): return
    if is_user_banned(user_id):
        bot.reply_to(message, M('banned'))
        return
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, M('locked_upload'))
        return
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.reply_to(message, M('upload_limit', used=current_files, limit=limit_str), reply_markup=_limit_reached_markup())
        return
    bot.reply_to(message, M('upload_prompt', **_upl_vars(user_id)))

def _projects_text(uid, empty=False):
    fl = user_files.get(uid, []); run = sum(1 for pn, _m, _t in fl if is_bot_running(uid, pn))
    lim = get_user_file_limit(uid); lim = 'Unlimited' if lim == float('inf') else lim
    if empty or not fl:
        return ("✦ <b>𝗠𝗬  𝗣𝗥𝗢𝗝𝗘𝗖𝗧𝗦</b> ✦\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n<blockquote><i>No projects yet.</i>\nTap 📤 Upload File to deploy your first bot.</blockquote>")
    return ("✦ <b>𝗠𝗬  𝗣𝗥𝗢𝗝𝗘𝗖𝗧𝗦</b> ✦\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            f"<blockquote>🟢 Running ▸ <b>{run}</b>\n🔴 Stopped ▸ <b>{len(fl) - run}</b>\n📁 Slots ▸ <b>{len(fl)} / {lim}</b></blockquote>\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n<i>◇ Select a project to manage it.</i>")

def _logic_check_files(message):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.reply_to(message, _projects_text(user_id, True), parse_mode='HTML')
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for project_name, main_file, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, project_name)
        status_icon = "🟢" if is_running else "🔴"
        markup.add(types.InlineKeyboardButton(f"{status_icon} {project_name}", callback_data=f'file_{user_id}_{project_name}'))
    bot.reply_to(message, _projects_text(user_id), reply_markup=markup, parse_mode='HTML')

def _user_level(user_id):
    if user_id == OWNER_ID: return "👑 Owner"
    if user_id in admin_ids: return _adm_rank(user_id)
    if has_active_sub(user_id): return f"⭐ {get_plan_label(user_id)}"
    return "🆓 Free User"

def _speed_measure(started):
    """Returns (response_ms, telegram_ping_ms, system_ms)."""
    t = time.perf_counter()
    try: bot.get_me()
    except Exception: pass
    tg_ms = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    psutil.cpu_percent(interval=None); os.getpid()
    sys_ms = (time.perf_counter() - t) * 1000
    response_ms = max((time.time() - started) * 1000, tg_ms)
    return response_ms, tg_ms, sys_ms

def _speed_rating(ms):
    if ms < 150: return "🚀 Ultra Fast"
    if ms < 300: return "⚡ Fast"
    if ms < 600: return "✅ Good"
    if ms < 1000: return "⚠️ Moderate"
    return "🐢 Slow"

def _speed_bar(ms, width=10):
    """Full bar = fast. 0ms -> 10 blocks, >=1000ms -> 1 block."""
    filled = max(1, min(width, round(width * (1 - min(ms, 1000) / 1000))))
    return "▰" * filled + "▱" * (width - filled)

def _speed_text(user_id, response_ms, tg_ms, sys_ms):
    running = [i for i in list(bot_scripts.values()) if i.get('process') and is_bot_running(i.get('script_owner_id'), i.get('project_name'))]
    mine = [i['start_time'] for i in running if i.get('script_owner_id') == user_id and i.get('start_time')]
    uptime = _format_uptime((datetime.now() - min(mine)).total_seconds()) if mine else "–"
    ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
    worst = max(response_ms, tg_ms)
    return (
        "╭─────────────────────╮\n"
        "   ⚡ <b>BOT SPEED MONITOR</b>\n"
        "╰─────────────────────╯\n\n"
        "┏━ 📶 <b>Performance</b>\n"
        f"┃ ⏱ Response Time  <code>{response_ms:.1f} ms</code>\n"
        f"┃ 📡 Telegram Ping   <code>{tg_ms:.1f} ms</code>\n"
        f"┃ 💻 System Latency <code>{sys_ms:.2f} ms</code>\n"
        f"┃ 🏎 Rating  {_speed_rating(worst)}\n"
        f"┗ <code>{_speed_bar(worst)}</code>\n\n"
        "┏━ 🤖 <b>Hosting</b>\n"
        f"┃ ⏳ Your Bot Uptime  <b>{uptime}</b>\n"
        f"┗ 🟢 Total Bots Running  <b>{len(running)}</b>\n\n"
        f"🌐 <i>Server Time (IST)</i>\n"
        f"🕒 <code>{ist.strftime('%d-%m-%Y • %H:%M:%S')}</code>")

def _speed_markup():
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🔄 Refresh Speed", callback_data="speed"))
    return m

def _logic_bot_speed(message):
    started = time.time()
    try:
        sent = bot.send_message(message.chat.id, "🏃 Testing speed...", reply_to_message_id=message.message_id)
        r, tg, sy = _speed_measure(started)
        bot.edit_message_text(_speed_text(message.from_user.id, r, tg, sy), message.chat.id, sent.message_id,
                              parse_mode='HTML', reply_markup=_speed_markup())
    except Exception as e:
        logger.error(f"Error during speed test: {e}")
        bot.send_message(message.chat.id, "❌ Error during speed test.")

def _logic_contact_owner(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('💬 Chat with Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
    bot.reply_to(message, M('contact_owner'), reply_markup=markup)

def _info_text(user_id, user_name, user_username):
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    expiry_info = ""
    if user_id == OWNER_ID:
        user_status = "👑 Owner"
    elif user_id in admin_ids:
        user_status = "🛡️ Admin"
    elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry') and user_subscriptions[user_id]['expiry'] > datetime.now():
        expiry_date = user_subscriptions[user_id]['expiry']
        user_status = f"⭐ {_md(get_plan_label(user_id))}"
        days_left = (expiry_date - datetime.now()).days
        hours_left = int(((expiry_date - datetime.now()).seconds) / 3600)
        expiry_info = f"\n⏳ *Subscription Expiry:* {expiry_date.strftime('%Y-%m-%d %H:%M')}\n📅 *Days Remaining:* `{days_left}d {hours_left}h`"
    else:
        user_status = "🆓 Free User"
        if user_id in user_subscriptions: remove_subscription_db(user_id)
    running_count = sum(
        1 for sk in list(bot_scripts.keys())
        if sk.startswith(f"{user_id}_") and is_bot_running(user_id, sk.split('_', 1)[1])
    )
    is_banned = "🚫 Yes" if is_user_banned(user_id) else "✅ No"
    return (
        f"👤 *My Profile*\n"
        f"──────────────────────\n\n"
        f"🆔 *User ID:* `{user_id}`\n"
        f"📛 *Name:* {user_name}\n"
        f"✳️ *Username:* `@{user_username or 'Not set'}`\n"
        f"🏖️ *Rank:* {user_status}{expiry_info}\n"
        f"🚫 *Banned:* {is_banned}\n\n"
        f"──────────────────────\n"
        f"📁 *Projects:* `{current_files} / {limit_str}`\n"
        f"🟢 *Running Scripts:* `{running_count}`\n"
        f"──────────────────────"
    )

def _logic_my_info(message):
    return _logic_my_info_v2(message)

def _logic_subscriptions_panel(message):
    if not _can(message.from_user.id, 'subs'):
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    bot.reply_to(message, "💳 *Subscription Management*", reply_markup=create_subscription_menu(), parse_mode='Markdown')

def _format_uptime(seconds: float) -> str:
    total = int(seconds)
    d, rem = divmod(total, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)

def _logic_statistics(message):
    user_id = message.from_user.id
    total_users = len(active_users)
    total_files = sum(len(f) for f in user_files.values())
    running_count = 0
    user_running = 0
    for sk, si in list(bot_scripts.items()):
        owner_id_str = sk.split('_', 1)[0]
        if is_bot_running(int(owner_id_str), si['project_name']):
            running_count += 1
            if int(owner_id_str) == user_id: user_running += 1

    uptime_str = _format_uptime(time.time() - BOT_START_TIME)
    stats_msg = ("✦ <b>𝗕𝗢𝗧  𝗦𝗧𝗔𝗧𝗜𝗦𝗧𝗜𝗖𝗦</b> ✦\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "<b>◈ COMMUNITY</b>\n"
        f"<blockquote>👥 Users ▸ <b>{total_users}</b>\n🚫 Banned ▸ <b>{len(banned_users)}</b></blockquote>\n"
        "<b>◈ HOSTING</b>\n"
        f"<blockquote>📂 Projects ▸ <b>{total_files}</b>\n🟢 Running bots ▸ <b>{running_count}</b>\n🤖 Your running bots ▸ <b>{user_running}</b></blockquote>\n"
        "<b>◈ SYSTEM</b>\n"
        f"<blockquote>⏱ Uptime ▸ <b>{uptime_str}</b>\n🔒 Status ▸ <b>{'🔴 Locked' if bot_locked else '🟢 Unlocked'}</b></blockquote>")
    try:
        bot.reply_to(message, stats_msg, parse_mode='HTML')
    except Exception:
        plain = re.sub(r'<[^>]+>', '', stats_msg)
        try: bot.reply_to(message, plain)
        except Exception as e: logger.error(f"Stats send failed: {e}")

def _logic_broadcast_init(message):
    if not _can(message.from_user.id, 'broadcast'):
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    msg = bot.reply_to(message, "📢 Send message to broadcast to all active users.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def _logic_toggle_lock_bot(message):
    if not _can(message.from_user.id, 'lock'):
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    global bot_locked
    bot_locked = not bot_locked
    status = "locked 🔒" if bot_locked else "unlocked 🔓"
    logger.warning(f"Bot {status} by Admin {message.from_user.id}")
    bot.reply_to(message, f"Bot has been *{status}*.", parse_mode='Markdown',
                 reply_markup=create_reply_keyboard_main_menu(message.from_user.id))

def _logic_admin_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    bot.reply_to(message, _admin_panel_text(), reply_markup=create_admin_panel(), parse_mode='Markdown')

def _logic_run_all_scripts(message_or_call):
    if isinstance(message_or_call, telebot.types.Message):
        admin_user_id = message_or_call.from_user.id
        admin_chat_id = message_or_call.chat.id
        reply_func = lambda text, **kw: bot.reply_to(message_or_call, text, **kw)
        admin_msg_obj = message_or_call
    elif isinstance(message_or_call, telebot.types.CallbackQuery):
        admin_user_id = message_or_call.from_user.id
        admin_chat_id = message_or_call.message.chat.id
        bot.answer_callback_query(message_or_call.id)
        reply_func = lambda text, **kw: bot.send_message(admin_chat_id, text, **kw)
        admin_msg_obj = message_or_call.message
    else: return

    if not _can(admin_user_id, 'lock'):
        reply_func("⚠️ Admin permissions required.")
        return

    reply_func("⏳ Starting all user scripts... (installing deps where needed)")
    started_count = 0; skipped_files = 0

    def _start_one(target_user_id, project_name, main_file, file_type, user_folder, file_path):
        try:
            if file_type == 'py':
                if not install_requirements_if_present(user_folder, target_user_id, admin_msg_obj):
                    return
                run_script(file_path, target_user_id, user_folder, project_name, admin_msg_obj,
                           attempt=1, skip_deps_install=True)
            elif file_type == 'js':
                if not install_package_json_if_present(user_folder, target_user_id, admin_msg_obj):
                    return
                run_js_script(file_path, target_user_id, user_folder, project_name, admin_msg_obj,
                              attempt=1, skip_deps_install=True)
        except Exception as e:
            logger.error(f"Error starting {project_name} for {target_user_id}: {e}")

    all_user_files_snapshot = dict(user_files)
    for target_user_id, files_for_user in all_user_files_snapshot.items():
        if not files_for_user: continue
        for project_name, main_file, file_type in files_for_user:
            if not is_bot_running(target_user_id, project_name):
                user_folder = get_user_folder(target_user_id, project_name)
                file_path = os.path.join(user_folder, main_file)
                if os.path.exists(file_path):
                    try:
                        threading.Thread(
                            target=_start_one,
                            args=(target_user_id, project_name, main_file, file_type, user_folder, file_path)
                        ).start()
                        started_count += 1
                        time.sleep(0.5)
                    except Exception as e:
                        skipped_files += 1
                        logger.error(f"Error starting {project_name} for {target_user_id}: {e}")
                else:
                    skipped_files += 1

    reply_func(f"✅ Run All Scripts Complete!\n▶️ Started: `{started_count}`\n⚠️ Skipped: `{skipped_files}`", parse_mode='Markdown')

def _logic_user_management(message):
    if not _can(message.from_user.id, 'users'):
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    bot.reply_to(message, "👥 *User Management*\nSelect an action:", reply_markup=create_user_management_menu(), parse_mode='Markdown')

def _logic_pending_files(message):
    if not _can(message.from_user.id, 'pending'):
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    _show_pending_files(message.chat.id, message_id=None)

def _logic_view_user_files(message):
    if not _can(message.from_user.id, 'users'):
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    msg = bot.reply_to(message, "🔍 Enter the User ID to view their files:\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_view_user_files_id)

def process_view_user_files_id(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        target_user_id = int(message.text.strip())
        if target_user_id <= 0: raise ValueError("ID must be positive")
        _show_user_files_admin(message, target_user_id)
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID. Must be a number.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

def _show_user_files_admin(message_or_call, target_user_id):
    """Show files of any user to admin (send as new message)."""
    chat_id = message_or_call.chat.id if hasattr(message_or_call, 'chat') else message_or_call.message.chat.id
    files_list = user_files.get(target_user_id, [])
    if not files_list:
        bot.send_message(chat_id, f"📂 User `{target_user_id}` has no projects.", parse_mode='Markdown')
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for project_name, main_file, file_type in sorted(files_list):
        is_running = is_bot_running(target_user_id, project_name)
        status_icon = "🟢" if is_running else "🔴"
        markup.add(types.InlineKeyboardButton(f"{status_icon} {project_name}", callback_data=f'umfile_{target_user_id}_{project_name}'))
    bot.send_message(chat_id, f"📂 *Projects for User* `{target_user_id}`:\nTap to manage.", reply_markup=markup, parse_mode='Markdown')

# ============================================================
# --- Broadcast ---
# ============================================================
def process_broadcast_message(message):
    user_id = message.from_user.id
    if user_id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text and message.text.lower() == '/cancel': bot.reply_to(message, "❌ Broadcast cancelled."); return
    broadcast_content = message.text
    if not broadcast_content and not (message.photo or message.video or message.document):
        bot.reply_to(message, "⚠️ Cannot broadcast empty message. Or /cancel.")
        msg = bot.send_message(message.chat.id, "📢 Send broadcast message or /cancel.")
        bot.register_next_step_handler(msg, process_broadcast_message)
        return
    target_count = len(active_users)
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("✅ Confirm & Send", callback_data=f"confirm_broadcast_{message.message_id}"),
               types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast"))
    preview_text = broadcast_content[:1000].strip() if broadcast_content else "(Media message)"
    bot.reply_to(message, f"⚠️ *Confirm Broadcast*\n\n```\n{preview_text}\n```\nTo *{target_count}* users. Sure?",
                 reply_markup=markup, parse_mode='Markdown')

def handle_confirm_broadcast(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if user_id not in admin_ids: bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True); return
    try:
        original_message = call.message.reply_to_message
        if not original_message: raise ValueError("Could not retrieve original message.")
        broadcast_text = None; broadcast_photo_id = None; broadcast_video_id = None
        if original_message.text: broadcast_text = original_message.text
        elif original_message.photo: broadcast_photo_id = original_message.photo[-1].file_id
        elif original_message.video: broadcast_video_id = original_message.video.file_id
        else: raise ValueError("No supported content for broadcast.")
        bot.answer_callback_query(call.id, "🚀 Starting broadcast...")
        bot.edit_message_text(f"📢 Broadcasting to {len(active_users)} users...", chat_id, call.message.message_id)
        threading.Thread(target=execute_broadcast,
                         args=(broadcast_text, broadcast_photo_id, broadcast_video_id,
                               original_message.caption if (broadcast_photo_id or broadcast_video_id) else None,
                               chat_id)).start()
    except ValueError as ve:
        bot.edit_message_text(f"❌ Broadcast error: {ve}", chat_id, call.message.message_id)
    except Exception as e:
        logger.error(f"Error in handle_confirm_broadcast: {e}", exc_info=True)
        bot.edit_message_text("❌ Unexpected error during broadcast.", chat_id, call.message.message_id)

def handle_cancel_broadcast(call):
    bot.answer_callback_query(call.id, "❌ Broadcast cancelled.")
    bot.delete_message(call.message.chat.id, call.message.message_id)
    if call.message.reply_to_message:
        try: bot.delete_message(call.message.chat.id, call.message.reply_to_message.message_id)
        except Exception: pass

def execute_broadcast(broadcast_text, photo_id, video_id, caption, admin_chat_id):
    sent_count = 0; failed_count = 0; blocked_count = 0
    start_time = time.time()
    users_to_broadcast = list(active_users)
    total = len(users_to_broadcast)
    batch_size = 25; delay_batches = 1.5
    for i, uid in enumerate(users_to_broadcast):
        try:
            if broadcast_text: bot.send_message(uid, broadcast_text, parse_mode='Markdown')
            elif photo_id: bot.send_photo(uid, photo_id, caption=caption, parse_mode='Markdown' if caption else None)
            elif video_id: bot.send_video(uid, video_id, caption=caption, parse_mode='Markdown' if caption else None)
            sent_count += 1
        except telebot.apihelper.ApiTelegramException as e:
            err = str(e).lower()
            if any(s in err for s in ["bot was blocked", "user is deactivated", "chat not found"]): blocked_count += 1
            elif "flood control" in err or "too many requests" in err:
                retry_after = 5
                match = re.search(r"retry after (\d+)", err)
                if match: retry_after = int(match.group(1)) + 1
                time.sleep(retry_after)
                try:
                    if broadcast_text: bot.send_message(uid, broadcast_text, parse_mode='Markdown')
                    elif photo_id: bot.send_photo(uid, photo_id, caption=caption)
                    sent_count += 1
                except Exception: failed_count += 1
            else: failed_count += 1
        except Exception: failed_count += 1
        if (i + 1) % batch_size == 0 and i < total - 1: time.sleep(delay_batches)
        elif i % 5 == 0: time.sleep(0.2)
    duration = round(time.time() - start_time, 2)
    result = (f"📢 *Broadcast Complete!*\n\n✅ Sent: `{sent_count}`\n❌ Failed: `{failed_count}`\n"
              f"🚫 Blocked/Inactive: `{blocked_count}`\n👥 Targets: `{total}`\n⏱️ Duration: `{duration}s`")
    try: bot.send_message(admin_chat_id, result, parse_mode='Markdown')
    except Exception as e: logger.error(f"Failed to send broadcast result: {e}")

# ============================================================
# --- Command Handlers ---
# ============================================================
@bot.message_handler(commands=['start'])
def command_send_welcome(message): _logic_send_welcome(message)

@bot.message_handler(commands=['help'])
def command_help(message): _logic_help(message)

@bot.message_handler(commands=['status'])
def command_show_status(message): _logic_statistics(message)

@bot.message_handler(commands=['ping'])
def ping(message):
    start_ping_time = time.time()
    msg = bot.reply_to(message, "Pong!")
    latency = round((time.time() - start_ping_time) * 1000, 2)
    bot.edit_message_text(f"🏓 Pong! Latency: `{latency} ms`", message.chat.id, msg.message_id, parse_mode='Markdown')

def _logic_help(message):
    help_msg = (
        "       📖 Help & Guide\n"
        "──────────────────────\n"
        "🤖 *FENIX HOSTING BOT* runs your Telegram bots 24/7 — just upload and go!\n\n"
        "──────────────────────\n"
        "⚡ *Quick Commands*\n\n"
        "📤 `/uploadfile` — Upload a script\n"
        "📂 `/checkfiles` — Manage your bots\n"
        "💎 `/plans` — View & buy plans\n"
        "📦 `/manualinstall` — Install a package\n"
        "👤 `/myinfo` — Your profile & usage\n"
        "🏓 `/ping` — Check response speed\n\n"
        "──────────────────────\n"
        "📁 *Supported Formats*\n\n"
        "🐍 `.py` — Python scripts\n"
        "🟨 `.js` — Node.js scripts\n"
        "📦 `.zip` — Full projects with multiple files"
    )
    bot.reply_to(message, help_msg, parse_mode='Markdown')

def _channel_add_panel(force_channels):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for e in force_channels:
        markup.add(types.InlineKeyboardButton(f"🔴 Remove {e['title']}", callback_data=f"remove_force_join_{e['channel']}"))
    markup.add(types.InlineKeyboardButton("➕ Add Channel", callback_data="set_force_join"))
    if force_channels:
        ch_list = '\n'.join(f"  {i+1}. *{e['title']}*" for i, e in enumerate(force_channels))
        status = (
            f"🔒 *Access restricted — {len(force_channels)} channel(s) active.*\n"
            f"Users must join all channels before using this bot.\n\n"
            f"──────────────────────\n"
            f"📋 *Required Channels:*\n{ch_list}\n\n"
            f"──────────────────────\n"
            f"👇 Manage channels below:"
        )
    else:
        status = (
            "🔕 *No channels active.*\n"
            "Users can access the bot freely.\n\n"
            "──────────────────────\n"
            "👇 Add a channel to restrict access:"
        )
    return f"   📢 Force Join Channels\n──────────────────────\n{status}", markup

def _logic_channel_add(message, override_user_id=None):
    """Admin-only: manage mandatory join channels."""
    check_id = override_user_id if override_user_id is not None else message.from_user.id
    if not _can(check_id, 'channels'):
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    text, markup = _channel_add_panel(force_join_channels)
    bot.reply_to(message, text, parse_mode='Markdown', reply_markup=markup)

# ============================================================
# --- Live Logs ---
# ============================================================
import html as _html
LIVE_SESSIONS = {}          # (chat_id, message_id) -> stop Event
LIVE_REFRESH_SEC = 3
LIVE_MAX_SEC = 300

def _read_log_tail(log_path, max_chars=3300):
    try:
        size = os.path.getsize(log_path)
        if size == 0: return "(Log is empty - waiting for output...)"
        with open(log_path, 'rb') as f:
            f.seek(max(0, size - 8192))
            txt = f.read().decode('utf-8', errors='ignore')
        txt = txt[-max_chars:]
        if size > 8192 or len(txt) == max_chars:
            nl = txt.find('\n')
            txt = "...\n" + (txt[nl+1:] if nl != -1 else txt)
        return txt if txt.strip() else "(No visible content)"
    except Exception as e:
        return f"(Cannot read log: {e})"

def _live_text(owner_id, project_name, log_path, live=True):
    running = is_bot_running(owner_id, project_name)
    body = _html.escape(_read_log_tail(log_path))
    state = "🟢 Running" if running else "🔴 Stopped"
    head = f"✦ <b>𝗟𝗜𝗩𝗘  𝗟𝗢𝗚𝗦</b> ✦ ▸ <code>{_html.escape(project_name)}</code>\n{state} · {'🔄 live' if live else '⏹ paused'} · 🕒 {datetime.now().strftime('%H:%M:%S')}\n"
    return head + f"<pre>{body}</pre>"

def _live_markup(owner_id, project_name, live=True):
    m = types.InlineKeyboardMarkup(row_width=2)
    if live:
        m.add(types.InlineKeyboardButton("⏹ Stop", callback_data=f"livestop_{owner_id}_{project_name}"))
    else:
        m.add(types.InlineKeyboardButton("▶️ Resume Live", callback_data=f"live_{owner_id}_{project_name}"))
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="live_menu"))
    return m

def live_menu_callback(call):
    bot.answer_callback_query(call.id)
    _show_live_menu(call.from_user.id, call.message.chat.id, call.message.message_id)

def _live_projects_markup(user_id):
    files = sorted(user_files.get(user_id, []))
    if not files: return None
    m = types.InlineKeyboardMarkup(row_width=1)
    for project_name, _mf, _ft in files:
        icon = "🟢" if is_bot_running(user_id, project_name) else "🔴"
        m.add(types.InlineKeyboardButton(f"{icon} {project_name}", callback_data=f"live_{user_id}_{project_name}"))
    return m

def _show_live_menu(user_id, chat_id, message_id=None):
    m = _live_projects_markup(user_id)
    if not m:
        txt = "✦ <b>𝗟𝗜𝗩𝗘  𝗟𝗢𝗚𝗦</b> ✦\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n<blockquote><i>No projects yet.</i>\nUpload a file first to watch its output.</blockquote>"
        m = None
    else:
        txt = "✦ <b>𝗟𝗜𝗩𝗘  𝗟𝗢𝗚𝗦</b> ✦\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n<blockquote>Select a project to stream its output in real time.</blockquote>\n<i>🟢 running   🔴 stopped</i>"
    try:
        if message_id: bot.edit_message_text(txt, chat_id, message_id, reply_markup=m, parse_mode='HTML')
        else: bot.send_message(chat_id, txt, reply_markup=m, parse_mode='HTML')
    except Exception as e:
        if 'not modified' not in str(e): bot.send_message(chat_id, txt, reply_markup=m, parse_mode='HTML')

def _logic_live_logs(message):
    _show_live_menu(message.from_user.id, message.chat.id)

def _live_worker(chat_id, message_id, owner_id, project_name, log_path, stop_ev):
    key = (chat_id, message_id)
    last = None
    end = time.time() + LIVE_MAX_SEC
    try:
        while not stop_ev.is_set() and time.time() < end:
            txt = _live_text(owner_id, project_name, log_path, True)
            body = txt.split('\n', 2)[-1]
            if body != last:
                try:
                    bot.edit_message_text(txt, chat_id, message_id, parse_mode='HTML',
                                          reply_markup=_live_markup(owner_id, project_name, True))
                    last = body
                except Exception as e:
                    if 'not modified' not in str(e):
                        if 'Too Many Requests' in str(e): time.sleep(5)
                        elif 'message to edit not found' in str(e) or "can't be edited" in str(e): break
            stop_ev.wait(LIVE_REFRESH_SEC)
        try:
            bot.edit_message_text(_live_text(owner_id, project_name, log_path, False), chat_id, message_id,
                                  parse_mode='HTML', reply_markup=_live_markup(owner_id, project_name, False))
        except Exception: pass
    finally:
        if LIVE_SESSIONS.get(key) is stop_ev: LIVE_SESSIONS.pop(key, None)

def live_logs_callback(call):
    try:
        _, owner_str, project_name = call.data.split('_', 2)
        owner_id = int(owner_str)
    except (ValueError, IndexError):
        bot.answer_callback_query(call.id, "Invalid request.", show_alert=True); return
    if not (call.from_user.id == owner_id or call.from_user.id in admin_ids):
        bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
    if not any(f[0] == project_name for f in user_files.get(owner_id, [])):
        bot.answer_callback_query(call.id, "⚠️ Project not found.", show_alert=True); return
    log_path = os.path.join(get_user_folder(owner_id, project_name), f"{project_name}.log")
    if not os.path.exists(log_path):
        bot.answer_callback_query(call.id, "⚠️ No logs yet - start the project first.", show_alert=True); return
    bot.answer_callback_query(call.id, "📡 Live logs started")
    chat_id, msg_id = call.message.chat.id, call.message.message_id
    key = (chat_id, msg_id)
    old = LIVE_SESSIONS.get(key)
    if old: old.set()
    ev = threading.Event()
    LIVE_SESSIONS[key] = ev
    try:
        bot.edit_message_text(_live_text(owner_id, project_name, log_path, True), chat_id, msg_id,
                              parse_mode='HTML', reply_markup=_live_markup(owner_id, project_name, True))
    except Exception: pass
    threading.Thread(target=_live_worker, args=(chat_id, msg_id, owner_id, project_name, log_path, ev), daemon=True).start()

def live_stop_callback(call):
    ev = LIVE_SESSIONS.get((call.message.chat.id, call.message.message_id))
    if ev: ev.set()
    bot.answer_callback_query(call.id, "⏹ Stopped")

BUTTON_TEXT_TO_LOGIC = {
    "📢 Updates Channel": _logic_updates_channel,
    "📤 Upload File": _logic_upload_file,
    "📂 Check Files": _logic_check_files,
    "⚡ Bot Speed": _logic_bot_speed,
    "📞 Contact Owner": _logic_contact_owner,
    "📊 Statistics": _logic_statistics,
    "💳 Subscriptions": _logic_subscriptions_panel,
    "📢 Broadcast": _logic_broadcast_init,
    "🔒 Lock Bot": _logic_toggle_lock_bot,
    "🔓 Unlock Bot": _logic_toggle_lock_bot,
    "🟢 Run All Code": _logic_run_all_scripts,
    "👑 Admin Panel": _logic_admin_panel,
    "👥 User Management": _logic_user_management,
    "📋 Pending Files": _logic_pending_files,
    "📦 Manual Install": _logic_manual_install,
    "🛠️ Manual Install": _logic_manual_install,
    "💎 View Plans": _logic_view_plans,
    "📡 Live Logs": _logic_live_logs,
    "👤 My Info": _logic_my_info,
    "📢 Channel Add": _logic_channel_add,
}

def setup_command_menu():
    """Register the bot's slash-command menu with Telegram (extended menu for admins)."""
    user_commands = [
        types.BotCommand('start',          '🏠 Start / show main menu'),
        types.BotCommand('help',           '❓ Show help & main menu'),
        types.BotCommand('uploadfile',     '📤 Upload a .py / .js / .zip file'),
        types.BotCommand('checkfiles',     '📂 List & manage your files'),
        types.BotCommand('plans',          '💎 View & buy plans'),
        types.BotCommand('statistics',     '📊 View bot statistics'),
        types.BotCommand('botspeed',       '⚡ Test bot response speed'),
        types.BotCommand('updateschannel', '📢 Join the updates channel'),
        types.BotCommand('contactowner',   '📞 Contact the bot owner'),
        types.BotCommand('ping',           '🏓 Ping the bot'),
        types.BotCommand('manualinstall',  '📦 Install a Python / Node.js module'),
        types.BotCommand('myinfo',         '👤 View your profile, status & file usage'),
        types.BotCommand('livelogs',       '📡 Watch live logs of your projects'),
        types.BotCommand('leaderboard',    '🏆 View the leaderboard'),
        types.BotCommand('refer',          '🔗 Refer & earn points'),
        types.BotCommand('redeem',         '🎟 Redeem a code'),
    ]
    admin_extra_commands = [
        types.BotCommand('subscriptions',   '💳 Manage user subscriptions'),
        types.BotCommand('broadcast',       '📢 Broadcast a message to all users'),
        types.BotCommand('lockbot',         '🔒 Toggle bot lock on/off'),
        types.BotCommand('runallcode',      '🟢 Start all uploaded scripts'),
        types.BotCommand('adminpanel',      '👑 Open the admin panel'),
        types.BotCommand('usermanagement',  '👥 Ban / unban / inspect users'),
        types.BotCommand('channeladd',      '📢 Set / remove mandatory join channel'),
    ]
    try:
        bot.set_my_commands(user_commands, scope=types.BotCommandScopeDefault())
        logger.info("✅ Command menu set for all users.")
    except Exception as e:
        logger.error(f"❌ Failed to set default command menu: {e}")
    for admin_id in admin_ids:
        try:
            bot.set_my_commands(user_commands + admin_extra_commands,
                                scope=types.BotCommandScopeChat(chat_id=admin_id))
            logger.info(f"✅ Extended command menu set for admin {admin_id}.")
        except Exception as e:
            logger.error(f"❌ Failed to set admin command menu for {admin_id}: {e}")

# ============================================================
# --- Premium (custom) emoji + bot name ---
# ============================================================
BOT_NAME_DEFAULT = "FENIX HOSTING BOT"
PE_SLOTS = [
    ('logo',     '✦',  'Title / logo'),
    ('account',  '❖',  'ACCOUNT heading'),
    ('id',       '🆔', 'ID line'),
    ('user',     '👤', 'Username line'),
    ('rank',     '👑', 'Membership line'),
    ('projects', '📁', 'Projects line'),
    ('services', '✨', 'SERVICES heading'),
    ('bullet',   '◇',  'Service bullets'),
    ('footer',   '👇', 'Footer line'),
]
_PE_FALLBACK = {k: f for k, f, _ in PE_SLOTS}

def _pe_map():
    try: return json.loads(get_setting('PREMIUM_EMOJI', '') or '{}')
    except Exception: return {}

def _has_premium_emoji():
    return bool(_pe_map())

def pe(slot, premium=True):
    """Return the slot's emoji; as a Telegram premium (custom) emoji when one is configured."""
    fb = _PE_FALLBACK.get(slot, '')
    cid = _pe_map().get(slot) if premium else None
    return f'<tg-emoji emoji-id="{cid}">{fb}</tg-emoji>' if cid else fb

def _pe_markup():
    m = types.InlineKeyboardMarkup(row_width=1)
    mp = _pe_map()
    for slot, fb, label in PE_SLOTS:
        m.add(types.InlineKeyboardButton(f"{fb} {label} — {'💎 set' if slot in mp else 'default'}", callback_data=f"bc_pe_{slot}"))
    m.row(types.InlineKeyboardButton("🔍 Preview", callback_data="bc_pe_preview"), types.InlineKeyboardButton("♻️ Reset all", callback_data="bc_pe_reset"))
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="bc_home"))
    return m

def _pe_text():
    return ("💎 <b>Premium Emoji</b>\n\nPick a spot, then send a message that contains a <b>Telegram Premium emoji</b> "
            "and the bot will use it there. Spots without one keep the normal emoji.\n\n"
            "<i>Note: Telegram decides whether a bot may show premium emoji. If it refuses, the bot automatically falls back to the normal emoji, so nothing breaks.</i>")

def bc_process_pe(message, slot):
    if message.text and message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    if message.text and message.text.strip() in ('-', 'reset'):
        mp = _pe_map(); mp.pop(slot, None); set_setting('PREMIUM_EMOJI', json.dumps(mp)); bot.reply_to(message, "♻️ Reset to the normal emoji."); return
    ents = [e for e in (message.entities or []) if getattr(e, 'type', '') == 'custom_emoji']
    if not ents:
        msg = bot.reply_to(message, "⚠️ I couldn't find a premium emoji in that message. Send one (needs Telegram Premium), `-` to reset, or /cancel.", parse_mode='Markdown')
        bot.register_next_step_handler(msg, bc_process_pe, slot); return
    mp = _pe_map(); mp[slot] = ents[0].custom_emoji_id
    set_setting('PREMIUM_EMOJI', json.dumps(mp))
    bot.reply_to(message, "✅ Premium emoji saved. Use 🔍 Preview to check it.")

def process_bot_name(message):
    if not message.text or message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    n = message.text.strip().upper()
    if len(n) > 32:
        bot.reply_to(message, "❌ Max 32 characters."); return
    set_setting('BOT_NAME', n)
    bot.reply_to(message, f"✅ Bot name set to <b>{n}</b>. Shown on the welcome message.", parse_mode='HTML')

# ============================================================
# --- Button Customizer (rename / emoji / photo / order / custom buttons) ---
# ============================================================
import json as _json2
import html as _hh3

BTN_DEFAULTS = {   # id: (emoji, name, full-width row?, access)
    'updates':  ('📢', 'Updates Channel', True,  'all'),
    'upload':   ('📤', 'Upload File',     False, 'all'),
    'check':    ('📂', 'Check Files',     False, 'all'),
    'speed':    ('⚡', 'Bot Speed',       False, 'all'),
    'stats':    ('📊', 'Statistics',      False, 'all'),
    'manual':   ('📦', 'Manual Install',  False, 'all'),
    'plans':    ('💎', 'View Plans',      False, 'all'),
    'livelogs': ('📡', 'Live Logs',       False, 'all'),
    'admin':    ('👑', 'Admin Panel',     False, 'admin'),
    'myinfo':   ('👤', 'My Info',         False, 'all'),
    'leaderboard': ('🏆', 'Leaderboard', False, 'all'),
    'refer':    ('🔗', 'Refer & Earn',    False, 'all'),
    'contact':  ('📞', 'Contact Owner',   False, 'all'),
}
BTN_DEFAULT_ORDER = list(BTN_DEFAULTS.keys())
BTN_NO_JOIN_CHECK = {'updates', 'contact'}
_BTN_CFG_CACHE = {}

def _hb(x):
    return _hh3.escape(str(x if x is not None else ''))

def _btn_cfg():
    if 'v' not in _BTN_CFG_CACHE:
        try: cfg = _json2.loads(get_setting('BTN_CFG', '') or '{}')
        except Exception: cfg = {}
        cfg.setdefault('btn', {}); cfg.setdefault('custom', {}); cfg.setdefault('order', [])
        cfg.setdefault('welcome_photo', '')
        _BTN_CFG_CACHE['v'] = cfg
    return _BTN_CFG_CACHE['v']

def _btn_save():
    set_setting('BTN_CFG', _json2.dumps(_btn_cfg(), ensure_ascii=False))

def _btn_order():
    cfg = _btn_cfg()
    ids = [i for i in cfg['order'] if i in BTN_DEFAULTS or i in cfg['custom']]
    for i in BTN_DEFAULT_ORDER + list(cfg['custom'].keys()):
        if i not in ids: ids.append(i)
    return ids

def btn_get(bid):
    cfg = _btn_cfg()
    if bid in BTN_DEFAULTS:
        e, n, wide, acc = BTN_DEFAULTS[bid]
        d = {'emoji': e, 'name': n, 'wide': wide, 'access': acc, 'photo': '', 'caption': '', 'hidden': False, 'kind': 'builtin', 'color': ''}
        d.update(cfg['btn'].get(bid, {}))
        return d
    c = cfg['custom'].get(bid)
    if not c: return None
    d = {'emoji': '🔘', 'name': bid, 'wide': False, 'access': 'all', 'photo': '', 'caption': '', 'hidden': False, 'color': '',
         'kind': 'custom', 'type': 'text', 'text': '', 'url': ''}
    d.update(c)
    return d

def btn_label(bid):
    d = btn_get(bid)
    return f"{d['emoji']} {d['name']}".strip() if d else ''

def _btn_default_label(bid):
    e, n, _, _ = BTN_DEFAULTS[bid]
    return f"{e} {n}"

def _btn_update(bid, **kw):
    cfg = _btn_cfg()
    if bid in BTN_DEFAULTS:
        cfg['btn'].setdefault(bid, {}).update(kw)
    else:
        cfg['custom'].setdefault(bid, {}).update(kw)
    _btn_save()

def _btn_label_taken(label, except_id=None):
    for bid in _btn_order():
        if bid != except_id and btn_label(bid).strip().lower() == label.strip().lower(): return True
    for bid in BTN_DEFAULTS:
        if bid != except_id and _btn_default_label(bid).lower() == label.strip().lower() and bid not in _btn_cfg()['btn']:
            return True
    return False

def _btn_resolve(text):
    if not text: return None
    for bid in _btn_order():
        if btn_label(bid) == text: return ('b' if bid in BTN_DEFAULTS else 'c', bid)
    for bid in BTN_DEFAULTS:                       # stale keyboards still work after a rename
        if _btn_default_label(bid) == text: return ('b', bid)
    if text in BUTTON_TEXT_TO_LOGIC: return ('l', text)
    return None

def _btn_visible(bid, user_id):
    d = btn_get(bid)
    if not d or d['hidden']: return False
    if d['access'] == 'admin' and user_id not in admin_ids: return False
    return True

BTN_DEFAULT_COLORS = {'updates': 'primary', 'upload': 'success', 'check': 'primary', 'speed': 'success', 'stats': 'primary', 'manual': 'primary',
                      'plans': 'success', 'livelogs': 'primary', 'admin': 'danger', 'myinfo': 'primary', 'leaderboard': 'success',
                      'refer': 'success', 'contact': 'primary'}
_COLOR_DOT = {'primary': '🔵', 'success': '🟢', 'danger': '🔴', 'none': '⚪'}

def _btn_effective_color(bid):
    """Color the main-menu button really shows: its own setting, else the built-in default, else the group color."""
    d = btn_get(bid) or {}
    c = d.get('color') or BTN_DEFAULT_COLORS.get(bid, '')
    if not c:
        c = _auto_style(btn_label(bid)) or 'none'
    return c

def _btn_build_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    rows, buf = [], []
    for bid in _btn_order():
        if not _btn_visible(bid, user_id): continue
        label = btn_label(bid)
        if btn_get(bid)['wide']:
            if buf: rows.append(buf); buf = []
            rows.append([label])
        else:
            buf.append(label)
            if len(buf) == 2: rows.append(buf); buf = []
    if buf: rows.append(buf)
    colors = {btn_label(b): _btn_effective_color(b) for b in _btn_order()}
    def _kb(t):
        kb = types.KeyboardButton(t)
        c = colors.get(t, '')
        if c: kb.style = c
        return kb
    for r in rows: markup.add(*[_kb(t) for t in r])
    return markup

def _btn_count_click(bid):
    try: _db_exec("INSERT INTO button_clicks (id, n) VALUES (?, 1) ON CONFLICT(id) DO UPDATE SET n = n + 1", (bid,))
    except Exception: pass

def _btn_send_banner(chat_id, d):
    """Send the button's photo (and caption) if the admin set one."""
    if d.get('photo'):
        try:
            bot.send_photo(chat_id, d['photo'], caption=(d.get('caption') or None))
            return True
        except Exception as e:
            logger.warning(f"Button photo failed: {e}")
    elif d.get('caption') and d['kind'] == 'builtin':
        try: bot.send_message(chat_id, d['caption']); return True
        except Exception: pass
    return False

def _btn_run_custom(message, d):
    chat_id = message.chat.id
    shown = _btn_send_banner(chat_id, d) if d.get('photo') else False
    text = d.get('text') or ''
    markup = None
    if d.get('type') == 'link' and d.get('url'):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"{d['emoji']} {d['name']}".strip(), url=d['url']))
        text = text or "👇 Tap the button below"
    if not text and not shown and not markup:
        text = "ℹ️ This button has no content yet."
    if text or markup:
        bot.send_message(chat_id, text or "👇", reply_markup=markup)

@bot.message_handler(func=lambda message: _btn_resolve(message.text) is not None)
def handle_button_text(message):
    uid = message.from_user.id
    touch_user(message.from_user)
    if is_user_banned(uid):
        bot.reply_to(message, M('banned'))
        return
    kind, key = _btn_resolve(message.text)
    if kind == 'l':
        if message.text not in {"📢 Updates Channel", "📞 Contact Owner", "📢 Channel Add"} and not check_force_join(message):
            return
        BUTTON_TEXT_TO_LOGIC[key](message); return
    d = btn_get(key)
    if key not in BTN_NO_JOIN_CHECK and not check_force_join(message):
        return
    if d['hidden'] and uid not in admin_ids:
        bot.reply_to(message, "ℹ️ This option is currently unavailable."); return
    if d['access'] == 'admin' and uid not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required."); return
    if d['access'] == 'premium' and uid not in admin_ids and not has_active_sub(uid):
        mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("💎 View Plans", callback_data="view_plans_cb"))
        bot.reply_to(message, f"🔒 <b>{_hb(d['name'])}</b> is for premium members only.", parse_mode='HTML', reply_markup=mk); return
    _btn_count_click(key)
    if kind == 'c':
        _btn_run_custom(message, d); return
    _btn_send_banner(message.chat.id, d)
    BTN_LOGIC[key](message)

# ---------------- admin UI ----------------
def _bc_list_markup():
    m = types.InlineKeyboardMarkup(row_width=1)
    for bid in _btn_order():
        d = btn_get(bid)
        flags = ("🖼" if d['photo'] else "") + ("🙈" if d['hidden'] else "") + ("🔒" if d['access'] != 'all' else "") + ("🔗" if d['kind'] == 'custom' and d.get('type') == 'link' else "")
        _c = _btn_effective_color(bid)
        _b = types.InlineKeyboardButton(f"{(_COLOR_DOT.get(_c, '⚪') + ' ') if _style_enabled() else ''}{btn_label(bid)} {flags}".strip(), callback_data=f"bc_b_{bid}")
        _b.style = _c
        m.add(_b)
    m.row(types.InlineKeyboardButton("➕ Add Custom Button", callback_data="bc_addc"),
          types.InlineKeyboardButton("🖼 Welcome Photo", callback_data="bc_wp"))
    m.row(types.InlineKeyboardButton("🔄 Apply to my keyboard", callback_data="bc_apply"),
          types.InlineKeyboardButton("📣 Push to all users", callback_data="bc_push"))
    m.row(types.InlineKeyboardButton("📊 Click Stats", callback_data="bc_stats"),
          types.InlineKeyboardButton("📤 Export", callback_data="bc_export"))
    m.row(types.InlineKeyboardButton("📥 Import", callback_data="bc_import"),
          types.InlineKeyboardButton("♻️ Reset All", callback_data="bc_resetall"))
    m.row(types.InlineKeyboardButton("🎨 Colors: " + ("ON ✅" if _style_enabled() else "OFF ❌"), callback_data="bk_t_bc"),
          types.InlineKeyboardButton("⚙️ Color Manager", callback_data="bk_home"))
    m.row(types.InlineKeyboardButton("💎 Premium Emoji", callback_data="bc_pe"),
          types.InlineKeyboardButton("✏️ Bot Name", callback_data="bc_name"))
    m.add(types.InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel"))
    return m

def _bc_list_text():
    return ("🎛️ <b>Customize Buttons</b>\n\nTap a button to rename it, change its emoji, set a photo, hide it, "
            "reorder it and more.\n🖼 photo • 🙈 hidden • 🔒 restricted • 🔗 link\n\n"
            f"Buttons: <b>{len(_btn_order())}</b> ({len(_btn_cfg()['custom'])} custom)")

def _bc_detail(bid):
    d = btn_get(bid)
    order = _btn_order()
    clicks = _db_q("SELECT n FROM button_clicks WHERE id=?", (bid,), one=True)
    acc = {'all': 'Everyone', 'premium': 'Premium only 💎', 'admin': 'Admins only 👑'}[d['access']]
    lines = [f"🎛️ <b>{_hb(btn_label(bid))}</b>", "",
             f"✏️ Name: <code>{_hb(d['name'])}</code>", f"😀 Emoji: {_hb(d['emoji']) or '—'}",
             f"🖼 Photo: {'✅ set' if d['photo'] else '— none'}", f"💬 Caption: {_hb(d['caption'])[:80] or '—'}",
             f"👁 Visible: {'No 🙈' if d['hidden'] else 'Yes'}", f"↔️ Width: {'Full row' if d['wide'] else 'Half row'}",
             f"🔐 Access: {acc}", f"📍 Position: {order.index(bid) + 1}/{len(order)}", f"👆 Clicks: {clicks[0] if clicks else 0}"]
    if d['kind'] == 'custom':
        lines += [f"🧩 Type: {'🔗 Link' if d.get('type') == 'link' else '💬 Text'}", f"📝 Reply text: {_hb(d.get('text'))[:80] or '—'}", f"🌐 URL: {_hb(d.get('url')) or '—'}"]
    m = types.InlineKeyboardMarkup(row_width=2)
    m.row(types.InlineKeyboardButton("✏️ Rename", callback_data=f"bc_a_name_{bid}"), types.InlineKeyboardButton("😀 Emoji", callback_data=f"bc_a_emoji_{bid}"))
    m.row(types.InlineKeyboardButton("🖼 Set Photo", callback_data=f"bc_a_photo_{bid}"), types.InlineKeyboardButton("🗑 Remove Photo", callback_data=f"bc_a_nophoto_{bid}"))
    m.row(types.InlineKeyboardButton("💬 Caption", callback_data=f"bc_a_cap_{bid}"),
          types.InlineKeyboardButton("👁 Show" if d['hidden'] else "🙈 Hide", callback_data=f"bc_a_hide_{bid}"))
    m.row(types.InlineKeyboardButton("↔️ Width", callback_data=f"bc_a_wide_{bid}"), types.InlineKeyboardButton("🔐 Access", callback_data=f"bc_a_acc_{bid}"))
    _c = _btn_effective_color(bid); _own = d.get('color') or ''
    _cb = types.InlineKeyboardButton("🎨 Color: " + {'primary': '🔵 Blue', 'success': '🟢 Green', 'danger': '🔴 Red', 'none': '⚪ None'}.get(_c, _c) + ("" if _own else "  (auto)"), callback_data=f"bc_a_color_{bid}")
    _cb.style = _c
    m.add(_cb)
    m.row(types.InlineKeyboardButton("⬆️ Up", callback_data=f"bc_a_up_{bid}"), types.InlineKeyboardButton("⬇️ Down", callback_data=f"bc_a_down_{bid}"))
    if d['kind'] == 'custom':
        m.row(types.InlineKeyboardButton("📝 Reply Text", callback_data=f"bc_a_text_{bid}"), types.InlineKeyboardButton("🔗 Link URL", callback_data=f"bc_a_url_{bid}"))
        m.add(types.InlineKeyboardButton("🗑 Delete Button", callback_data=f"bc_a_del_{bid}"))
    else:
        m.add(types.InlineKeyboardButton("♻️ Reset This Button", callback_data=f"bc_a_reset_{bid}"))
    m.row(types.InlineKeyboardButton("🔄 Refresh my keyboard", callback_data="bc_apply"), types.InlineKeyboardButton("🔙 List", callback_data="bc_home"))
    return "\n".join(lines), m

def _bc_show_detail(chat_id, bid, message_id=None):
    txt, mk = _bc_detail(bid)
    _send_or_edit(chat_id, txt, mk, message_id)

def _bc_applied(message, bid=None):
    """After a text/photo change: refresh admin keyboard and reopen the detail screen."""
    bot.send_message(message.chat.id, "✅ Saved.", reply_markup=_btn_build_keyboard(message.from_user.id))
    if bid: _bc_show_detail(message.chat.id, bid)

def _bc_cancelled(message):
    return (not message.text) or message.text.strip().lower() == '/cancel'

def bc_process_name(message, bid):
    if _bc_cancelled(message): bot.reply_to(message, "❌ Cancelled."); return
    name = message.text.strip()
    if not name or len(name) > 24:
        bot.reply_to(message, "❌ Name must be 1-24 characters."); return
    d = btn_get(bid); new_label = f"{d['emoji']} {name}".strip()
    if _btn_label_taken(new_label, bid):
        bot.reply_to(message, "❌ Another button already has that label."); return
    _btn_update(bid, name=name); _bc_applied(message, bid)

def bc_process_emoji(message, bid):
    if _bc_cancelled(message): bot.reply_to(message, "❌ Cancelled."); return
    emoji = message.text.strip()
    if emoji in ('-', 'none'): emoji = ''
    if len(emoji) > 8:
        bot.reply_to(message, "❌ Send just one emoji (or `-` for none).", parse_mode='Markdown'); return
    d = btn_get(bid); new_label = f"{emoji} {d['name']}".strip()
    if _btn_label_taken(new_label, bid):
        bot.reply_to(message, "❌ Another button already has that label."); return
    _btn_update(bid, emoji=emoji); _bc_applied(message, bid)

def bc_process_photo(message, bid):
    if message.text and message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    if not message.photo:
        msg = bot.reply_to(message, "⚠️ Please send a *photo* (not a file), or /cancel.", parse_mode='Markdown')
        bot.register_next_step_handler(msg, bc_process_photo, bid); return
    _btn_update(bid, photo=message.photo[-1].file_id); _bc_applied(message, bid)

def bc_process_welcome_photo(message):
    if message.text and message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    if message.text and message.text.strip() in ('-', 'remove'):
        _btn_cfg()['welcome_photo'] = ''; _btn_save(); bot.reply_to(message, "✅ Welcome photo removed."); return
    if not message.photo:
        msg = bot.reply_to(message, "⚠️ Send a *photo*, `-` to remove, or /cancel.", parse_mode='Markdown')
        bot.register_next_step_handler(msg, bc_process_welcome_photo); return
    _btn_cfg()['welcome_photo'] = message.photo[-1].file_id; _btn_save()
    bot.reply_to(message, "✅ Welcome photo saved. It shows on /start.")

def bc_process_caption(message, bid):
    if _bc_cancelled(message): bot.reply_to(message, "❌ Cancelled."); return
    cap = message.text.strip()
    if cap in ('-', 'none', 'clear'): cap = ''
    if len(cap) > 900:
        bot.reply_to(message, "❌ Caption is too long (max 900 characters)."); return
    _btn_update(bid, caption=cap); _bc_applied(message, bid)

def bc_process_text(message, bid):
    if _bc_cancelled(message): bot.reply_to(message, "❌ Cancelled."); return
    t = message.text.strip()
    if t in ('-', 'none', 'clear'): t = ''
    if len(t) > 3500:
        bot.reply_to(message, "❌ Too long (max 3500 characters)."); return
    _btn_update(bid, text=t, type=('link' if btn_get(bid).get('url') else 'text')); _bc_applied(message, bid)

def bc_process_url(message, bid):
    if _bc_cancelled(message): bot.reply_to(message, "❌ Cancelled."); return
    u = message.text.strip()
    if u in ('-', 'none', 'clear'):
        _btn_update(bid, url='', type='text'); _bc_applied(message, bid); return
    if u.startswith('@'): u = f"https://t.me/{u[1:]}"
    if not u.lower().startswith(('http://', 'https://', 'tg://')):
        bot.reply_to(message, "❌ Send a full link starting with https:// (or @username)."); return
    _btn_update(bid, url=u, type='link'); _bc_applied(message, bid)

def bc_process_add_custom(message):
    if _bc_cancelled(message): bot.reply_to(message, "❌ Cancelled."); return
    parts = [p.strip() for p in message.text.split('|')]
    if len(parts) == 1: emoji, name = '🔘', parts[0]
    else: emoji, name = parts[0], parts[1]
    if not name or len(name) > 24 or len(emoji) > 8:
        bot.reply_to(message, "❌ Use `EMOJI | NAME` (name up to 24 characters).", parse_mode='Markdown'); return
    label = f"{emoji} {name}".strip()
    if _btn_label_taken(label):
        bot.reply_to(message, "❌ A button with that label already exists."); return
    cfg = _btn_cfg(); n = 1
    while f"c{n}" in cfg['custom']: n += 1
    cid = f"c{n}"
    cfg['custom'][cid] = {'emoji': emoji, 'name': name, 'type': 'text', 'text': '', 'url': ''}
    cfg['order'] = _btn_order() + [cid] if cid not in _btn_order() else _btn_order()
    _btn_save()
    bot.send_message(message.chat.id, f"✅ Custom button <b>{_hb(label)}</b> created.\nNow set its reply text, link or photo:",
                     parse_mode='HTML', reply_markup=_btn_build_keyboard(message.from_user.id))
    _bc_show_detail(message.chat.id, cid)

def bc_process_import(message):
    if message.text and message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    if not message.document:
        msg = bot.reply_to(message, "⚠️ Send the exported *.json* file, or /cancel.", parse_mode='Markdown')
        bot.register_next_step_handler(msg, bc_process_import); return
    try:
        raw = bot.download_file(bot.get_file(message.document.file_id).file_path)
        cfg = _json2.loads(raw.decode('utf-8'))
        if not isinstance(cfg, dict): raise ValueError
        cfg.setdefault('btn', {}); cfg.setdefault('custom', {}); cfg.setdefault('order', []); cfg.setdefault('welcome_photo', '')
        if not all(isinstance(cfg[k], t) for k, t in (('btn', dict), ('custom', dict), ('order', list))): raise ValueError
        _BTN_CFG_CACHE['v'] = cfg; _btn_save()
    except Exception:
        bot.reply_to(message, "❌ That file isn't a valid button config."); return
    bot.send_message(message.chat.id, "✅ Button config imported.", reply_markup=_btn_build_keyboard(message.from_user.id))

def _bc_push_all(chat_id):
    ids = [u for u in active_users if u not in banned_users]
    def work():
        ok = 0
        for u in ids:
            try:
                bot.send_message(u, "🔄 <b>Menu updated!</b>", parse_mode='HTML', reply_markup=_btn_build_keyboard(u), disable_notification=True)
                ok += 1
            except Exception: pass
            time.sleep(0.05)
        try: bot.send_message(chat_id, f"✅ New keyboard pushed to <b>{ok}</b> of {len(ids)} users.", parse_mode='HTML')
        except Exception: pass
    threading.Thread(target=work, daemon=True).start()

def button_cfg_callback(call):
    data = call.data; uid = call.from_user.id; chat_id = call.message.chat.id; mid = call.message.message_id
    try:
        if data == 'bc_home':
            bot.answer_callback_query(call.id); _send_or_edit(chat_id, _bc_list_text(), _bc_list_markup(), mid); return
        if data.startswith('bc_b_'):
            bid = data[5:]
            if not btn_get(bid): bot.answer_callback_query(call.id, "Button not found.", show_alert=True); return
            bot.answer_callback_query(call.id); _bc_show_detail(chat_id, bid, mid); return
        if data == 'bc_pe':
            bot.answer_callback_query(call.id); _send_or_edit(chat_id, _pe_text(), _pe_markup(), mid); return
        if data == 'bc_pe_reset':
            bot.answer_callback_query(call.id, "Reset"); set_setting('PREMIUM_EMOJI', ''); _send_or_edit(chat_id, _pe_text(), _pe_markup(), mid); return
        if data == 'bc_pe_preview':
            bot.answer_callback_query(call.id)
            txt = "\n".join(f"{pe(sl)} {_hb(lb)}" for sl, _f, lb in PE_SLOTS)
            try: bot.send_message(chat_id, "🔍 <b>Preview</b>\n\n" + txt, parse_mode='HTML')
            except Exception as e: bot.send_message(chat_id, f"⚠️ Telegram refused the premium emoji ({_hb(e)}). Normal emoji will be used instead.", parse_mode='HTML')
            return
        if data.startswith('bc_pe_'):
            slot = data[6:]
            if slot in _PE_FALLBACK:
                bot.answer_callback_query(call.id)
                _ask(chat_id, f"💎 Send a message containing the *premium emoji* for: {dict((k, l) for k, _f, l in PE_SLOTS)[slot]}\n(`-` to reset this one)", bc_process_pe, slot); return
        if data == 'bc_name':
            bot.answer_callback_query(call.id)
            _ask(chat_id, f"✏️ Send the new *bot name* (max 32 chars).\nCurrent: `{get_setting('BOT_NAME', BOT_NAME_DEFAULT)}`", process_bot_name); return
        if data == 'bc_apply':
            bot.answer_callback_query(call.id, "Keyboard refreshed")
            bot.send_message(chat_id, "🔄 Keyboard refreshed.", reply_markup=_btn_build_keyboard(uid)); return
        if data == 'bc_push':
            bot.answer_callback_query(call.id)
            m = types.InlineKeyboardMarkup(); m.row(types.InlineKeyboardButton("✅ Yes, push", callback_data="bc_push_yes"), types.InlineKeyboardButton("❌ Cancel", callback_data="bc_home"))
            bot.send_message(chat_id, f"📣 Send the new keyboard to <b>{len(active_users)}</b> users now?", parse_mode='HTML', reply_markup=m); return
        if data == 'bc_push_yes':
            bot.answer_callback_query(call.id, "Sending..."); _bc_push_all(chat_id); return
        if data == 'bc_stats':
            bot.answer_callback_query(call.id)
            rows = dict(_db_q("SELECT id, n FROM button_clicks"))
            lines = ["📊 <b>Button clicks</b>\n"]
            for bid in sorted(_btn_order(), key=lambda b: rows.get(b, 0), reverse=True):
                lines.append(f"{_hb(btn_label(bid))}: <b>{rows.get(bid, 0)}</b>")
            bot.send_message(chat_id, "\n".join(lines), parse_mode='HTML'); return
        if data == 'bc_export':
            bot.answer_callback_query(call.id)
            path = os.path.join(tempfile.gettempdir(), f"buttons_{int(time.time())}.json")
            with open(path, 'w', encoding='utf-8') as f: _json2.dump(_btn_cfg(), f, ensure_ascii=False, indent=1)
            with open(path, 'rb') as f: bot.send_document(chat_id, f, caption="📤 Button config (re-import any time)")
            os.remove(path); return
        if data == 'bc_import':
            bot.answer_callback_query(call.id)
            _ask(chat_id, "📥 Send an exported button config (*.json* file):", bc_process_import); return
        if data == 'bc_resetall':
            bot.answer_callback_query(call.id)
            m = types.InlineKeyboardMarkup(); m.row(types.InlineKeyboardButton("✅ Yes, reset all", callback_data="bc_resetall_yes"), types.InlineKeyboardButton("❌ Cancel", callback_data="bc_home"))
            bot.send_message(chat_id, "⚠️ Reset <b>all</b> button names, emojis, photos, order and delete custom buttons?", parse_mode='HTML', reply_markup=m); return
        if data == 'bc_resetall_yes':
            bot.answer_callback_query(call.id)
            _BTN_CFG_CACHE.pop('v', None); set_setting('BTN_CFG', '')
            bot.send_message(chat_id, "♻️ All buttons were reset to default.", reply_markup=_btn_build_keyboard(uid)); return
        if data == 'bc_wp':
            bot.answer_callback_query(call.id)
            _ask(chat_id, "🖼 Send the *photo* to show on /start (send `-` to remove it):", bc_process_welcome_photo); return
        if data == 'bc_addc':
            bot.answer_callback_query(call.id)
            _ask(chat_id, "➕ Send: `EMOJI | NAME`\nExample: `🎁 | Free Gifts`", bc_process_add_custom); return
        if data.startswith('bc_a_'):
            _, _, action, bid = data.split('_', 3)
            d = btn_get(bid)
            if not d: bot.answer_callback_query(call.id, "Button not found.", show_alert=True); return
            if action == 'name': bot.answer_callback_query(call.id); _ask(chat_id, f"✏️ Send the new *name* (max 24 chars).\nCurrent: `{d['name']}`", bc_process_name, bid)
            elif action == 'emoji': bot.answer_callback_query(call.id); _ask(chat_id, f"😀 Send the new *emoji* (or `-` for none).\nCurrent: {d['emoji'] or '—'}", bc_process_emoji, bid)
            elif action == 'photo': bot.answer_callback_query(call.id); _ask(chat_id, "🖼 Send the *photo* to show when this button is pressed:", bc_process_photo, bid)
            elif action == 'cap': bot.answer_callback_query(call.id); _ask(chat_id, "💬 Send the *caption* shown with the photo (or `-` to clear):", bc_process_caption, bid)
            elif action == 'text': bot.answer_callback_query(call.id); _ask(chat_id, "📝 Send the *reply text* this button should show (or `-` to clear):", bc_process_text, bid)
            elif action == 'url': bot.answer_callback_query(call.id); _ask(chat_id, "🔗 Send the *link* (https://... or @username). Send `-` to remove:", bc_process_url, bid)
            else:
                if action == 'nophoto': _btn_update(bid, photo=''); bot.answer_callback_query(call.id, "Photo removed")
                elif action == 'hide': _btn_update(bid, hidden=not d['hidden']); bot.answer_callback_query(call.id, "Updated")
                elif action == 'color':
                    cyc = ['', 'primary', 'success', 'danger', 'none']; cur = d.get('color') or ''
                    _btn_update(bid, color=cyc[(cyc.index(cur) + 1) % len(cyc)] if cur in cyc else ''); bot.answer_callback_query(call.id, "Color changed - tap 🔄 Apply to my keyboard")
                elif action == 'wide': _btn_update(bid, wide=not d['wide']); bot.answer_callback_query(call.id, "Updated")
                elif action == 'acc':
                    nxt = {'all': 'premium', 'premium': 'admin', 'admin': 'all'}[d['access']]
                    _btn_update(bid, access=nxt); bot.answer_callback_query(call.id, f"Access: {nxt}")
                elif action in ('up', 'down'):
                    order = _btn_order(); i = order.index(bid); j = i - 1 if action == 'up' else i + 1
                    if 0 <= j < len(order):
                        order[i], order[j] = order[j], order[i]; _btn_cfg()['order'] = order; _btn_save()
                    bot.answer_callback_query(call.id, "Moved")
                elif action == 'reset' and bid in BTN_DEFAULTS:
                    _btn_cfg()['btn'].pop(bid, None); _btn_save(); bot.answer_callback_query(call.id, "Reset")
                elif action == 'del' and bid not in BTN_DEFAULTS:
                    _btn_cfg()['custom'].pop(bid, None); _btn_cfg()['order'] = [i for i in _btn_cfg()['order'] if i != bid]; _btn_save()
                    bot.answer_callback_query(call.id, "Deleted"); _send_or_edit(chat_id, _bc_list_text(), _bc_list_markup(), mid); return
                _bc_show_detail(chat_id, bid, mid)
            return
    except Exception as e:
        logger.error(f"Button customizer error ({data}): {e}", exc_info=True)
        try: bot.send_message(chat_id, f"❌ Error: {_hb(e)}", parse_mode='HTML')
        except Exception: pass

# ============================================================
# --- LEADERBOARD + REFER & EARN ---
# ============================================================
import html as _hlb

LB_BOARDS = {   # key: (emoji, title, unit)
    'points': ('⭐', 'Top Points',      'pts'),
    'refs':   ('👥', 'Top Referrals',   'invites'),
    'money':  ('💰', 'Top Money Spent', ''),
    'hosts':  ('🤖', 'Top Bot Hosts',   'bots'),
}
LB_DEF = {'LB_ENABLED': '1', 'LB_BOARDS': 'points,refs,money,hosts', 'LB_DEFAULT': 'points', 'LB_SIZE': '10',
          'LB_PERIOD': 'all', 'LB_NAMES': 'name', 'LB_HIDE_ADMINS': '1', 'LB_TITLE': 'LEADERBOARD',
          'POINTS_ON': '1', 'REF_ON': '1', 'REF_POINTS': '10', 'REF_NEW_BONUS': '0', 'REF_MAX': '0', 'REF_REQ_UPLOAD': '0',
          'REF_MS_N': '0', 'REF_MS_PTS': '0', 'REF_NOTIFY': '1',
          'SPEND_ON': '1', 'BUY_POINTS': '5', 'SPEND_UNIT': '100', 'SPEND_MIN': '0',
          'DAILY_ON': '0', 'DAILY_PTS': '5', 'REDEEM_ON': '0', 'REDEEM_COST': '50', 'REDEEM_MAX': '30',
          'PB_ON': '1', 'PB_RATE': '1', 'PB_INCL_TAX': '0', 'PB_MAX_BUYS': '0'}
_LB_PERIODS = {'all': ('All Time', None), 'month': ('This Month', 30), 'week': ('This Week', 7)}
_LB_NAME_MODES = {'name': 'Name', 'username': '@Username', 'masked': 'Masked (Pr***)'}
_LB_ME = {}

def _lbh(x): return _hlb.escape(str(x if x is not None else ''))
def _lbs(k): return str(get_setting(k, LB_DEF[k]) or LB_DEF[k])
def _lbn(k):
    try: return float(_lbs(k))
    except Exception: return float(LB_DEF[k])

def _lb_init():
    _db_exec("CREATE TABLE IF NOT EXISTS referrals (invitee INTEGER PRIMARY KEY, inviter INTEGER, created_at TEXT)")
    _db_exec("CREATE TABLE IF NOT EXISTS user_points (user_id INTEGER PRIMARY KEY, points REAL DEFAULT 0)")
    _db_exec("CREATE TABLE IF NOT EXISTS points_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, delta REAL, reason TEXT, created_at TEXT)")
    _db_exec("CREATE TABLE IF NOT EXISTS user_daily (user_id INTEGER PRIMARY KEY, last_day TEXT)")
    try: _db_exec("ALTER TABLE referrals ADD COLUMN rewarded INTEGER DEFAULT 1")
    except Exception: pass

def _lb_enabled_boards():
    ks = [k for k in _lbs('LB_BOARDS').split(',') if k in LB_BOARDS]
    return ks or ['points']

def _lb_default():
    d = _lbs('LB_DEFAULT'); en = _lb_enabled_boards()
    return d if d in en else en[0]

def _lb_bot_username():
    if 'u' not in _LB_ME:
        try: _LB_ME['u'] = bot.get_me().username
        except Exception: return ''
    return _LB_ME['u']

def _lb_add_points(uid, n, reason=''):
    _db_exec("INSERT INTO user_points (user_id, points) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET points = MAX(0, points + ?)",
             (uid, max(0, n), n))
    try: _db_exec("INSERT INTO points_log (user_id, delta, reason, created_at) VALUES (?,?,?,?)", (uid, n, reason, datetime.now().isoformat()))
    except Exception: pass

def _lb_points(uid):
    r = _db_q("SELECT points FROM user_points WHERE user_id=?", (uid,), one=True)
    return r[0] if r else 0

def _lb_since(period):
    days = _LB_PERIODS.get(period, _LB_PERIODS['all'])[1]
    return (datetime.now() - timedelta(days=days)).isoformat() if days else None

def _lb_rows(board):
    """[(uid, value)] sorted desc, filtered (banned / admins)."""
    since = _lb_since(_lbs('LB_PERIOD'))
    if board == 'points':
        rows = _db_q("SELECT user_id, points FROM user_points WHERE points > 0")
    elif board == 'refs':
        rows = (_db_q("SELECT inviter, COUNT(*) FROM referrals WHERE rewarded=1 AND created_at >= ? GROUP BY inviter", (since,)) if since
                else _db_q("SELECT inviter, COUNT(*) FROM referrals WHERE rewarded=1 GROUP BY inviter"))
    elif board == 'money':
        rows = (_db_q("SELECT user_id, SUM(amount_base) FROM payments WHERE created_at >= ? GROUP BY user_id", (since,)) if since
                else _db_q("SELECT user_id, SUM(amount_base) FROM payments GROUP BY user_id"))
    else:
        rows = _db_q("SELECT user_id, COUNT(*) FROM user_files GROUP BY user_id")
    hide = _lbs('LB_HIDE_ADMINS') == '1'
    out = [(u, v) for u, v in rows if v and v > 0 and u not in banned_users and not (hide and u in admin_ids)]
    out.sort(key=lambda x: (-x[1], x[0]))
    return out

def _lb_val(board, v):
    if board == 'money': return fmt_money(v)
    unit = LB_BOARDS[board][2]
    if float(v) == 1 and unit in ('bots', 'invites'): unit = unit[:-1]
    return f"{int(v) if float(v).is_integer() else round(v, 1)} {unit}".strip()

def _lb_name(uid):
    fn, un, _, _ = get_profile(uid, fetch=False)
    mode = _lbs('LB_NAMES')
    base = (fn or (un and '@' + un) or f"User{str(uid)[-4:]}").strip()
    if mode == 'username' and un: return '@' + un
    if mode == 'masked': return (base[:2] + '***') if len(base) > 2 else base[:1] + '***'
    return base[:16]

def _lb_text(board, uid):
    emo, ttl, _ = LB_BOARDS[board]
    rows = _lb_rows(board)
    size = int(_lbn('LB_SIZE'))
    per = _LB_PERIODS.get(_lbs('LB_PERIOD'), _LB_PERIODS['all'])[0] if board in ('refs', 'money') else 'All Time'
    medals = {1: '🥇', 2: '🥈', 3: '🥉'}
    L = [f"✦ <b>{_lbh(_lbs('LB_TITLE'))}</b> ✦", "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
         f"◈ {emo} <b>{ttl}</b>  ·  <i>{per}</i>", ""]
    body = []
    if not rows:
        body.append("<i>The board is waiting for its first champion.</i> 👑")
    for i, (u, v) in enumerate(rows[:size], 1):
        you = "  ◀ <b>YOU</b>" if u == uid else ""
        nm = _lbh(_lb_name(u))
        if i <= 3: body.append(f"{medals[i]} <b>{nm}</b> ▸ <b>{_lb_val(board, v)}</b>{you}")
        else: body.append(f"<code>{i:02d}</code> {nm} ▸ {_lb_val(board, v)}{you}")
    L.append("<blockquote>" + "\n".join(body) + "</blockquote>")
    L.append("▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬")
    pos = next((i for i, (u, _) in enumerate(rows, 1) if u == uid), None)
    if pos: L.append(f"◇ Your position  <b>#{pos}</b>  ▸  {_lb_val(board, rows[pos-1][1])}")
    else:
        mine = {'points': _lb_points(uid)}.get(board)
        L.append("◇ Your position  <i>not ranked yet</i>" + (f"  ▸  {_lb_val(board, mine)}" if mine else ""))
    L.append(f"◇ Competitors  <b>{len(rows)}</b>   ·   🕒 <i>{datetime.now():%H:%M}</i>")
    return "\n".join(L)

def _lb_markup(active):
    B = types.InlineKeyboardButton
    m = types.InlineKeyboardMarkup(row_width=2)
    tabs = [B(("✦ " if k == active else "") + f"{LB_BOARDS[k][0]} {LB_BOARDS[k][1].replace('Top ', '')}", callback_data=f"lb_b_{k}")
            for k in _lb_enabled_boards()]
    m.add(*tabs)
    m.add(B("🔄 Refresh", callback_data=f"lb_b_{active}"))
    m.add(B("🔙 Back to Main", callback_data="back_to_main"))
    return m

def _lb_show(chat_id, uid, board=None, message_id=None):
    if _lbs('LB_ENABLED') != '1' and uid not in admin_ids:
        txt, mk = "🏆 The leaderboard is currently unavailable.", None
        board = None
    else:
        en = _lb_enabled_boards()
        board = board if board in en else _lb_default()
        txt, mk = _lb_text(board, uid), _lb_markup(board)
    if message_id:
        try:
            bot.edit_message_text(txt, chat_id, message_id, reply_markup=mk, parse_mode='HTML'); return
        except Exception as e:
            if 'not modified' in str(e): return
    bot.send_message(chat_id, txt, reply_markup=mk, parse_mode='HTML')

def _logic_leaderboard(message):
    _lb_show(message.chat.id, message.from_user.id)

@bot.message_handler(commands=['leaderboard', 'top'])
def cmd_leaderboard(message): _logic_leaderboard(message)
# ---------------- admin settings ----------------
def _lb_admin_text():
    en = _lb_enabled_boards()
    return ("🏆 <b>Leaderboard Settings</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"Status: <b>{'ON ✅' if _lbs('LB_ENABLED') == '1' else 'OFF ❌'}</b>\n"
            f"Boards shown: <b>{', '.join(LB_BOARDS[k][1] for k in en)}</b>\n"
            f"Default board: <b>{LB_BOARDS[_lb_default()][1]}</b>\n"
            f"Entries per board: <b>{int(_lbn('LB_SIZE'))}</b>\n"
            f"Period (referrals/money): <b>{_LB_PERIODS.get(_lbs('LB_PERIOD'), _LB_PERIODS['all'])[0]}</b>\n"
            f"Names shown as: <b>{_LB_NAME_MODES.get(_lbs('LB_NAMES'), 'Name')}</b>\n"
            f"Hide admins: <b>{'Yes' if _lbs('LB_HIDE_ADMINS') == '1' else 'No'}</b>\n"
            f"Title: <b>{_lbh(_lbs('LB_TITLE'))}</b>\n\n"
            "Points, referral and spending rewards are managed in <b>🔗 Refer &amp; Points</b>.")

def _lb_admin_markup():
    B = types.InlineKeyboardButton
    en = _lb_enabled_boards()
    m = types.InlineKeyboardMarkup(row_width=2)
    m.row(B(f"Leaderboard: {'ON ✅' if _lbs('LB_ENABLED') == '1' else 'OFF ❌'}", callback_data="lb_a_on"))
    m.add(*[B(("✅ " if k in en else "❌ ") + f"{LB_BOARDS[k][0]} {LB_BOARDS[k][1]}", callback_data=f"lb_a_t_{k}") for k in LB_BOARDS])
    m.row(B("⭐ Default Board", callback_data="lb_a_def"), B(f"🔢 Size: {int(_lbn('LB_SIZE'))}", callback_data="lb_a_size"))
    m.row(B("📅 Period", callback_data="lb_a_per"), B("🙈 Name Style", callback_data="lb_a_names"))
    m.row(B(f"🛡 Hide Admins: {'Yes' if _lbs('LB_HIDE_ADMINS') == '1' else 'No'}", callback_data="lb_a_hide"), B("✏️ Title", callback_data="lb_a_title"))
    m.add(B("🔗 Refer & Points Settings", callback_data="rp_a_home"))
    m.row(B("👁 Preview", callback_data="lb_b_" + _lb_default()), B("🔙 Admin Panel", callback_data="admin_panel"))
    return m

def _lb_admin_show(call):
    try: bot.edit_message_text(_lb_admin_text(), call.message.chat.id, call.message.message_id,
                               reply_markup=_lb_admin_markup(), parse_mode='HTML')
    except Exception as e:
        if 'not modified' not in str(e): logger.debug(e)

def _lb_cycle(key, options):
    cur = _lbs(key)
    set_setting(key, options[(options.index(cur) + 1) % len(options)] if cur in options else options[0])

_LB_PROMPTS = {
    'title':  ("✏️ Send the new leaderboard title (max 30 chars).", 'LB_TITLE'),
}

def _lb_process_input(message, kind):
    if message.from_user.id not in admin_ids: return
    t = (message.text or '').strip()
    if t.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    if not t or len(t) > 30: bot.reply_to(message, "❌ 1–30 characters please."); return
    set_setting('LB_TITLE', t.upper()); bot.reply_to(message, "✅ Saved.")

def leaderboard_callback(call):
    d, uid = call.data, call.from_user.id
    if d.startswith('lb_b_'):
        bot.answer_callback_query(call.id)
        _lb_show(call.message.chat.id, uid, d[5:], call.message.message_id); return
    if uid not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin permissions required.", show_alert=True); return
    if d == 'lb_a_home': bot.answer_callback_query(call.id)
    elif d == 'lb_a_on': set_setting('LB_ENABLED', '0' if _lbs('LB_ENABLED') == '1' else '1'); bot.answer_callback_query(call.id, "Updated")
    elif d.startswith('lb_a_t_'):
        k = d[7:]; en = _lb_enabled_boards()
        if k in en and len(en) == 1: bot.answer_callback_query(call.id, "At least one board must stay enabled.", show_alert=True); return
        en = [x for x in en if x != k] if k in en else [x for x in LB_BOARDS if x in en or x == k]
        set_setting('LB_BOARDS', ','.join(en)); bot.answer_callback_query(call.id, "Updated")
    elif d == 'lb_a_def': _lb_cycle('LB_DEFAULT', _lb_enabled_boards()); bot.answer_callback_query(call.id, "Default: " + LB_BOARDS[_lb_default()][1])
    elif d == 'lb_a_size': _lb_cycle('LB_SIZE', ['5', '10', '15', '20']); bot.answer_callback_query(call.id, "Updated")
    elif d == 'lb_a_per': _lb_cycle('LB_PERIOD', list(_LB_PERIODS)); bot.answer_callback_query(call.id, "Period updated")
    elif d == 'lb_a_names': _lb_cycle('LB_NAMES', list(_LB_NAME_MODES)); bot.answer_callback_query(call.id, "Updated")
    elif d == 'lb_a_hide': set_setting('LB_HIDE_ADMINS', '0' if _lbs('LB_HIDE_ADMINS') == '1' else '1'); bot.answer_callback_query(call.id, "Updated")
    elif d.startswith('lb_a_') and d[5:] in _LB_PROMPTS:
        kind = d[5:]; bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, _LB_PROMPTS[kind][0] + "\n\n/cancel to abort.", parse_mode='HTML')
        bot.register_next_step_handler(msg, _lb_process_input, kind); return
    else: bot.answer_callback_query(call.id); return
    _lb_admin_show(call)

# ============================================================
# --- REFER & EARN + POINTS (user panel, hooks, admin manager) ---
# ============================================================
def _lbf(k): return _lbs(k) == '1'
def _rp_on(): return _lbf('POINTS_ON')
def _lbi(k): return int(_lbn(k))

def _lb_rank(uid, board='points'):
    for i, (u, _) in enumerate(_lb_rows(board), 1):
        if u == uid: return i
    return None

def _rp_ref_counts(uid):
    ok = (_db_q("SELECT COUNT(*) FROM referrals WHERE inviter=? AND rewarded=1", (uid,), one=True) or [0])[0]
    pend = (_db_q("SELECT COUNT(*) FROM referrals WHERE inviter=? AND rewarded=0", (uid,), one=True) or [0])[0]
    return ok, pend

def _rp_link(uid): return f"https://t.me/{_lb_bot_username()}?start=ref_{uid}"

def _rp_reward(inviter, invitee_name):
    """Give the referral reward (+ milestone) to the inviter."""
    pts = _lbi('REF_POINTS')
    extra = ''
    if pts > 0: _lb_add_points(inviter, pts, 'referral')
    n = _rp_ref_counts(inviter)[0]
    msn, msp = _lbi('REF_MS_N'), _lbi('REF_MS_PTS')
    if msn > 0 and msp > 0 and n % msn == 0:
        _lb_add_points(inviter, msp, 'milestone'); extra = f"\n🏅 Milestone <b>{n} referrals</b>! Bonus <b>+{msp} points</b>."
    if _lbf('REF_NOTIFY'):
        try: bot.send_message(inviter, f"🎉 <b>{_lbh(invitee_name or 'A new user')}</b> joined with your link!"
                                       + (f"\n⭐ You earned <b>+{pts} points</b>." if pts > 0 else "") + extra, parse_mode='HTML')
        except Exception: pass

# --- referral capture on /start ref_<id> ---
_lb_orig_welcome = _logic_send_welcome
def _logic_send_welcome(message):
    try:
        uid = message.from_user.id
        parts = (message.text or '').split(maxsplit=1)
        if _rp_on() and _lbf('REF_ON') and len(parts) == 2 and parts[1].startswith('ref_') and parts[1][4:].isdigit():
            inviter = int(parts[1][4:])
            is_new = not _db_q("SELECT 1 FROM active_users WHERE user_id=?", (uid,), one=True)
            if (is_new and inviter != uid and inviter not in banned_users
                    and _db_q("SELECT 1 FROM active_users WHERE user_id=?", (inviter,), one=True)
                    and not _db_q("SELECT 1 FROM referrals WHERE invitee=?", (uid,), one=True)):
                total = (_db_q("SELECT COUNT(*) FROM referrals WHERE inviter=?", (inviter,), one=True) or [0])[0]
                mx = _lbi('REF_MAX')
                state = -1 if (mx > 0 and total >= mx) else (0 if _lbf('REF_REQ_UPLOAD') else 1)
                _db_exec("INSERT OR IGNORE INTO referrals (invitee, inviter, created_at, rewarded) VALUES (?, ?, ?, ?)",
                         (uid, inviter, datetime.now().isoformat(), state))
                if state == 1: _rp_reward(inviter, message.from_user.first_name)
                nb = _lbi('REF_NEW_BONUS')
                if nb > 0:
                    _lb_add_points(uid, nb, 'welcome_bonus')
                    try: bot.send_message(message.chat.id, f"🎁 Welcome bonus: <b>+{nb} points</b> added to your account!", parse_mode='HTML')
                    except Exception: pass
    except Exception as e:
        logger.warning(f"referral capture failed: {e}")
    return _lb_orig_welcome(message)

# --- delayed referral reward: invitee's first upload ---
_rp_orig_save = save_user_file
def save_user_file(user_id, project_name, main_file, file_type='py'):
    res = _rp_orig_save(user_id, project_name, main_file, file_type)
    try:
        if _rp_on() and _lbf('REF_REQ_UPLOAD'):
            r = _db_q("SELECT inviter FROM referrals WHERE invitee=? AND rewarded=0", (user_id,), one=True)
            if r:
                rc, _ = _db_exec("UPDATE referrals SET rewarded=1 WHERE invitee=? AND rewarded=0", (user_id,))
                if rc: _rp_reward(r[0], get_profile(user_id, fetch=False)[0])
    except Exception as e:
        logger.warning(f"upload referral reward failed: {e}")
    return res

# --- points for spending ---
_lb_orig_complete = complete_purchase
def complete_purchase(user_id, plan, method, paid_text, amount_base, ref, coupon=''):
    res = _lb_orig_complete(user_id, plan, method, paid_text, amount_base, ref, coupon)
    try:
        amt, unit = float(amount_base or 0), _lbn('SPEND_UNIT')
        if _rp_on() and _lbf('SPEND_ON') and unit > 0 and amt >= _lbn('SPEND_MIN') and amt > 0:
            pts = int(amt / unit * _lbn('BUY_POINTS'))
            if pts > 0:
                _lb_add_points(user_id, pts, 'purchase')
                try: bot.send_message(user_id, f"⭐ You earned <b>+{pts} points</b> for your purchase!", parse_mode='HTML')
                except Exception: pass
    except Exception as e:
        logger.warning(f"purchase points failed: {e}")
    return res

# ---------------- user panel ----------------
def _rp_home_text(uid):
    if not _rp_on():
        return "✦ <b>𝗥𝗘𝗙𝗘𝗥  &amp;  𝗘𝗔𝗥𝗡</b> ✦\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n<blockquote><i>This feature is currently disabled.</i></blockquote>"
    ok, pend = _rp_ref_counts(uid)
    rank = _lb_rank(uid)
    ways = []
    if _lbf('REF_ON'):
        ways.append(f"👥 Each referral ▸ <b>+{_lbi('REF_POINTS')} pts</b>" + (" <i>(after they upload a bot)</i>" if _lbf('REF_REQ_UPLOAD') else ""))
        if _lbi('REF_NEW_BONUS') > 0: ways.append(f"🎁 Friend's welcome bonus ▸ <b>+{_lbi('REF_NEW_BONUS')} pts</b>")
        if _lbi('REF_MS_N') > 0 and _lbi('REF_MS_PTS') > 0: ways.append(f"🏅 Every {_lbi('REF_MS_N')} referrals ▸ <b>+{_lbi('REF_MS_PTS')} pts</b>")
    if _lbf('SPEND_ON'): ways.append(f"💳 Every {fmt_money(_lbn('SPEND_UNIT'))} spent ▸ <b>+{_lbi('BUY_POINTS')} pts</b>")
    if _lbf('DAILY_ON'): ways.append(f"📅 Daily check-in ▸ <b>+{_lbi('DAILY_PTS')} pts</b>")
    L = ["✦ <b>𝗥𝗘𝗙𝗘𝗥  &amp;  𝗘𝗔𝗥𝗡</b> ✦", "<i>Invite friends and turn them into rewards</i>", "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]
    if ways: L += ["<b>◈ WAYS TO EARN</b>", "<blockquote>" + "\n".join(ways) + "</blockquote>"]
    if _lbf('REDEEM_ON'): L += ["<b>◈ REDEEM</b>", f"<blockquote>🎟 <b>{_lbi('REDEEM_COST')} pts</b> = 1 day of premium</blockquote>"]
    L += ["<b>◈ YOUR STATS</b>",
          f"<blockquote>⭐ Points ▸ <b>{int(_lb_points(uid))}</b>\n👥 Referrals ▸ <b>{ok}</b>" + (f"  <i>({pend} pending)</i>" if pend else "") +
          f"\n🏅 Rank ▸ <b>{('#' + str(rank)) if rank else '—'}</b></blockquote>",
          "<b>◈ YOUR PERSONAL LINK</b>", f"<code>{_lbh(_rp_link(uid))}</code>"]
    return "\n".join(L)

def _rp_home_markup(uid):
    B = types.InlineKeyboardButton
    m = types.InlineKeyboardMarkup(row_width=2)
    if _rp_on():
        m.add(B("📤 Share My Link", url="https://t.me/share/url?url=" + _rp_link(uid) + "&text=Host%20your%20bots%2024%2F7!"))
        row = []
        if _lbf('DAILY_ON'): row.append(B("📅 Daily Bonus", callback_data="rp_daily"))
        if _lbf('REDEEM_ON'): row.append(B("🎟 Redeem", callback_data="rp_redeem"))
        if row: m.row(*row)
        m.row(B("📜 History", callback_data="rp_hist"), B("👥 My Referrals", callback_data="rp_refs"))
        m.add(B("🏆 Leaderboard", callback_data="lb_b_" + _lb_default()))
    m.add(B("🔙 Back to Main", callback_data="back_to_main"))
    return m

def _rp_edit(call, txt, mk):
    try: bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=mk, parse_mode='HTML')
    except Exception as e:
        if 'not modified' in str(e): return
        bot.send_message(call.message.chat.id, txt, reply_markup=mk, parse_mode='HTML')

def _logic_refer(message):
    uid = message.from_user.id
    bot.send_message(message.chat.id, _rp_home_text(uid), reply_markup=_rp_home_markup(uid), parse_mode='HTML')

@bot.message_handler(commands=['refer', 'points'])
def cmd_refer(message): _logic_refer(message)

def _rp_back_mk(uid=None):
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("🔙 Back", callback_data="rp_home"))
    return mk

def _rp_redeem_view(uid):
    cost, mx, pts = max(1, _lbi('REDEEM_COST')), max(1, _lbi('REDEEM_MAX')), int(_lb_points(uid))
    B = types.InlineKeyboardButton
    m = types.InlineKeyboardMarkup(row_width=2)
    opts = [d for d in (1, 3, 7, 15, 30) if d <= mx]
    if mx not in opts and mx < 90: opts.append(mx)
    m.add(*[B(f"{d} day{'s' if d > 1 else ''} · {d * cost} pts" + ("" if pts >= d * cost else " 🔒"), callback_data=f"rp_rd_{d}") for d in opts])
    m.add(B("🔙 Back", callback_data="rp_home"))
    return (f"🎟 <b>Redeem Points</b>\n━━━━━━━━━━━━━━━━━━\n⭐ Balance: <b>{pts} pts</b>\n"
            f"💱 Rate: <b>{cost} pts = 1 day</b> of premium\n\nChoose how many days to add 👇"), m

def _rp_do_daily(uid):
    today = datetime.now().strftime('%Y-%m-%d')
    rc, _ = _db_exec("UPDATE user_daily SET last_day=? WHERE user_id=? AND last_day<>?", (today, uid, today))
    if not rc: rc, _ = _db_exec("INSERT OR IGNORE INTO user_daily (user_id, last_day) VALUES (?, ?)", (uid, today))
    if rc: _lb_add_points(uid, _lbi('DAILY_PTS'), 'daily'); return True
    return False

def points_callback(call):
    d, uid = call.data, call.from_user.id
    if d.startswith('rp_a_'):
        if uid not in admin_ids:
            bot.answer_callback_query(call.id, "⚠️ Admin permissions required.", show_alert=True); return
        return _rp_admin_cb(call)
    if not _rp_on() and d != 'rp_home':
        bot.answer_callback_query(call.id, "Refer & Earn is currently disabled.", show_alert=True); return
    if d == 'rp_home':
        bot.answer_callback_query(call.id); _rp_edit(call, _rp_home_text(uid), _rp_home_markup(uid))
    elif d == 'rp_daily':
        if not _lbf('DAILY_ON'): bot.answer_callback_query(call.id, "Daily bonus is off.", show_alert=True); return
        if _rp_do_daily(uid): bot.answer_callback_query(call.id, f"🎁 +{_lbi('DAILY_PTS')} points claimed!", show_alert=True)
        else: bot.answer_callback_query(call.id, "✅ Already claimed today — come back tomorrow!", show_alert=True)
        _rp_edit(call, _rp_home_text(uid), _rp_home_markup(uid))
    elif d == 'rp_redeem':
        if not _lbf('REDEEM_ON'): bot.answer_callback_query(call.id, "Redeem is off.", show_alert=True); return
        bot.answer_callback_query(call.id); t, m = _rp_redeem_view(uid); _rp_edit(call, t, m)
    elif d.startswith('rp_rd_'):
        if not _lbf('REDEEM_ON'): bot.answer_callback_query(call.id, "Redeem is off.", show_alert=True); return
        days = int(d[6:]); cost = max(1, _lbi('REDEEM_COST')) * days
        if days < 1 or days > max(1, _lbi('REDEEM_MAX')): bot.answer_callback_query(call.id, "Invalid amount.", show_alert=True); return
        rc, _ = _db_exec("UPDATE user_points SET points = points - ? WHERE user_id=? AND points >= ?", (cost, uid, cost))
        if not rc: bot.answer_callback_query(call.id, f"❌ You need {cost} points.", show_alert=True); return
        try: _db_exec("INSERT INTO points_log (user_id, delta, reason, created_at) VALUES (?,?,?,?)", (uid, -cost, f'redeem_{days}d', datetime.now().isoformat()))
        except Exception: pass
        now = datetime.now(); cur = user_subscriptions.get(uid)
        if cur and cur['expiry'] > now: expiry, pn, lim = cur['expiry'] + timedelta(days=days), cur.get('plan_name'), cur.get('file_limit')
        else: expiry, pn, lim = now + timedelta(days=days), "Rewards", SUBSCRIBED_USER_LIMIT
        save_subscription(uid, expiry, pn, lim)
        bot.answer_callback_query(call.id, f"🎉 +{days} day(s) added!", show_alert=True)
        t, m = _rp_redeem_view(uid)
        _rp_edit(call, f"✅ <b>Redeemed {days} day(s)</b> · premium active until <b>{expiry:%d-%m-%Y}</b>\n\n" + t, m)
    elif d == 'rp_hist':
        bot.answer_callback_query(call.id)
        rows = _db_q("SELECT delta, reason, created_at FROM points_log WHERE user_id=? ORDER BY id DESC LIMIT 12", (uid,))
        L = ["📜 <b>Points History</b>", "━━━━━━━━━━━━━━━━━━"]
        L += [f"{'🟢' if dl > 0 else '🔴'} <b>{dl:+g}</b> · {_lbh(rs.replace('_', ' '))} · <i>{ca[:10]}</i>" for dl, rs, ca in rows] or ["<i>No activity yet.</i>"]
        L.append(f"\n⭐ Balance: <b>{int(_lb_points(uid))} pts</b>")
        _rp_edit(call, "\n".join(L), _rp_back_mk())
    elif d == 'rp_refs':
        bot.answer_callback_query(call.id)
        rows = _db_q("SELECT invitee, rewarded, created_at FROM referrals WHERE inviter=? ORDER BY created_at DESC LIMIT 15", (uid,))
        L = ["👥 <b>My Referrals</b>", "━━━━━━━━━━━━━━━━━━"]
        st = {1: '✅', 0: '⏳', -1: '🚫'}
        L += [f"{st.get(r, '✅')} {_lbh(_lb_name(u))} · <i>{ca[:10]}</i>" for u, r, ca in rows] or ["<i>No referrals yet — share your link!</i>"]
        L.append("\n✅ rewarded · ⏳ waiting for first upload · 🚫 over limit")
        _rp_edit(call, "\n".join(L), _rp_back_mk())
    else: bot.answer_callback_query(call.id)

# ---------------- admin manager ----------------
RP_TOGGLES = {
    'POINTS_ON': "Points System", 'REF_ON': "Referral Rewards", 'REF_REQ_UPLOAD': "Reward after 1st upload",
    'REF_NOTIFY': "Notify inviter", 'PB_ON': "Buy Plans with Points", 'PB_INCL_TAX': "Include tax in points price", 'SPEND_ON': "Spending Rewards", 'DAILY_ON': "Daily Bonus", 'REDEEM_ON': "Redeem for Premium",
}
RP_NUMS = {   # key: (label, min, max)
    'REF_POINTS': ("Points per referral", 0, 100000), 'REF_NEW_BONUS': ("Friend welcome bonus", 0, 100000),
    'REF_MAX': ("Max referrals/user (0=∞)", 0, 1000000), 'REF_MS_N': ("Milestone every N referrals (0=off)", 0, 100000),
    'REF_MS_PTS': ("Milestone bonus points", 0, 100000),
    'BUY_POINTS': ("Points per spend unit", 0, 100000), 'SPEND_UNIT': ("Spend unit (amount)", 1, 10000000),
    'SPEND_MIN': ("Min purchase for points", 0, 10000000),
    'DAILY_PTS': ("Daily bonus points", 0, 100000), 'REDEEM_COST': ("Points per premium day", 1, 1000000),
    'REDEEM_MAX': ("Max days per redeem", 1, 365),
    'PB_RATE': ("Points per 1 currency unit", 1, 1000000), 'PB_MAX_BUYS': ("Max points purchases/user (0=∞)", 0, 100000),
}
RP_PAGES = {
    'ref': ("👥 Referral Rewards", ['REF_ON', 'REF_REQ_UPLOAD', 'REF_NOTIFY'], ['REF_POINTS', 'REF_NEW_BONUS', 'REF_MAX', 'REF_MS_N', 'REF_MS_PTS']),
    'sp':  ("💳 Spending Rewards", ['SPEND_ON'], ['BUY_POINTS', 'SPEND_UNIT', 'SPEND_MIN']),
    'pb':  ("🛍 Buy with Points", ['PB_ON', 'PB_INCL_TAX'], ['PB_RATE', 'PB_MAX_BUYS']),
    'dr':  ("📅 Daily & Redeem", ['DAILY_ON', 'REDEEM_ON'], ['DAILY_PTS', 'REDEEM_COST', 'REDEEM_MAX']),
}

def _rp_a_home():
    tot = (_db_q("SELECT COALESCE(SUM(points),0), COUNT(*) FROM user_points WHERE points>0", one=True) or (0, 0))
    refs = (_db_q("SELECT COUNT(*) FROM referrals WHERE rewarded=1", one=True) or [0])[0]
    onoff = lambda k: '✅' if _lbf(k) else '❌'
    txt = ("🔗 <b>Refer &amp; Points Manager</b>\n━━━━━━━━━━━━━━━━━━\n"
           f"Points system: <b>{'ON ✅' if _rp_on() else 'OFF ❌'}</b>\n"
           f"{onoff('REF_ON')} Referral: <b>+{_lbi('REF_POINTS')}</b> pts each\n"
           f"{onoff('SPEND_ON')} Spending: <b>+{_lbi('BUY_POINTS')}</b> pts per {fmt_money(_lbn('SPEND_UNIT'))}\n"
           f"{onoff('DAILY_ON')} Daily bonus: <b>+{_lbi('DAILY_PTS')}</b> pts\n"
           f"{onoff('REDEEM_ON')} Redeem: <b>{_lbi('REDEEM_COST')}</b> pts / day\n"
           f"{onoff('PB_ON')} Buy plans with points: <b>{_lbi('PB_RATE')}</b> pts per {fmt_money(1)}\n\n"
           f"⭐ Points in circulation: <b>{int(tot[0])}</b> ({tot[1]} users)\n👥 Total referrals: <b>{refs}</b>")
    B = types.InlineKeyboardButton
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(B(f"Points System: {'ON ✅' if _rp_on() else 'OFF ❌'}", callback_data="rp_a_tg_POINTS_ON"))
    m.row(B("👥 Referral Rewards", callback_data="rp_a_pg_ref"), B("💳 Spending Rewards", callback_data="rp_a_pg_sp"))
    m.row(B("📅 Daily & Redeem", callback_data="rp_a_pg_dr"), B("🛍 Buy with Points", callback_data="rp_a_pg_pb"))
    m.add(B("👤 User Points", callback_data="rp_a_users"))
    m.row(B("📊 Reports & Export", callback_data="rp_a_rep"), B("🏆 Leaderboard Settings", callback_data="lb_a_home"))
    m.add(B("🔙 Admin Panel", callback_data="admin_panel"))
    return txt, m

def _rp_a_page(pg):
    title, tg, nm = RP_PAGES[pg]
    B = types.InlineKeyboardButton
    m = types.InlineKeyboardMarkup(row_width=1)
    for k in tg: m.add(B(f"{'✅' if _lbf(k) else '❌'} {RP_TOGGLES[k]}", callback_data=f"rp_a_tg_{k}_{pg}"))
    for k in nm: m.add(B(f"✏️ {RP_NUMS[k][0]}: {_lbi(k)}", callback_data=f"rp_a_nm_{k}_{pg}"))
    if pg == 'pb': m.add(B("📦 Plan Points Prices", callback_data="rp_a_pps"))
    m.add(B("🔙 Back", callback_data="rp_a_home"))
    return f"{title}\n━━━━━━━━━━━━━━━━━━\nTap a switch to turn it on/off, or a number to change it.", m

def _rp_a_users():
    B = types.InlineKeyboardButton
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(B("🔍 Find / Manage a User", callback_data="rp_a_find"))
    m.row(B("➕ Give Points", callback_data="rp_a_give"), B("➖ Remove Points", callback_data="rp_a_take"))
    m.row(B("🎯 Set Exact Points", callback_data="rp_a_set"), B("🎁 Give Points to ALL", callback_data="rp_a_all"))
    m.add(B("🔙 Back", callback_data="rp_a_home"))
    return "👤 <b>User Points</b>\n━━━━━━━━━━━━━━━━━━\nAdd, remove or set points for any user, or reward everyone at once.", m

def _rp_a_user_view(uid):
    fn, un, _, _ = get_profile(uid, fetch=True)
    ok, pend = _rp_ref_counts(uid)
    inv = _db_q("SELECT inviter FROM referrals WHERE invitee=?", (uid,), one=True)
    spent = (_db_q("SELECT COALESCE(SUM(amount_base),0) FROM payments WHERE user_id=?", (uid,), one=True) or [0])[0]
    L = (f"👤 <b>{_lbh(fn or 'User')}</b> {('@' + _lbh(un)) if un else ''}\n🆔 <code>{uid}</code>\n━━━━━━━━━━━━━━━━━━\n"
         f"⭐ Points: <b>{int(_lb_points(uid))}</b>  (rank {('#' + str(_lb_rank(uid))) if _lb_rank(uid) else '—'})\n"
         f"👥 Referrals: <b>{ok}</b>{f' (+{pend} pending)' if pend else ''}\n💰 Spent: <b>{fmt_money(spent) if spent else '—'}</b>\n"
         f"🔗 Invited by: <b>{inv[0] if inv else '—'}</b>")
    B = types.InlineKeyboardButton
    m = types.InlineKeyboardMarkup(row_width=3)
    m.row(*[B(f"+{n}", callback_data=f"rp_a_adj_{uid}_{n}") for n in (10, 50, 100)])
    m.row(*[B(f"-{n}", callback_data=f"rp_a_adj_{uid}_-{n}") for n in (10, 50, 100)])
    m.row(B("🎯 Set Exact", callback_data=f"rp_a_setu_{uid}"), B("♻️ Reset to 0", callback_data=f"rp_a_zero_{uid}"))
    m.row(B("📜 History", callback_data=f"rp_a_hist_{uid}"), B("👥 Referrals", callback_data=f"rp_a_rl_{uid}"))
    m.add(B("🔙 Back", callback_data="rp_a_users"))
    return L, m

def _rp_a_rep():
    B = types.InlineKeyboardButton
    m = types.InlineKeyboardMarkup(row_width=2)
    m.row(B("🏅 Top 20 Points", callback_data="rp_a_top"), B("🧾 Recent Activity", callback_data="rp_a_log"))
    m.add(B("📤 Export CSV (users, points, referrals)", callback_data="rp_a_csv"))
    m.row(B("🗑 Reset Points", callback_data="rp_a_rst_points"), B("🗑 Reset Referrals", callback_data="rp_a_rst_refs"))
    m.add(B("🗑 Clear Points Log", callback_data="rp_a_rst_log"))
    m.add(B("🔙 Back", callback_data="rp_a_home"))
    return "📊 <b>Reports &amp; Export</b>\n━━━━━━━━━━━━━━━━━━", m

def _rp_prompt(call, text, kind, ctx=None):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, text + "\n\n/cancel to abort.", parse_mode='HTML')
    bot.register_next_step_handler(msg, _rp_input, kind, ctx)

def _rp_apply(uid, mode, n, reason):
    if mode == 'give': _lb_add_points(uid, n, reason)
    elif mode == 'take': _lb_add_points(uid, -n, reason)
    else:
        cur = _lb_points(uid)
        _db_exec("INSERT INTO user_points (user_id, points) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET points=?", (uid, n, n))
        try: _db_exec("INSERT INTO points_log (user_id, delta, reason, created_at) VALUES (?,?,?,?)", (uid, n - cur, 'admin_set', datetime.now().isoformat()))
        except Exception: pass

def _rp_input(message, kind, ctx):
    if message.from_user.id not in admin_ids: return
    t = (message.text or '').strip()
    if t.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    try:
        if kind.startswith('nm:'):
            key = kind[3:]; lab, lo, hi = RP_NUMS[key]; n = int(t)
            if n < lo or n > hi: raise ValueError(f"Enter a whole number {lo}–{hi}.")
            set_setting(key, str(n)); bot.reply_to(message, f"✅ {lab} = <b>{n}</b>", parse_mode='HTML'); return
        if kind == 'find':
            uid = int(t.lstrip('@')) if t.lstrip('@').isdigit() else None
            if uid is None:
                r = _db_q("SELECT user_id FROM active_users WHERE LOWER(username)=?", (t.lstrip('@').lower(),), one=True)
                if not r: raise ValueError("User not found. Send a numeric ID or a known @username.")
                uid = r[0]
            txt, mk = _rp_a_user_view(uid); bot.send_message(message.chat.id, txt, reply_markup=mk, parse_mode='HTML'); return
        if kind == 'all':
            n = int(t)
            if n <= 0 or n > 100000: raise ValueError("Enter 1–100000.")
            mk = types.InlineKeyboardMarkup()
            mk.row(types.InlineKeyboardButton("✅ Confirm", callback_data=f"rp_a_allc_{n}"), types.InlineKeyboardButton("❌ Cancel", callback_data="rp_a_users"))
            cnt = (_db_q("SELECT COUNT(*) FROM active_users", one=True) or [0])[0]
            bot.send_message(message.chat.id, f"🎁 Give <b>+{n} points</b> to <b>{cnt}</b> users?", reply_markup=mk, parse_mode='HTML'); return
        if kind == 'pp':
            n = int(t)
            if n < -1 or n > 100000000: raise ValueError("Enter -1, 0 or a positive number.")
            set_setting(f'PB_PLAN_{ctx}', str(n)); bot.reply_to(message, "✅ Saved. Plan points price: " + ("disabled" if n < 0 else ("automatic" if n == 0 else f"{n} pts"))); return
        # give / take / set  (ctx = fixed uid or None)
        parts = t.split()
        if ctx is None:
            if len(parts) != 2: raise ValueError("Send: USER_ID POINTS")
            uid, n = int(parts[0]), int(parts[1])
        else:
            uid, n = ctx, int(parts[0])
        if n < 0 or (kind != 'set' and n == 0) or n > 10000000: raise ValueError("Enter a valid positive number.")
        _rp_apply(uid, kind, n, 'admin_' + kind)
        if kind == 'give':
            try: bot.send_message(uid, f"🎁 An admin gave you <b>+{n} points</b>!", parse_mode='HTML')
            except Exception: pass
        txt, mk = _rp_a_user_view(uid)
        bot.send_message(message.chat.id, "✅ Done.\n\n" + txt, reply_markup=mk, parse_mode='HTML')
    except ValueError as e:
        msg = str(e)
        bot.reply_to(message, "❌ " + (msg if msg and 'invalid literal' not in msg else "Invalid input. Numbers only."))
    except Exception as e:
        logger.warning(f"rp input failed: {e}"); bot.reply_to(message, "❌ Something went wrong.")

def _rp_all_job(chat_id, n):
    ids = [r[0] for r in _db_q("SELECT user_id FROM active_users") if r[0] not in banned_users]
    for u in ids: _lb_add_points(u, n, 'admin_all')
    try: bot.send_message(chat_id, f"✅ Gave +{n} points to {len(ids)} users.")
    except Exception: pass

def _rp_a_export(chat_id):
    import io as _io
    buf = _io.StringIO(); w = _csv.writer(buf)
    w.writerow(['user_id', 'name', 'username', 'points', 'referrals', 'pending_referrals', 'invited_by', 'spent_base'])
    ids = {r[0] for r in _db_q("SELECT user_id FROM user_points")} | {r[0] for r in _db_q("SELECT inviter FROM referrals")}
    for u in sorted(ids):
        fn, un, _, _ = get_profile(u, fetch=False); ok, pend = _rp_ref_counts(u)
        inv = _db_q("SELECT inviter FROM referrals WHERE invitee=?", (u,), one=True)
        sp = (_db_q("SELECT COALESCE(SUM(amount_base),0) FROM payments WHERE user_id=?", (u,), one=True) or [0])[0]
        w.writerow([u, fn, un, int(_lb_points(u)), ok, pend, inv[0] if inv else '', sp])
    data = _io.BytesIO(buf.getvalue().encode('utf-8-sig')); data.name = f"points_{datetime.now():%Y%m%d_%H%M}.csv"
    bot.send_document(chat_id, data, caption=f"📤 {len(ids)} users")

def _rp_admin_cb(call):
    d, chat = call.data, call.message.chat.id
    if d == 'rp_a_home': bot.answer_callback_query(call.id); t, m = _rp_a_home(); return _rp_edit(call, t, m)
    if d.startswith('rp_a_tg_'):
        rest = d[8:]; pg = None
        for k in RP_TOGGLES:
            if rest == k or rest.startswith(k + '_'):
                if k == 'REF_ON' and rest.startswith('REF_ON_'): pass
                key = k; pg = rest[len(k) + 1:] or None; break
        else: bot.answer_callback_query(call.id); return
        # longest-key safety (REF_REQ_UPLOAD vs REF_ON etc. are distinct prefixes)
        set_setting(key, '0' if _lbf(key) else '1'); bot.answer_callback_query(call.id, f"{RP_TOGGLES[key]}: {'ON' if _lbf(key) else 'OFF'}")
        t, m = _rp_a_page(pg) if pg in RP_PAGES else _rp_a_home(); return _rp_edit(call, t, m)
    if d.startswith('rp_a_pg_'): bot.answer_callback_query(call.id); t, m = _rp_a_page(d[8:]); return _rp_edit(call, t, m)
    if d.startswith('rp_a_nm_'):
        rest = d[8:]; key = next((k for k in RP_NUMS if rest == k or rest.startswith(k + '_')), None)
        if not key: bot.answer_callback_query(call.id); return
        lab, lo, hi = RP_NUMS[key]
        return _rp_prompt(call, f"✏️ <b>{lab}</b>\nCurrent: <b>{_lbi(key)}</b>\nSend a whole number ({lo}–{hi}).", 'nm:' + key)
    if d == 'rp_a_users': bot.answer_callback_query(call.id); t, m = _rp_a_users(); return _rp_edit(call, t, m)
    if d == 'rp_a_find': return _rp_prompt(call, "🔍 Send the user's <b>ID</b> or <b>@username</b>.", 'find')
    if d in ('rp_a_give', 'rp_a_take', 'rp_a_set'):
        return _rp_prompt(call, {'give': "➕", 'take': "➖", 'set': "🎯"}[d[5:]] + " Send: <code>USER_ID POINTS</code>\ne.g. <code>8931203734 50</code>", d[5:])
    if d == 'rp_a_all': return _rp_prompt(call, "🎁 How many points should EVERY user receive?", 'all')
    if d.startswith('rp_a_allc_'):
        bot.answer_callback_query(call.id, "Working…"); threading.Thread(target=_rp_all_job, args=(chat, int(d[10:])), daemon=True).start()
        t, m = _rp_a_users(); return _rp_edit(call, t, m)
    if d.startswith('rp_a_adj_'):
        _, _, _, u, n = d.split('_'); u, n = int(u), int(n)
        _rp_apply(u, 'give' if n > 0 else 'take', abs(n), 'admin_adjust'); bot.answer_callback_query(call.id, f"{n:+d} pts")
        t, m = _rp_a_user_view(u); return _rp_edit(call, t, m)
    if d.startswith('rp_a_setu_'): return _rp_prompt(call, "🎯 Send the new exact points total for this user.", 'set', int(d[10:]))
    if d.startswith('rp_a_zero_'):
        u = int(d[10:]); _rp_apply(u, 'set', 0, 'admin_reset'); bot.answer_callback_query(call.id, "Reset to 0")
        t, m = _rp_a_user_view(u); return _rp_edit(call, t, m)
    if d.startswith('rp_a_hist_'):
        u = int(d[10:]); bot.answer_callback_query(call.id)
        rows = _db_q("SELECT delta, reason, created_at FROM points_log WHERE user_id=? ORDER BY id DESC LIMIT 15", (u,))
        L = [f"📜 <b>History · <code>{u}</code></b>", "━━━━━━━━━━━━━━━━━━"] + \
            [f"{'🟢' if dl > 0 else '🔴'} <b>{dl:+g}</b> · {_lbh(rs.replace('_', ' '))} · <i>{ca[:16].replace('T', ' ')}</i>" for dl, rs, ca in rows]
        if not rows: L.append("<i>No activity.</i>")
        mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"rp_a_u_{u}"))
        return _rp_edit(call, "\n".join(L), mk)
    if d.startswith('rp_a_rl_'):
        u = int(d[8:]); bot.answer_callback_query(call.id)
        rows = _db_q("SELECT invitee, rewarded, created_at FROM referrals WHERE inviter=? ORDER BY created_at DESC LIMIT 20", (u,))
        st = {1: '✅', 0: '⏳', -1: '🚫'}
        L = [f"👥 <b>Referrals of <code>{u}</code></b>", "━━━━━━━━━━━━━━━━━━"] + \
            [f"{st.get(r, '✅')} <code>{i}</code> {_lbh(_lb_name(i))} · <i>{ca[:10]}</i>" for i, r, ca in rows]
        if not rows: L.append("<i>None.</i>")
        mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"rp_a_u_{u}"))
        return _rp_edit(call, "\n".join(L), mk)
    if d.startswith('rp_a_u_'):
        bot.answer_callback_query(call.id); t, m = _rp_a_user_view(int(d[7:])); return _rp_edit(call, t, m)
    if d == 'rp_a_pps':
        bot.answer_callback_query(call.id)
        B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
        for p in get_all_plans():
            if is_free_plan(p[1], p[3]): continue
            ov = _pb_plan_setting(p[0]); auto = _pb_cost(0, p) if ov == 0 else None
            lab = "🚫 off" if ov < 0 else (f"{ov} pts (custom)" if ov > 0 else (f"{auto} pts (auto)" if auto else "auto"))
            m.add(B(f"{str(p[1])[:20]} — {lab}", callback_data=f"rp_a_pp_{p[0]}"))
        m.add(B("🔙 Back", callback_data="rp_a_pg_pb"))
        return _rp_edit(call, "📦 <b>Plan Points Prices</b>\n━━━━━━━━━━━━━━━━━━\nTap a plan to set its points price.\n<code>0</code> = automatic (price × rate) · <code>-1</code> = can't be bought with points", m)
    if d.startswith('rp_a_pp_'):
        return _rp_prompt(call, "✏️ Send the points price for this plan.\n<code>0</code> = automatic · <code>-1</code> = disabled", 'pp', int(d[8:]))
    if d == 'rp_a_rep': bot.answer_callback_query(call.id); t, m = _rp_a_rep(); return _rp_edit(call, t, m)
    if d == 'rp_a_top':
        bot.answer_callback_query(call.id)
        L = ["🏅 <b>Top 20 by Points</b>", "━━━━━━━━━━━━━━━━━━"]
        rows = _db_q("SELECT user_id, points FROM user_points WHERE points>0 ORDER BY points DESC LIMIT 20")
        L += [f"<code>{i:>2}.</code> <code>{u}</code> {_lbh(_lb_name(u))} — <b>{int(p)}</b>" for i, (u, p) in enumerate(rows, 1)] or ["<i>Nobody has points yet.</i>"]
        mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔙 Back", callback_data="rp_a_rep"))
        return _rp_edit(call, "\n".join(L), mk)
    if d == 'rp_a_log':
        bot.answer_callback_query(call.id)
        rows = _db_q("SELECT user_id, delta, reason, created_at FROM points_log ORDER BY id DESC LIMIT 20")
        L = ["🧾 <b>Recent Points Activity</b>", "━━━━━━━━━━━━━━━━━━"] + \
            [f"{'🟢' if dl > 0 else '🔴'} <code>{u}</code> <b>{dl:+g}</b> · {_lbh(rs.replace('_', ' '))} · <i>{ca[5:16].replace('T', ' ')}</i>" for u, dl, rs, ca in rows]
        if not rows: L.append("<i>No activity yet.</i>")
        mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔙 Back", callback_data="rp_a_rep"))
        return _rp_edit(call, "\n".join(L), mk)
    if d == 'rp_a_csv':
        bot.answer_callback_query(call.id, "Preparing…"); return _rp_a_export(chat)
    if d.startswith('rp_a_rst_'):
        what = d[9:]; bot.answer_callback_query(call.id)
        mk = types.InlineKeyboardMarkup()
        mk.row(types.InlineKeyboardButton("✅ Yes, reset", callback_data=f"rp_a_rstc_{what}"), types.InlineKeyboardButton("❌ Cancel", callback_data="rp_a_rep"))
        label = {'points': 'points', 'refs': 'referral records', 'log': 'points log'}.get(what, what)
        return _rp_edit(call, f"⚠️ Reset ALL {label}? This cannot be undone.", mk)
    if d.startswith('rp_a_rstc_'):
        what = d[10:]
        _db_exec({'points': "DELETE FROM user_points", 'refs': "DELETE FROM referrals", 'log': "DELETE FROM points_log"}.get(what, "SELECT 1"))
        bot.answer_callback_query(call.id, "✅ Done", show_alert=True); t, m = _rp_a_rep(); return _rp_edit(call, t, m)
    bot.answer_callback_query(call.id)


# ============================================================
# --- BUY PLANS WITH POINTS ---
# ============================================================
def _pb_plan_setting(plan_id):
    try: return int(float(get_setting(f'PB_PLAN_{plan_id}', '0') or 0))
    except Exception: return 0

def _pb_cost(uid, plan):
    """Points needed for this plan, or None when it can't be bought with points."""
    if not (_rp_on() and _lbf('PB_ON')): return None
    if is_free_plan(plan[1], plan[3]): return None
    ov = _pb_plan_setting(plan[0])
    if ov < 0: return None
    if ov > 0: return ov
    pr = calc_price(uid, plan)
    base = pr['total'] if _lbf('PB_INCL_TAX') else pr['total'] - pr['tax_amt']
    cost = int(_math.ceil(base * _lbn('PB_RATE') - 1e-9))
    return cost if cost > 0 else None

def _pb_bought_count(uid):
    return (_db_q("SELECT COUNT(*) FROM points_log WHERE user_id=? AND reason LIKE 'plan\\_%' ESCAPE '\\'", (uid,), one=True) or [0])[0]

def _pb_confirm_view(uid, plan):
    cost = _pb_cost(uid, plan); bal = int(_lb_points(uid))
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
    lim = _lbi('PB_MAX_BUYS')
    if cost is None:
        return "ℹ️ This plan can't be bought with points.", None
    L = ["⭐ <b>PAY WITH POINTS</b>", "━━━━━━━━━━━━━━━━━━",
         f"📦 Plan: <b>{_h(plan[1])}</b> · {plan[4]} days · {plan[2]} project(s)",
         f"💎 Cost: <b>{cost} points</b>", f"⭐ Your balance: <b>{bal} points</b>"]
    if lim > 0: L.append(f"🔁 Points purchases used: <b>{_pb_bought_count(uid)}/{lim}</b>")
    if bal >= cost:
        L.append(f"✅ After purchase: <b>{bal - cost} points</b> left")
        m.add(B("✅ Confirm Purchase", callback_data=f"pbuyc_{plan[0]}"))
    else:
        L.append(f"❌ You need <b>{cost - bal} more points</b>.")
        m.add(B("🔗 Earn Points", callback_data="rp_home"))
    m.add(B("🔙 Back", callback_data=f"plbuy_{plan[0]}"))
    return "\n".join(L), m

def points_buy_callback(call):
    d, uid, chat = call.data, call.from_user.id, call.message.chat.id
    confirm = d.startswith('pbuyc_')
    try: plan = get_plan_by_id(int(d.split('_')[1]))
    except Exception: plan = None
    if not plan: bot.answer_callback_query(call.id, "❌ Plan not found.", show_alert=True); return
    if not _flag('PAYMENTS_ENABLED'): bot.answer_callback_query(call.id, "⏸️ Payments are paused.", show_alert=True); return
    cost = _pb_cost(uid, plan)
    if cost is None: bot.answer_callback_query(call.id, "This plan can't be bought with points.", show_alert=True); return
    lim = _lbi('PB_MAX_BUYS')
    if lim > 0 and _pb_bought_count(uid) >= lim:
        bot.answer_callback_query(call.id, f"❌ Points purchase limit reached ({lim}).", show_alert=True); return
    if not confirm:
        bot.answer_callback_query(call.id); t, m = _pb_confirm_view(uid, plan); _rp_edit(call, t, m); return
    rc, _ = _db_exec("UPDATE user_points SET points = points - ? WHERE user_id=? AND points >= ?", (cost, uid, cost))
    if not rc: bot.answer_callback_query(call.id, f"❌ You need {cost} points.", show_alert=True); return
    try:
        _db_exec("INSERT INTO points_log (user_id, delta, reason, created_at) VALUES (?,?,?,?)",
                 (uid, -cost, 'plan_' + str(plan[1]).replace(' ', '_')[:30], datetime.now().isoformat()))
        pr = calc_price(uid, plan)
        expiry, inv = complete_purchase(uid, plan, 'Points', f"{cost} points", 0, f"pts:{cost}", pr['coupon'])
    except Exception as e:
        logger.error(f"points purchase failed: {e}", exc_info=True)
        _lb_add_points(uid, cost, 'refund')
        bot.answer_callback_query(call.id, "❌ Purchase failed — your points were refunded.", show_alert=True); return
    bot.answer_callback_query(call.id, "🎉 Plan activated!", show_alert=True)
    mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🏠 Back to Main", callback_data="back_to_main"))
    _rp_edit(call, f"🎉 <b>Purchase complete!</b>\n\n📦 {_h(plan[1])} is active until <b>{expiry:%d-%m-%Y}</b>\n"
                   f"⭐ Points left: <b>{int(_lb_points(uid))}</b>", mk)

# points are not earned for purchases made with points
_pb_orig_complete = complete_purchase
def complete_purchase(user_id, plan, method, paid_text, amount_base, ref, coupon=''):
    if method == 'Points':
        _lb_orig_hold = _lb_orig_complete
        return _lb_orig_hold(user_id, plan, method, paid_text, amount_base, ref, coupon)
    return _pb_orig_complete(user_id, plan, method, paid_text, amount_base, ref, coupon)

def _pb_plan_line(uid, plan):
    c = _pb_cost(uid, plan)
    return f"\n⭐ Or pay with <b>{c} points</b>" if c else ""


# ============================================================
# --- REDEEM CODES + RICH "MY INFO" ---
# ============================================================
import random as _rnd
import string as _strg

RC_DEF = {'RC_ON': '1', 'RC_NOTIFY': '1', 'RC_MAX_FAIL': '5'}
LB_DEF.update(RC_DEF)
RC_KINDS = {'days': '⏳ Premium Days', 'points': '⭐ Points', 'plan': '📦 Full Plan'}
_RC_FAILS = {}
_CD_DRAFT = {}

def _rc_init():
    _db_exec("""CREATE TABLE IF NOT EXISTS redeem_codes (code TEXT PRIMARY KEY, kind TEXT, amount REAL DEFAULT 0, plan_id INTEGER DEFAULT 0,
                max_uses INTEGER DEFAULT 1, used INTEGER DEFAULT 0, expires_at TEXT, active INTEGER DEFAULT 1, note TEXT DEFAULT '',
                created_at TEXT, created_by INTEGER)""")
    _db_exec("""CREATE TABLE IF NOT EXISTS redeem_log (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, user_id INTEGER, created_at TEXT,
                UNIQUE(code, user_id))""")

def _rc_norm(c): return re.sub(r'[^A-Z0-9_-]', '', str(c).upper())[:24]

def _rc_gen(prefix=''):
    alpha = ''.join(ch for ch in _strg.ascii_uppercase + _strg.digits if ch not in 'O0I1L')
    while True:
        c = (prefix + '-' if prefix else '') + ''.join(_rnd.choices(alpha, k=5)) + '-' + ''.join(_rnd.choices(alpha, k=5))
        if not _rc_get(c): return c

_RC_COLS = ('code', 'kind', 'amount', 'plan_id', 'max_uses', 'used', 'expires_at', 'active', 'note', 'created_at', 'created_by')
def _rc_get(code):
    r = _db_q("SELECT " + ",".join(_RC_COLS) + " FROM redeem_codes WHERE code=?", (code,), one=True)
    return dict(zip(_RC_COLS, r)) if r else None

def _rc_reward_text(c):
    if c['kind'] == 'days': return f"+{int(c['amount'])} day(s) of premium"
    if c['kind'] == 'points': return f"+{int(c['amount'])} points"
    p = get_plan_by_id(c['plan_id'])
    return f"{p[1]} plan ({p[4]} days)" if p else "plan (deleted!)"

def _rc_status(c):
    if not c['active']: return "⛔ Disabled"
    if c['expires_at'] and c['expires_at'] < datetime.now().isoformat(): return "⌛ Expired"
    if c['max_uses'] and c['used'] >= c['max_uses']: return "🈵 Used up"
    return "✅ Active"

def _rc_redeem(uid, name, raw):
    """-> (ok, html message)"""
    if not _lbf('RC_ON'): return False, "🎟 Redeem codes are currently disabled."
    now = time.time()
    fails = [t for t in _RC_FAILS.get(uid, []) if now - t < 3600]
    _RC_FAILS[uid] = fails
    mx = _lbi('RC_MAX_FAIL')
    if mx > 0 and len(fails) >= mx:
        return False, "⏳ <b>Too many wrong attempts.</b> Please try again in a while."
    code = _rc_norm(raw)
    c = _rc_get(code) if code else None
    if not c:
        fails.append(now); _RC_FAILS[uid] = fails
        return False, "❌ <b>Invalid code.</b> Check the spelling and try again."
    st = _rc_status(c)
    if st != "✅ Active":
        return False, {"⛔ Disabled": "⛔ This code is no longer active.", "⌛ Expired": "⌛ This code has expired.",
                       "🈵 Used up": "🈵 This code has already been used the maximum number of times."}[st]
    rc, _ = _db_exec("INSERT OR IGNORE INTO redeem_log (code, user_id, created_at) VALUES (?,?,?)", (code, uid, datetime.now().isoformat()))
    if not rc: return False, "ℹ️ You have already redeemed this code."
    rc, _ = _db_exec("UPDATE redeem_codes SET used = used + 1 WHERE code=? AND active=1 AND (max_uses=0 OR used < max_uses) "
                     "AND (expires_at IS NULL OR expires_at='' OR expires_at > ?)", (code, datetime.now().isoformat()))
    if not rc:
        _db_exec("DELETE FROM redeem_log WHERE code=? AND user_id=?", (code, uid))
        return False, "🈵 Sorry, this code just ran out."
    try:
        now_dt = datetime.now()
        if c['kind'] == 'points':
            _lb_add_points(uid, int(c['amount']), 'redeem_code')
            got = f"⭐ <b>+{int(c['amount'])} points</b> added!\nBalance: <b>{int(_lb_points(uid))}</b>"
        elif c['kind'] == 'days':
            days = int(c['amount']); cur = user_subscriptions.get(uid)
            if cur and cur['expiry'] > now_dt: expiry, pn, lim = cur['expiry'] + timedelta(days=days), cur.get('plan_name'), cur.get('file_limit')
            else: expiry, pn, lim = now_dt + timedelta(days=days), "Redeemed", SUBSCRIBED_USER_LIMIT
            save_subscription(uid, expiry, pn, lim)
            got = f"⏳ <b>+{days} day(s)</b> of premium!\nActive until <b>{expiry:%d-%m-%Y}</b>"
        else:
            plan = get_plan_by_id(c['plan_id'])
            if not plan: raise RuntimeError("plan missing")
            expiry = activate_plan(uid, plan)
            got = f"📦 <b>{_h(plan[1])}</b> plan activated until <b>{expiry:%d-%m-%Y}</b>"
    except Exception as e:
        logger.error(f"redeem apply failed: {e}", exc_info=True)
        _db_exec("UPDATE redeem_codes SET used = MAX(0, used - 1) WHERE code=?", (code,))
        _db_exec("DELETE FROM redeem_log WHERE code=? AND user_id=?", (code, uid))
        return False, "❌ Could not apply this code right now. Please contact support."
    if _lbf('RC_NOTIFY'):
        for aid in list(admin_ids)[:5]:
            try: bot.send_message(aid, f"🎟 <b>Code redeemed</b>\n<code>{_h(code)}</code> by <code>{uid}</code> ({_h(name)})\n🎁 {_h(_rc_reward_text(c))}", parse_mode='HTML')
            except Exception: pass
    return True, f"🎉 <b>Code redeemed!</b>\n━━━━━━━━━━━━━━━━━━\n{got}"

# ---------------- user side ----------------
def _rc_user_input(message):
    uid = message.from_user.id
    t = (message.text or '').strip()
    if t.lower() == '/cancel': bot.send_message(message.chat.id, "❌ Cancelled."); return
    try: bot.delete_message(message.chat.id, message.message_id)      # keep codes private
    except Exception: pass
    ok, txt = _rc_redeem(uid, message.from_user.first_name or '', t)
    mk = types.InlineKeyboardMarkup()
    if not ok and 'Invalid' in txt: mk.add(types.InlineKeyboardButton("🔁 Try Again", callback_data="redeem_start"))
    mk.add(types.InlineKeyboardButton("👤 My Info", callback_data="my_info"))
    bot.send_message(message.chat.id, txt, reply_markup=mk, parse_mode='HTML')

def redeem_user_start(call):
    if not _lbf('RC_ON'): bot.answer_callback_query(call.id, "Redeem codes are currently disabled.", show_alert=True); return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🎟 <b>Redeem Code</b>\n\nSend your code now (it will be deleted from the chat for privacy).\n\n/cancel to abort.", parse_mode='HTML')
    bot.register_next_step_handler(msg, _rc_user_input)

@bot.message_handler(commands=['redeem'])
def cmd_redeem(message):
    parts = (message.text or '').split(maxsplit=1)
    if len(parts) == 2:
        message.text = parts[1]; _rc_user_input(message)
    else:
        msg = bot.send_message(message.chat.id, "🎟 <b>Redeem Code</b>\n\nSend your code now.\n\n/cancel to abort.", parse_mode='HTML')
        bot.register_next_step_handler(msg, _rc_user_input)

# ---------------- My Info ----------------
def _dir_size(path):
    tot = 0
    try:
        for root, _d, files in os.walk(path):
            for f in files:
                try: tot += os.path.getsize(os.path.join(root, f))
                except Exception: pass
    except Exception: pass
    return tot

def _fmt_bytes(n):
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or u == 'GB': return f"{n:.0f} {u}" if u == 'B' else f"{n:.1f} {u}"
        n /= 1024

def _fmt_dt(iso):
    try: return datetime.fromisoformat(iso).strftime('%d %b %Y')
    except Exception: return '—'

def _info_text(user_id, user_name, user_username):
    file_limit = get_user_file_limit(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    now = datetime.now(); expiry_info = ""
    if user_id == OWNER_ID: rank = "👑 Owner"
    elif user_id in admin_ids: rank = _adm_rank(user_id)
    elif has_active_sub(user_id):
        exp = user_subscriptions[user_id]['expiry']; left = exp - now
        rank = f"⭐ {_lbh(get_plan_label(user_id))}"
        expiry_info = f"\n⏳ <b>Expires:</b> {exp:%d %b %Y, %H:%M}\n📅 <b>Time left:</b> <code>{left.days}d {left.seconds // 3600}h</code>"
    else:
        rank = "🆓 Free User"
        if user_id in user_subscriptions: remove_subscription_db(user_id)
    running = sum(1 for pn in [f[0] for f in user_files.get(user_id, [])] if is_bot_running(user_id, pn))
    banned = "🚫 Yes" if is_user_banned(user_id) else "✅ No"
    fn, un, jd, ls = get_profile(user_id, fetch=False)
    ok, pend = _rp_ref_counts(user_id)
    pr = (_db_q("SELECT COUNT(*), COALESCE(SUM(amount_base),0) FROM payments WHERE user_id=?", (user_id,), one=True) or (0, 0))
    codes = (_db_q("SELECT COUNT(*) FROM redeem_log WHERE user_id=?", (user_id,), one=True) or [0])[0]
    inv = _db_q("SELECT inviter FROM referrals WHERE invitee=?", (user_id,), one=True)
    prank, rrank = _lb_rank(user_id, 'points'), _lb_rank(user_id, 'refs')
    folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    size = _dir_size(folder) if os.path.isdir(folder) else 0
    exp_lines = []
    if expiry_info:
        exp = user_subscriptions[user_id]['expiry']; left = exp - now
        exp_lines = [f"⏳ Expires ▸ <b>{exp:%d %b %Y, %H:%M}</b>", f"📅 Time left ▸ <b>{left.days}d {left.seconds // 3600}h</b>"]
    who = [f"🆔 ID ▸ <code>{user_id}</code>", f"👤 Name ▸ <b>{_lbh(user_name)}</b>",
           f"✳️ Username ▸ {('@' + _lbh(user_username)) if user_username else '<i>not set</i>'}",
           f"🏅 Rank ▸ <b>{rank}</b>"] + exp_lines + [f"🛡 Banned ▸ {banned}"]
    rew = [f"💎 Points ▸ <b>{int(_lb_points(user_id))}</b>" + (f"  <i>(rank #{prank})</i>" if prank else ""),
           f"👥 Referrals ▸ <b>{ok}</b>" + (f"  <i>({pend} pending)</i>" if pend else "") + (f"  <i>(rank #{rrank})</i>" if rrank else "")]
    if _lbf('DAILY_ON'):
        done = (_db_q("SELECT last_day FROM user_daily WHERE user_id=?", (user_id,), one=True) or [''])[0] == now.strftime('%Y-%m-%d')
        rew.append(f"📅 Daily bonus ▸ {'✅ claimed today' if done else '🎁 available'}")
    rew.append(f"🎟 Codes redeemed ▸ <b>{codes}</b>")
    if inv: rew.append(f"🔗 Invited by ▸ <code>{inv[0]}</code>")
    host = [f"📁 Projects ▸ <b>{get_user_file_count(user_id)} / {limit_str}</b>", f"🟢 Running ▸ <b>{running}</b>", f"💾 Storage ▸ <b>{_fmt_bytes(size)}</b>"]
    acc = [f"🛒 Purchases ▸ <b>{pr[0]}</b>" + (f"  <i>({_h(fmt_money(pr[1]))} spent)</i>" if pr[1] else ""),
           f"📆 Joined ▸ {_fmt_dt(jd)}", f"🕒 Last seen ▸ {_fmt_dt(ls)}"]
    q = lambda lines: "<blockquote>" + "\n".join(lines) + "</blockquote>"
    return ("✦ <b>𝗠𝗬  𝗣𝗥𝗢𝗙𝗜𝗟𝗘</b> ✦\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n" + q(who) + "\n<b>◈ REWARDS</b>\n" + q(rew) +
            "\n<b>◈ HOSTING</b>\n" + q(host) + "\n<b>◈ ACCOUNT</b>\n" + q(acc))

def _info_markup():
    B = types.InlineKeyboardButton
    m = types.InlineKeyboardMarkup(row_width=2)
    m.row(B("🎟 Redeem Code", callback_data="redeem_start"), B("📜 My History", callback_data="mi_hist"))
    m.row(B("🔄 Refresh", callback_data="my_info"), B("🔙 Back to Main", callback_data="back_to_main"))
    return m

def _mi_hist(uid):
    L = ["📜 <b>MY HISTORY</b>", "━━━━━━━━━━━━━━━━━━", "<b>🛒 Purchases</b>"]
    rows = _db_q("SELECT plan_name, method, amount_base, created_at FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 6", (uid,))
    L += [f"• {_lbh(p)} · {_lbh(mt)} · {_h(fmt_money(a)) if a else 'points/free'} · <i>{ca[:10]}</i>" for p, mt, a, ca in rows] or ["<i>None yet.</i>"]
    L += ["", "<b>🎟 Redeemed codes</b>"]
    rows = _db_q("SELECT l.code, l.created_at, c.kind, c.amount FROM redeem_log l LEFT JOIN redeem_codes c ON c.code=l.code WHERE l.user_id=? ORDER BY l.id DESC LIMIT 6", (uid,))
    L += [f"• <code>{_lbh(cd)}</code> · {_lbh(RC_KINDS.get(k, ''))} {int(a) if a else ''} · <i>{ca[:10]}</i>" for cd, ca, k, a in rows] or ["<i>None yet.</i>"]
    L += ["", "<b>⭐ Recent points</b>"]
    rows = _db_q("SELECT delta, reason, created_at FROM points_log WHERE user_id=? ORDER BY id DESC LIMIT 6", (uid,))
    L += [f"• <b>{d:+g}</b> · {_lbh(r.replace('_', ' '))} · <i>{ca[:10]}</i>" for d, r, ca in rows] or ["<i>None yet.</i>"]
    return "\n".join(L)

def my_info_callback(call):
    uid = call.from_user.id
    try:
        bot.answer_callback_query(call.id)
        if call.data == 'mi_hist':
            mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔙 Back", callback_data="my_info"))
            _rp_edit(call, _mi_hist(uid), mk); return
        _rp_edit(call, _info_text(uid, call.from_user.first_name or "User", call.from_user.username), _info_markup())
    except Exception as e:
        logger.error(f"Error in my_info_callback: {e}")

def _logic_my_info_v2(message):
    uid = message.from_user.id
    bot.send_message(message.chat.id, _info_text(uid, message.from_user.first_name or "User", message.from_user.username),
                     reply_markup=_info_markup(), parse_mode='HTML')

# ---------------- admin: redeem codes ----------------
def _cd_home():
    n = (_db_q("SELECT COUNT(*), COALESCE(SUM(active),0), COALESCE(SUM(used),0) FROM redeem_codes", one=True) or (0, 0, 0))
    today = (_db_q("SELECT COUNT(*) FROM redeem_log WHERE created_at >= ?", (datetime.now().strftime('%Y-%m-%d'),), one=True) or [0])[0]
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=2)
    m.row(B("➕ Create Code", callback_data="cd_new"), B("📋 All Codes", callback_data="cd_list_0"))
    m.row(B("🔍 Find Code", callback_data="cd_find"), B("📜 Recent Redeems", callback_data="cd_log"))
    m.row(B("📤 Export CSV", callback_data="cd_csv"), B("🧹 Clean Up", callback_data="cd_clean"))
    m.row(B("⚙️ Settings", callback_data="cd_set"), B("🔙 Admin Panel", callback_data="admin_panel"))
    return (f"🎟 <b>Redeem Codes</b>\n━━━━━━━━━━━━━━━━━━\nSystem: <b>{'ON ✅' if _lbf('RC_ON') else 'OFF ❌'}</b>\n"
            f"📦 Codes: <b>{n[0]}</b> ({int(n[1])} enabled)\n✅ Total redemptions: <b>{int(n[2])}</b>\n📅 Redeemed today: <b>{today}</b>"), m

def _cd_detail(code):
    c = _rc_get(code)
    if not c: return "❌ Code not found.", None
    exp = c['expires_at'][:16].replace('T', ' ') if c['expires_at'] else "Never"
    L = [f"🎟 <b>{_h(code)}</b>", "━━━━━━━━━━━━━━━━━━", f"Status: <b>{_rc_status(c)}</b>",
         f"🎁 Reward: <b>{_h(_rc_reward_text(c))}</b>", f"🔢 Uses: <b>{c['used']}/{c['max_uses'] or '∞'}</b>",
         f"⏳ Expires: <b>{exp}</b>", f"📝 Note: {_h(c['note']) or '—'}", f"🗓 Created: {_fmt_dt(c['created_at'])} by <code>{c['created_by']}</code>",
         "", f"Redeem command: <code>/redeem {_h(code)}</code>"]
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=2)
    m.row(B("⛔ Disable" if c['active'] else "✅ Enable", callback_data=f"cd_t_{code}"), B("🗑 Delete", callback_data=f"cd_d_{code}"))
    m.row(B("➕ Add Uses", callback_data=f"cd_u_{code}"), B("⏳ Set Expiry", callback_data=f"cd_e_{code}"))
    m.row(B("📝 Note", callback_data=f"cd_n_{code}"), B("👥 Who Redeemed", callback_data=f"cd_w_{code}"))
    m.add(B("🔙 Back", callback_data="cd_list_0"))
    return "\n".join(L), m

def _cd_prompt(call, text, kind, ctx=None):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, text + "\n\n/cancel to abort.", parse_mode='HTML')
    bot.register_next_step_handler(msg, _cd_input, kind, ctx)

def _cd_create(admin, kind, amount, plan_id, code, max_uses, exp_days, note=''):
    exp = (datetime.now() + timedelta(days=exp_days)).isoformat() if exp_days > 0 else None
    rc, _ = _db_exec("INSERT OR IGNORE INTO redeem_codes (code, kind, amount, plan_id, max_uses, used, expires_at, active, note, created_at, created_by) "
                     "VALUES (?,?,?,?,?,0,?,1,?,?,?)", (code, kind, amount, plan_id, max_uses, exp, note, datetime.now().isoformat(), admin))
    return bool(rc)

def _cd_input(message, kind, ctx):
    uid = message.from_user.id
    if uid not in admin_ids: return
    t = (message.text or '').strip()
    if t.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    try:
        if kind == 'amount':
            n = int(t)
            if n <= 0 or n > 10000000: raise ValueError("Enter a positive whole number.")
            d = _CD_DRAFT.setdefault(uid, {}); d['amount'] = n
            return _cd_mode_msg(message.chat.id, uid)
        if kind == 'single':
            p = t.split()
            code = _rc_gen() if p[0].lower() == 'auto' else _rc_norm(p[0])
            if len(code) < 3: raise ValueError("Code must be at least 3 characters (A-Z, 0-9, - _).")
            mx = int(p[1]) if len(p) > 1 else 1; ed = int(p[2]) if len(p) > 2 else 0
            if mx < 0 or ed < 0 or mx > 10000000 or ed > 3650: raise ValueError("Invalid max uses / expiry days.")
            d = _CD_DRAFT.get(uid)
            if not d: raise ValueError("Session expired — start again from ➕ Create Code.")
            if not _cd_create(uid, d['kind'], d.get('amount', 0), d.get('plan_id', 0), code, mx, ed):
                raise ValueError("That code already exists.")
            txt, mk = _cd_detail(code); bot.send_message(message.chat.id, "✅ Code created.\n\n" + txt, reply_markup=mk, parse_mode='HTML'); return
        if kind == 'bulk':
            p = t.split(); cnt = int(p[0]); ed = int(p[1]) if len(p) > 1 else 0
            if cnt < 1 or cnt > 500 or ed < 0 or ed > 3650: raise ValueError("Count 1–500, expiry days 0–3650.")
            d = _CD_DRAFT.get(uid)
            if not d: raise ValueError("Session expired — start again from ➕ Create Code.")
            codes = []
            for _ in range(cnt):
                c = _rc_gen()
                if _cd_create(uid, d['kind'], d.get('amount', 0), d.get('plan_id', 0), c, 1, ed): codes.append(c)
            body = "\n".join(codes)
            if len(codes) <= 20: bot.send_message(message.chat.id, f"✅ <b>{len(codes)} single-use codes</b> ({_h(_rc_reward_text(_rc_get(codes[0])))}):\n\n<code>" + _h(body) + "</code>", parse_mode='HTML')
            else:
                import io as _io
                f = _io.BytesIO(body.encode()); f.name = "redeem_codes.txt"; bot.send_document(message.chat.id, f, caption=f"✅ {len(codes)} codes")
            return
        if kind == 'find':
            code = _rc_norm(t); txt, mk = _cd_detail(code); bot.send_message(message.chat.id, txt, reply_markup=mk, parse_mode='HTML'); return
        if kind == 'uses':
            n = int(t)
            if n < 0 or n > 10000000: raise ValueError("Enter 0 (unlimited) or a positive number.")
            _db_exec("UPDATE redeem_codes SET max_uses = CASE WHEN ?=0 THEN 0 ELSE max_uses + ? END WHERE code=?", (n, n, ctx))
        elif kind == 'exp':
            n = int(t)
            if n < 0 or n > 3650: raise ValueError("Enter days from now (0 = never expires).")
            _db_exec("UPDATE redeem_codes SET expires_at=? WHERE code=?", ((datetime.now() + timedelta(days=n)).isoformat() if n else None, ctx))
        elif kind == 'note':
            _db_exec("UPDATE redeem_codes SET note=? WHERE code=?", (t[:120], ctx))
        elif kind == 'fail':
            n = int(t)
            if n < 0 or n > 1000: raise ValueError("Enter 0–1000 (0 = unlimited).")
            set_setting('RC_MAX_FAIL', str(n)); bot.reply_to(message, "✅ Saved."); return
        txt, mk = _cd_detail(ctx); bot.send_message(message.chat.id, "✅ Updated.\n\n" + txt, reply_markup=mk, parse_mode='HTML')
    except ValueError as e:
        s = str(e); bot.reply_to(message, "❌ " + (s if s and 'invalid literal' not in s else "Invalid input."))
    except IndexError:
        bot.reply_to(message, "❌ Missing values — see the format shown.")
    except Exception as e:
        logger.warning(f"cd input failed: {e}"); bot.reply_to(message, "❌ Something went wrong.")

def _cd_mode_msg(chat_id, uid):
    d = _CD_DRAFT.get(uid, {})
    what = _rc_reward_text({'kind': d['kind'], 'amount': d.get('amount', 0), 'plan_id': d.get('plan_id', 0)})
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
    m.add(B("✏️ One custom code", callback_data="cd_single"), B("🎲 Bulk random single-use codes", callback_data="cd_bulk"))
    m.add(B("🔙 Cancel", callback_data="cd_home"))
    bot.send_message(chat_id, f"🎁 Reward: <b>{_h(what)}</b>\n\nHow do you want to create codes?", reply_markup=m, parse_mode='HTML')

def redeem_admin_callback(call):
    d, uid, chat = call.data, call.from_user.id, call.message.chat.id
    if d == 'cd_home': bot.answer_callback_query(call.id); t, m = _cd_home(); return _rp_edit(call, t, m)
    if d == 'cd_colors':
        global _STYLE_BROKEN
        _STYLE_BROKEN = False
        set_setting('BTN_COLORS', '0' if _style_enabled() else '1')
        bot.answer_callback_query(call.id, "🎨 Button colors: " + ("ON" if _style_enabled() else "OFF"))
        try: bot.edit_message_text(_admin_panel_text(), chat, call.message.message_id, reply_markup=create_admin_panel(), parse_mode='Markdown')
        except Exception: pass
        return
    if d == 'cd_stars':
        set_setting('STARS_ENABLED', '0' if _flag('STARS_ENABLED') else '1')
        bot.answer_callback_query(call.id, "⭐ Telegram Stars: " + ("ON" if _flag('STARS_ENABLED') else "OFF"))
        try: bot.edit_message_text(_admin_panel_text(), chat, call.message.message_id, reply_markup=create_admin_panel(), parse_mode='Markdown')
        except Exception: pass
        return
    if d == 'cd_new':
        bot.answer_callback_query(call.id); _CD_DRAFT[uid] = {}
        B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
        m.add(*[B(v, callback_data=f"cd_k_{k}") for k, v in RC_KINDS.items()]); m.add(B("🔙 Back", callback_data="cd_home"))
        return _rp_edit(call, "➕ <b>New Redeem Code</b>\n\nWhat should the code give?", m)
    if d.startswith('cd_k_'):
        k = d[5:]
        if k not in RC_KINDS: bot.answer_callback_query(call.id); return
        _CD_DRAFT[uid] = {'kind': k}
        if k == 'plan':
            bot.answer_callback_query(call.id)
            B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
            for p in get_all_plans():
                if not is_free_plan(p[1], p[3]): m.add(B(f"{str(p[1])[:24]} · {p[4]}d", callback_data=f"cd_p_{p[0]}"))
            m.add(B("🔙 Back", callback_data="cd_new"))
            return _rp_edit(call, "📦 Pick the plan this code activates:", m)
        return _cd_prompt(call, "🔢 Send the amount of " + ("<b>premium days</b>" if k == 'days' else "<b>points</b>") + " (whole number).", 'amount')
    if d.startswith('cd_p_'):
        _CD_DRAFT.setdefault(uid, {'kind': 'plan'}).update({'kind': 'plan', 'plan_id': int(d[5:])}); bot.answer_callback_query(call.id)
        return _cd_mode_msg(chat, uid)
    if d == 'cd_single':
        return _cd_prompt(call, "✏️ Send: <code>CODE MAX_USES EXPIRY_DAYS</code>\n• CODE may be <code>auto</code>\n• MAX_USES 0 = unlimited (default 1)\n• EXPIRY_DAYS 0 = never (default 0)\n\ne.g. <code>WELCOME50 100 7</code>", 'single')
    if d == 'cd_bulk':
        return _cd_prompt(call, "🎲 Send: <code>COUNT EXPIRY_DAYS</code>\ne.g. <code>20 30</code> (20 single-use codes, valid 30 days; expiry optional)", 'bulk')
    if d == 'cd_find': return _cd_prompt(call, "🔍 Send the code to look up.", 'find')
    if d.startswith('cd_list_'):
        pg = int(d[8:]); per = 8
        rows = _db_q("SELECT code FROM redeem_codes ORDER BY created_at DESC LIMIT ? OFFSET ?", (per, pg * per))
        total = (_db_q("SELECT COUNT(*) FROM redeem_codes", one=True) or [0])[0]
        B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
        for (cd,) in rows:
            c = _rc_get(cd); m.add(B(f"{_rc_status(c).split()[0]} {cd} · {c['used']}/{c['max_uses'] or '∞'}", callback_data=f"cd_v_{cd}"))
        nav = []
        if pg > 0: nav.append(B("⬅️ Prev", callback_data=f"cd_list_{pg - 1}"))
        if (pg + 1) * per < total: nav.append(B("Next ➡️", callback_data=f"cd_list_{pg + 1}"))
        if nav: m.row(*nav)
        m.add(B("🔙 Back", callback_data="cd_home")); bot.answer_callback_query(call.id)
        return _rp_edit(call, f"📋 <b>All Codes</b> ({total})\n✅ active · ⛔ off · ⌛ expired · 🈵 used up" + ("" if rows else "\n\n<i>No codes yet.</i>"), m)
    if d.startswith('cd_v_'): bot.answer_callback_query(call.id); t, m = _cd_detail(d[5:]); return _rp_edit(call, t, m)
    if d.startswith('cd_t_'):
        _db_exec("UPDATE redeem_codes SET active = 1 - active WHERE code=?", (d[5:],)); bot.answer_callback_query(call.id, "Updated")
        t, m = _cd_detail(d[5:]); return _rp_edit(call, t, m)
    if d.startswith('cd_d_'):
        bot.answer_callback_query(call.id); B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup()
        m.row(B("✅ Delete", callback_data=f"cd_dc_{d[5:]}"), B("❌ Cancel", callback_data=f"cd_v_{d[5:]}"))
        return _rp_edit(call, f"⚠️ Delete code <code>{_h(d[5:])}</code>? Users who already redeemed keep their reward.", m)
    if d.startswith('cd_dc_'):
        _db_exec("DELETE FROM redeem_codes WHERE code=?", (d[6:],)); bot.answer_callback_query(call.id, "Deleted")
        call.data = 'cd_list_0'; return redeem_admin_callback(call)
    if d.startswith('cd_u_'): return _cd_prompt(call, "➕ How many MORE uses should this code get? (<code>0</code> = make unlimited)", 'uses', d[5:])
    if d.startswith('cd_e_'): return _cd_prompt(call, "⏳ Expires in how many days from now? (<code>0</code> = never)", 'exp', d[5:])
    if d.startswith('cd_n_'): return _cd_prompt(call, "📝 Send a note for this code (max 120 chars).", 'note', d[5:])
    if d.startswith('cd_w_'):
        bot.answer_callback_query(call.id)
        rows = _db_q("SELECT user_id, created_at FROM redeem_log WHERE code=? ORDER BY id DESC LIMIT 25", (d[5:],))
        L = [f"👥 <b>Redeemed <code>{_h(d[5:])}</code></b>", "━━━━━━━━━━━━━━━━━━"] + \
            [f"• <code>{u}</code> {_lbh(_lb_name(u))} · <i>{ca[:16].replace('T', ' ')}</i>" for u, ca in rows]
        if not rows: L.append("<i>Nobody yet.</i>")
        mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"cd_v_{d[5:]}"))
        return _rp_edit(call, "\n".join(L), mk)
    if d == 'cd_log':
        bot.answer_callback_query(call.id)
        rows = _db_q("SELECT l.code, l.user_id, l.created_at FROM redeem_log l ORDER BY l.id DESC LIMIT 20")
        L = ["📜 <b>Recent Redemptions</b>", "━━━━━━━━━━━━━━━━━━"] + [f"• <code>{_h(c)}</code> · <code>{u}</code> · <i>{ca[5:16].replace('T', ' ')}</i>" for c, u, ca in rows]
        if not rows: L.append("<i>None yet.</i>")
        mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔙 Back", callback_data="cd_home"))
        return _rp_edit(call, "\n".join(L), mk)
    if d == 'cd_csv':
        bot.answer_callback_query(call.id, "Preparing…")
        import io as _io
        for name, hdr, rows in (("codes", ['code', 'reward', 'status', 'used', 'max_uses', 'expires_at', 'note', 'created_at'],
                                 [[c['code'], _rc_reward_text(c), _rc_status(c), c['used'], c['max_uses'], c['expires_at'] or '', c['note'], c['created_at']]
                                  for (cd,) in _db_q("SELECT code FROM redeem_codes") for c in [_rc_get(cd)]]),
                                ("redemptions", ['code', 'user_id', 'created_at'], [list(r) for r in _db_q("SELECT code, user_id, created_at FROM redeem_log ORDER BY id")])):
            buf = _io.StringIO(); w = _csv.writer(buf); w.writerow(hdr); w.writerows(rows)
            f = _io.BytesIO(buf.getvalue().encode('utf-8-sig')); f.name = f"redeem_{name}_{datetime.now():%Y%m%d}.csv"
            bot.send_document(chat, f, caption=f"📤 {len(rows)} {name}")
        return
    if d == 'cd_clean':
        bot.answer_callback_query(call.id); B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup()
        m.row(B("✅ Delete", callback_data="cd_cleanc"), B("❌ Cancel", callback_data="cd_home"))
        return _rp_edit(call, "🧹 Delete all <b>expired</b>, <b>used-up</b> and <b>disabled</b> codes?", m)
    if d == 'cd_cleanc':
        now = datetime.now().isoformat()
        rc, _ = _db_exec("DELETE FROM redeem_codes WHERE active=0 OR (expires_at IS NOT NULL AND expires_at <> '' AND expires_at < ?) OR (max_uses > 0 AND used >= max_uses)", (now,))
        bot.answer_callback_query(call.id, f"Deleted {rc} code(s)", show_alert=True); t, m = _cd_home(); return _rp_edit(call, t, m)
    if d in ('cd_set', 'cd_tg_RC_ON', 'cd_tg_RC_NOTIFY'):
        if d.startswith('cd_tg_'): k = d[6:]; set_setting(k, '0' if _lbf(k) else '1')
        bot.answer_callback_query(call.id); B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
        m.add(B(f"{'✅' if _lbf('RC_ON') else '❌'} Redeem system", callback_data="cd_tg_RC_ON"),
              B(f"{'✅' if _lbf('RC_NOTIFY') else '❌'} Notify admins on redeem", callback_data="cd_tg_RC_NOTIFY"),
              B(f"✏️ Max wrong attempts/hour: {_lbi('RC_MAX_FAIL')}", callback_data="cd_fail"), B("🔙 Back", callback_data="cd_home"))
        return _rp_edit(call, "⚙️ <b>Redeem Settings</b>\n━━━━━━━━━━━━━━━━━━\nLimit wrong attempts to stop code guessing.", m)
    if d == 'cd_fail': return _cd_prompt(call, "✏️ Max wrong attempts per user per hour (<code>0</code> = unlimited).", 'fail')
    bot.answer_callback_query(call.id)


# ============================================================
# --- BUTTON COLOR MANAGER (admin) ---
# ============================================================
BK_CATS = {   # key: (label, default color)
    'nav':  ("🔙 Back / Navigation", 'primary'),
    'info': ("📊 Info & Tools", 'primary'),
    'good': ("🟢 Actions (buy, start, upload)", 'success'),
    'bad':  ("🔴 Danger (delete, stop, lock)", 'danger'),
    'ton':  ("✅ ON switches / Confirm", 'success'),
    'toff': ("❌ OFF switches / Cancel", 'danger'),
    'other': ("🔘 All other buttons", 'primary'),
}
BK_COLORS = {'primary': '🔵 Blue', 'success': '🟢 Green', 'danger': '🔴 Red', 'none': '⚪ None'}
BK_PRESETS = {
    'default': ("🌈 Default (blue / green / red)", None),
    'blue': ("🔵 All Blue", 'primary'), 'green': ("🟢 All Green", 'success'),
    'red': ("🔴 All Red", 'danger'), 'none': ("⚪ No colors (grey)", 'none'),
}
_BK_CACHE = {}

def _bk_cfg():
    c = _BK_CACHE.get('v')
    if c is None:
        try:
            cats = {}
            for k, (_l, dflt) in BK_CATS.items():
                v = str(get_setting('BC_' + k.upper(), '') or '')
                cats[k] = v if v in BK_COLORS else dflt
            try: rules = [(str(a).lower(), b) for a, b in json.loads(get_setting('BC_RULES', '') or '[]') if b in BK_COLORS]
            except Exception: rules = []
            c = {'on': str(get_setting('BTN_COLORS', '1')) != '0', 'cats': cats, 'rules': rules}
        except Exception:
            c = {'on': True, 'cats': {k: v[1] for k, v in BK_CATS.items()}, 'rules': []}
        _BK_CACHE['v'] = c
    return c

def _bk_clear(): _BK_CACHE.clear()

def _bk_style_cat(t):
    if t.startswith('✅'): return 'ton'
    if t.startswith('❌'): return 'toff'
    if any(k in t for k in _ST_NONE): return 'nav'
    if any(k in t for k in _ST_PRIMARY_FIRST): return 'info'
    if t.startswith('unlock') or '🔓' in t: return 'good'
    if any(k in t for k in _ST_DANGER): return 'bad'
    if any(k in t for k in _ST_SUCCESS): return 'good'
    if any(k in t for k in _ST_PRIMARY): return 'info'
    return 'other'

def _style_enabled():
    if _STYLE_BROKEN: return False
    return _bk_cfg()['on']

def _auto_style(text, cb=None):
    cfg = _bk_cfg(); t = (text or '').lower()
    for kw, col in cfg['rules']:
        if kw and kw in t: return None if col == 'none' else col
    cat = _bk_style_cat(t)
    if not cat: return None
    col = cfg['cats'].get(cat)
    return None if col in (None, 'none') else col

def _bk_home():
    cfg = _bk_cfg()
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
    m.add(B(f"🎨 Button Colors: {'ON ✅' if cfg['on'] else 'OFF ❌'}", callback_data="bk_on"))
    for k, (lab, _d) in BK_CATS.items():
        m.add(B(f"{lab}: {BK_COLORS[cfg['cats'][k]]}", callback_data=f"bk_c_{k}"))
    m.row(B(f"🔤 Keyword Rules ({len(cfg['rules'])})", callback_data="bk_rules"), B("🌈 Presets", callback_data="bk_pre"))
    m.row(B("👁 Preview", callback_data="bk_prev"), B("🎛 Main Menu Buttons", callback_data="bc_home"))
    m.row(B("🔄 Apply to my keyboard", callback_data="bk_apply"), B("📣 Push to all users", callback_data="bk_push"))
    m.row(B("♻️ Reset All", callback_data="bk_reset"), B("🔙 Admin Panel", callback_data="admin_panel"))
    txt = ("🎨 <b>Button Colors</b>\n━━━━━━━━━━━━━━━━━━\n"
           f"Colors: <b>{'ON ✅' if cfg['on'] else 'OFF ❌ — all buttons are plain grey for everyone'}</b>\n\n"
           "Tap a group to change its color (🔵 → 🟢 → 🔴 → ⚪). Use <b>Keyword Rules</b> to color any button whose label contains a word, "
           "and <b>Main Menu Buttons</b> to color each main-menu button.\n\n"
           "<i>Menu (bottom) keyboards refresh when you push them to users; inline buttons update instantly.</i>")
    return txt, m

def _bk_toggle_master(call, where='bk'):
    global _STYLE_BROKEN
    _STYLE_BROKEN = False
    set_setting('BTN_COLORS', '0' if _bk_cfg()['on'] else '1'); _bk_clear()
    on = _bk_cfg()['on']
    bot.answer_callback_query(call.id, "🎨 Colors " + ("ON for everyone" if on else "OFF for everyone (admin + users)"))
    try:
        if where == 'ap':
            bot.edit_message_text(_admin_panel_text(), call.message.chat.id, call.message.message_id,
                                  reply_markup=create_admin_panel(), parse_mode='Markdown')
        elif where == 'bc':
            _send_or_edit(call.message.chat.id, _bc_list_text(), _bc_list_markup(), call.message.message_id)
        else:
            t, m = _bk_home(); _rp_edit(call, t, m)
    except Exception as e:
        logger.debug(f"toggle refresh: {e}")
    _bc_push_all(call.message.chat.id)       # refresh every user's bottom menu so it turns on/off immediately

def _bk_rule_input(message):
    if message.from_user.id not in admin_ids: return
    t = (message.text or '').strip()
    if t.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    p = t.rsplit(None, 1)
    names = {'blue': 'primary', 'primary': 'primary', 'green': 'success', 'success': 'success', 'red': 'danger', 'danger': 'danger', 'none': 'none', 'grey': 'none', 'gray': 'none'}
    if len(p) != 2 or p[1].lower() not in names or not p[0].strip():
        bot.reply_to(message, "❌ Format: <code>KEYWORD COLOR</code> — e.g. <code>plans green</code>", parse_mode='HTML'); return
    try: rules = json.loads(get_setting('BC_RULES', '') or '[]')
    except Exception: rules = []
    kw = p[0].strip().lower()[:30]
    rules = [r for r in rules if r[0] != kw]
    if len(rules) >= 30: bot.reply_to(message, "❌ Max 30 rules. Delete one first."); return
    rules.append([kw, names[p[1].lower()]]); set_setting('BC_RULES', json.dumps(rules, ensure_ascii=False)); _bk_clear()
    bot.reply_to(message, f"✅ Any button containing <b>{_h(kw)}</b> is now {BK_COLORS[names[p[1].lower()]]}.", parse_mode='HTML')

def button_color_callback(call):
    d, chat = call.data, call.message.chat.id
    if d == 'bk_home': bot.answer_callback_query(call.id); t, m = _bk_home(); return _rp_edit(call, t, m)
    if d == 'bk_on': return _bk_toggle_master(call, 'bk')
    if d.startswith('bk_t_'): return _bk_toggle_master(call, d[5:])
    if d.startswith('bk_c_'):
        k = d[5:]
        if k in BK_CATS:
            cyc = ['primary', 'success', 'danger', 'none']; cur = _bk_cfg()['cats'][k]
            set_setting('BC_' + k.upper(), cyc[(cyc.index(cur) + 1) % 4]); _bk_clear()
        bot.answer_callback_query(call.id); t, m = _bk_home(); return _rp_edit(call, t, m)
    if d == 'bk_rules':
        bot.answer_callback_query(call.id)
        try: rules = json.loads(get_setting('BC_RULES', '') or '[]')
        except Exception: rules = []
        B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
        for i, (kw, col) in enumerate(rules): m.add(B(f"🗑 “{kw}” → {BK_COLORS.get(col, col)}", callback_data=f"bk_rd_{i}"))
        m.add(B("➕ Add Rule", callback_data="bk_ra"), B("🔙 Back", callback_data="bk_home"))
        return _rp_edit(call, "🔤 <b>Keyword Rules</b>\n━━━━━━━━━━━━━━━━━━\nAny button (menu or inline) whose label contains the keyword gets that color. Rules beat the group colors.\nTap a rule to delete it.", m)
    if d == 'bk_ra':
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat, "➕ Send: <code>KEYWORD COLOR</code>\nColors: <code>blue</code> · <code>green</code> · <code>red</code> · <code>none</code>\ne.g. <code>plans green</code> or <code>live logs red</code>\n\n/cancel to abort.", parse_mode='HTML')
        bot.register_next_step_handler(msg, _bk_rule_input); return
    if d.startswith('bk_rd_'):
        try: rules = json.loads(get_setting('BC_RULES', '') or '[]'); rules.pop(int(d[6:]))
        except Exception: rules = None
        if rules is not None: set_setting('BC_RULES', json.dumps(rules, ensure_ascii=False)); _bk_clear()
        call.data = 'bk_rules'; bot.answer_callback_query(call.id, "Deleted"); return button_color_callback(call)
    if d == 'bk_pre':
        bot.answer_callback_query(call.id)
        B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
        for k, (lab, _c) in BK_PRESETS.items(): m.add(B(lab, callback_data=f"bk_p_{k}"))
        m.add(B("🔙 Back", callback_data="bk_home"))
        return _rp_edit(call, "🌈 <b>Presets</b>\nPick one to set every group at once (keyword rules are cleared).", m)
    if d.startswith('bk_p_'):
        k = d[5:]
        if k in BK_PRESETS:
            col = BK_PRESETS[k][1]
            for ck, (_l, dflt) in BK_CATS.items(): set_setting('BC_' + ck.upper(), dflt if col is None else col)
            set_setting('BC_RULES', '[]'); _bk_clear()
        bot.answer_callback_query(call.id, "Preset applied"); t, m = _bk_home(); return _rp_edit(call, t, m)
    if d == 'bk_prev':
        bot.answer_callback_query(call.id)
        mk = types.InlineKeyboardMarkup(row_width=2); btns = []
        for lab, st in (("🔵 Blue", 'primary'), ("🟢 Green", 'success'), ("🔴 Red", 'danger'), ("⚪ Plain", 'none')):
            b = types.InlineKeyboardButton(lab, callback_data="bk_noop"); b.style = st; btns.append(b)
        mk.add(*btns)
        for k, (lab, _d) in BK_CATS.items(): mk.add(types.InlineKeyboardButton(lab.split(' ', 1)[1], callback_data="bk_noop"))
        bot.send_message(chat, "👁 <b>Preview</b> — " + ("these are your current colors:" if _style_enabled() else "colors are OFF, so everything is grey."), reply_markup=mk, parse_mode='HTML'); return
    if d == 'bk_noop': bot.answer_callback_query(call.id, "Just a preview 🙂"); return
    if d == 'bk_apply':
        bot.answer_callback_query(call.id, "Keyboard refreshed")
        bot.send_message(chat, "🔄 Keyboard refreshed.", reply_markup=_btn_build_keyboard(call.from_user.id)); return
    if d == 'bk_push':
        bot.answer_callback_query(call.id); m = types.InlineKeyboardMarkup()
        m.row(types.InlineKeyboardButton("✅ Yes, push", callback_data="bk_push_yes"), types.InlineKeyboardButton("❌ Cancel", callback_data="bk_home"))
        return _rp_edit(call, f"📣 Send the updated menu to <b>{len(active_users)}</b> users now?", m)
    if d == 'bk_push_yes': bot.answer_callback_query(call.id, "Sending…"); _bc_push_all(chat); return
    if d == 'bk_reset':
        bot.answer_callback_query(call.id); m = types.InlineKeyboardMarkup()
        m.row(types.InlineKeyboardButton("✅ Yes, reset", callback_data="bk_resetc"), types.InlineKeyboardButton("❌ Cancel", callback_data="bk_home"))
        return _rp_edit(call, "♻️ Reset all color groups, keyword rules and main-menu button colors to default?", m)
    if d == 'bk_resetc':
        for ck in BK_CATS: set_setting('BC_' + ck.upper(), '')
        set_setting('BC_RULES', '[]'); set_setting('BTN_COLORS', '1')
        cfg = _btn_cfg()
        for v in cfg['btn'].values(): v.pop('color', None)
        for v in cfg['custom'].values(): v.pop('color', None)
        _btn_save(); _bk_clear(); bot.answer_callback_query(call.id, "Reset"); t, m = _bk_home(); return _rp_edit(call, t, m)
    bot.answer_callback_query(call.id)

BTN_LOGIC = {
    'updates': _logic_updates_channel, 'upload': _logic_upload_file, 'check': _logic_check_files,
    'speed': _logic_bot_speed, 'stats': _logic_statistics, 'manual': _logic_manual_install,
    'plans': _logic_view_plans, 'livelogs': _logic_live_logs, 'admin': _logic_admin_panel,
    'myinfo': _logic_my_info, 'leaderboard': _logic_leaderboard, 'refer': _logic_refer, 'contact': _logic_contact_owner,
}


@bot.message_handler(commands=['updateschannel'])
def cmd_updates_channel(message): _logic_updates_channel(message)
@bot.message_handler(commands=['uploadfile'])
def cmd_upload_file(message): _logic_upload_file(message)
@bot.message_handler(commands=['checkfiles'])
def cmd_check_files(message): _logic_check_files(message)
@bot.message_handler(commands=['livelogs'])
def cmd_live_logs(message): _logic_live_logs(message)
@bot.message_handler(commands=['plans'])
def cmd_plans(message):
    if check_force_join(message): _logic_view_plans(message)
@bot.message_handler(commands=['botspeed'])
def cmd_bot_speed(message): _logic_bot_speed(message)
@bot.message_handler(commands=['contactowner'])
def cmd_contact_owner(message): _logic_contact_owner(message)
@bot.message_handler(commands=['subscriptions'])
def cmd_subscriptions(message): _logic_subscriptions_panel(message)
@bot.message_handler(commands=['statistics'])
def cmd_statistics(message): _logic_statistics(message)
@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(message): _logic_broadcast_init(message)
@bot.message_handler(commands=['lockbot'])
def cmd_lock_bot(message): _logic_toggle_lock_bot(message)
@bot.message_handler(commands=['adminpanel'])
def cmd_admin_panel(message): _logic_admin_panel(message)
@bot.message_handler(commands=['runallcode'])
def cmd_run_all(message): _logic_run_all_scripts(message)
@bot.message_handler(commands=['usermanagement'])
def cmd_user_management(message): _logic_user_management(message)
@bot.message_handler(commands=['manualinstall'])
def cmd_manual_install(message): _logic_manual_install(message)
@bot.message_handler(commands=['myinfo'])
def cmd_my_info(message): _logic_my_info(message)
@bot.message_handler(commands=['channeladd'])
def cmd_channel_add(message): _logic_channel_add(message)

# ============================================================
# --- Document Handler ---
# ============================================================
# ============================================================
# --- Upload animation ---
# ============================================================
import html as _html_up
_UP_SPIN = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
_UP_STAGES = ["Connecting to Telegram", "Receiving your file", "Verifying data", "Almost there"]

def _up_bar(pct, width=12):
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)

def _up_size(n):
    n = float(n or 0)
    return f"{n/1024:.1f} KB" if n < 1024*1024 else f"{n/1024/1024:.2f} MB"

def _upload_frame(file_name, size, pct, tick):
    stage = _UP_STAGES[min(len(_UP_STAGES)-1, int(pct // 26))]
    return (
        "╭─── 📤 <b>FILE UPLOAD</b> ───╮\n\n"
        f"📄 <code>{_html_up.escape(file_name)}</code>\n"
        f"📦 Size: <b>{_up_size(size)}</b>\n\n"
        f"{_UP_SPIN[tick % len(_UP_SPIN)]} <i>{stage}...</i>\n"
        f"<code>[{_up_bar(pct)}]</code> <b>{int(pct)}%</b>\n\n"
        "╰──────────────────╯")

def _track_upload_msg(user_id, chat_id, msg_id):
    st = pending_file_uploads.get(user_id)
    if st is not None and msg_id:
        st.setdefault('cleanup', []).append((chat_id, msg_id))

def _cleanup_upload_msgs(state):
    """Delete the upload progress card, the name prompts and the user's replies."""
    for chat_id, msg_id in (state or {}).get('cleanup', []):
        try: bot.delete_message(chat_id, msg_id)
        except Exception: pass

def _upload_animator(chat_id, msg_id, file_name, size, stop_ev, state=None):
    """Animates a progress bar until the download finishes (caps at 95%)."""
    tick, pct = 0, 0.0
    while not stop_ev.wait(0.9):
        tick += 1
        pct = min(95.0, pct + max(2.0, (95.0 - pct) * 0.22))
        if state is not None: state['pct'] = pct; state['tick'] = tick
        try:
            bot.edit_message_text(_upload_frame(file_name, size, pct, tick), chat_id, msg_id, parse_mode='HTML')
        except Exception as e:
            if 'Too Many Requests' in str(e): time.sleep(3)

def _upload_run_to_100_and_delete(chat_id, msg_id, file_name, real_size, state):
    """Play the remaining progress up to 100%, show 'complete', then delete the card."""
    pct = float(state.get('pct', 0)); tick = int(state.get('tick', 0))
    steps = 5
    for i in range(1, steps + 1):
        pct_i = pct + (100 - pct) * i / steps
        tick += 1
        try:
            bot.edit_message_text(_upload_frame(file_name, real_size, min(pct_i, 99), tick), chat_id, msg_id, parse_mode='HTML')
        except Exception: pass
        time.sleep(0.45)
    _upload_finish(chat_id, msg_id, file_name, real_size)
    time.sleep(1.2)
    try: bot.delete_message(chat_id, msg_id)
    except Exception: pass

def _upload_finish(chat_id, msg_id, file_name, real_size):
    try:
        bot.edit_message_text(
            "╭─── ✅ <b>UPLOAD COMPLETE</b> ───╮\n\n"
            f"📄 <code>{_html_up.escape(file_name)}</code>\n"
            f"📦 Size: <b>{_up_size(real_size)}</b>\n\n"
            f"<code>[{_up_bar(100)}]</code> <b>100%</b>\n\n"
            "✨ <i>Now let's set up your project...</i>\n\n"
            "╰────────────────────╯", chat_id, msg_id, parse_mode='HTML')
    except Exception: pass

@bot.message_handler(content_types=['document'])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    touch_user(message.from_user)
    chat_id = message.chat.id
    doc = message.document
    logger.info(f"Doc from {user_id}: {doc.file_name} ({doc.mime_type}), Size: {doc.file_size}")

    if is_user_banned(user_id):
        bot.reply_to(message, M('banned'))
        return
    if not check_force_join(message):
        return
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked, cannot accept files.")
        return
    if user_id not in active_users:
        bot.reply_to(message, "👋 Please run /start first to register, then upload your file.")
        return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.reply_to(message, f"⚠️ Project limit (`{current_files}/{limit_str}`) reached. Delete a project or upgrade your plan.",
                     parse_mode='Markdown', reply_markup=_limit_reached_markup())
        return

    file_name = doc.file_name
    if not file_name: bot.reply_to(message, "⚠️ No file name."); return
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, M('upload_bad_type'))
        return
    if not _ap_upload_gate(message, file_ext, doc.file_size): return
    max_file_size = get_max_upload_bytes()
    if doc.file_size > max_file_size:
        bot.reply_to(message, M('upload_too_big', max=max_file_size // 1048576)); return

    try:
        try:
            bot.forward_message(OWNER_ID, chat_id, message.message_id)
            bot.send_message(OWNER_ID, M('owner_file_note', file=file_name, user=user_id))
        except Exception as e: logger.error(f"Failed to forward to OWNER: {e}")

        download_wait_msg = bot.reply_to(message, _upload_frame(file_name, doc.file_size, 0, 0), parse_mode='HTML')
        stop_anim = threading.Event()
        anim_state = {}
        anim = threading.Thread(target=_upload_animator, args=(chat_id, download_wait_msg.message_id, file_name, doc.file_size, stop_anim, anim_state), daemon=True)
        anim.start()
        try:
            file_info_tg = bot.get_file(doc.file_id)
            downloaded_file_content = bot.download_file(file_info_tg.file_path)
        finally:
            stop_anim.set(); anim.join(timeout=5)
        _upload_run_to_100_and_delete(chat_id, download_wait_msg.message_id, file_name, len(downloaded_file_content), anim_state)

        pending_file_uploads[user_id] = {
            'file_content': downloaded_file_content,
            'file_name': file_name,
            'file_ext': file_ext,
            'project_name': None,
        }
        _ask_bot_username(chat_id, user_id)

    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"Telegram API Error for {user_id}: {e}")
        if "file is too big" in str(e).lower():
            bot.reply_to(message, "❌ File too large to download (~20MB limit).")
        else:
            bot.reply_to(message, f"❌ Telegram API Error: {str(e)}.")
    except Exception as e:
        logger.error(f"❌ General error for {user_id}: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Unexpected error: {str(e)}")

def process_upload_project_name(message):
    """Step 1: User provides the project name."""
    user_id = message.from_user.id
    if message.text and message.text.strip().lower() == '/cancel':
        _cleanup_upload_msgs(pending_file_uploads.pop(user_id, None))
        bot.reply_to(message, "❌ Upload cancelled.")
        return
    if user_id not in pending_file_uploads:
        bot.reply_to(message, "⚠️ No pending upload found. Please send your file again.")
        return
    _track_upload_msg(user_id, message.chat.id, message.message_id)   # user's typed project name

    raw_name = (message.text or '').strip()
    project_name = re.sub(r'[^\w\-]', '_', raw_name)[:_ap_namelen()]
    if not project_name:
        msg = bot.reply_to(message, "⚠️ Invalid name. Use letters, numbers, dashes, or underscores.\nTry again or /cancel.")
        _track_upload_msg(user_id, message.chat.id, msg.message_id)
        bot.register_next_step_handler(msg, process_upload_project_name)
        return

    existing_projects = [pn for pn, _, _ in user_files.get(user_id, [])]
    if project_name in existing_projects:
        msg = bot.reply_to(message, f"⚠️ You already have a project named `{project_name}`.\nChoose a different name or /cancel.", parse_mode='Markdown')
        _track_upload_msg(user_id, message.chat.id, msg.message_id)
        bot.register_next_step_handler(msg, process_upload_project_name)
        return

    pending_file_uploads[user_id]['project_name'] = project_name
    file_ext = pending_file_uploads[user_id]['file_ext']
    # project name accepted -> delete the prompt, the typed name and any error replies right away
    _cleanup_upload_msgs(pending_file_uploads[user_id])
    pending_file_uploads[user_id]['cleanup'] = []

    if file_ext == '.zip':
        msg = bot.send_message(
            message.chat.id,
            f"✅ Project name set to `{project_name}`.\n\n"
            "📁 *Step 2 of 2 — Main File*\n\n"
            "Send the main script filename to run:\n"
            "• Python: `bot.py`, `main.py`, `app.py`…\n"
            "• Node.js: `index.js`, `bot.js`…\n\n"
            "Type /skip to auto-detect, or /cancel to abort.",
            parse_mode='Markdown'
        )
        _track_upload_msg(user_id, message.chat.id, msg.message_id)
        bot.register_next_step_handler(msg, process_upload_main_file)
    else:
        pending_file_uploads[user_id]['main_file'] = pending_file_uploads[user_id]['file_name']
        _finalize_upload(message, user_id)

def process_upload_main_file(message):
    """Step 2: User provides the main file name (ZIP uploads only)."""
    user_id = message.from_user.id
    text = (message.text or '').strip()
    if text.lower() == '/cancel':
        _cleanup_upload_msgs(pending_file_uploads.pop(user_id, None))
        bot.reply_to(message, "❌ Upload cancelled.")
        return
    if user_id not in pending_file_uploads:
        bot.reply_to(message, "⚠️ No pending upload found. Please send your file again.")
        return
    _track_upload_msg(user_id, message.chat.id, message.message_id)

    if text.lower() == '/skip':
        pending_file_uploads[user_id]['main_file'] = None
        _m = bot.reply_to(message, "⏭️ Skipped — main file will be auto-detected from the archive.")
        _track_upload_msg(user_id, message.chat.id, _m.message_id)
    else:
        main_file = text
        if not (main_file.endswith('.py') or main_file.endswith('.js')):
            msg = bot.reply_to(message, "⚠️ Main file must end in `.py` or `.js`.\nTry again, /skip to auto-detect, or /cancel.", parse_mode='Markdown')
            _track_upload_msg(user_id, message.chat.id, msg.message_id)
            bot.register_next_step_handler(msg, process_upload_main_file)
            return
        pending_file_uploads[user_id]['main_file'] = main_file
        _m = bot.reply_to(message, f"✅ Main file set to `{main_file}`.", parse_mode='Markdown')
        _track_upload_msg(user_id, message.chat.id, _m.message_id)

    _finalize_upload(message, user_id)

def _finalize_upload(message, user_id):
    """Process the saved file now that we have project_name and main_file."""
    chat_id = message.chat.id
    if user_id not in pending_file_uploads:
        bot.send_message(chat_id, "⚠️ Upload state lost. Please send the file again.")
        return

    state = pending_file_uploads.pop(user_id)
    _cleanup_upload_msgs(state)   # remove progress card, name prompts and replies
    try: _db_exec("INSERT OR REPLACE INTO project_meta (user_id, project_name, bot_username, uploaded_at) VALUES (?,?,?,?)", (user_id, state['project_name'], state.get('bot_username', ''), datetime.now().isoformat()))
    except Exception as _me: logger.warning(f"project_meta save failed: {_me}")
    file_content = state['file_content']
    file_name = state['file_name']
    file_ext = state['file_ext']
    project_name = state['project_name']
    main_file = state.get('main_file')

    project_folder = get_user_folder(user_id, project_name)

    if file_ext == '.zip':
        threading.Thread(
            target=_queue_zip_for_approval,
            args=(file_content, file_name, user_id, project_name, main_file, message)
        ).start()
    else:
        file_path = os.path.join(project_folder, file_name)
        with open(file_path, 'wb') as f: f.write(file_content)
        is_safe, security_msg = check_code_security(file_path, file_ext.lstrip('.'))

        if user_id not in pending_script_files: pending_script_files[user_id] = {}
        pending_script_files[user_id][project_name] = {
            'path': file_path, 'type': file_ext.lstrip('.'),
            'is_safe': is_safe, 'security_msg': security_msg,
            'chat_id': chat_id, 'project_name': project_name,
            'main_file': file_name,
        }
        save_pending_script_db(user_id, project_name, pending_script_files[user_id][project_name])
        if _should_auto_approve(is_safe, user_id):
            if _approve_file_core(user_id, project_name, message):
                _notify_auto_approved(user_id, project_name, 'file'); return
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_file_{user_id}_{project_name}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_file_{user_id}_{project_name}")
        )
        markup.row(types.InlineKeyboardButton("📋 View in Pending Files", callback_data=f"pending_user_{user_id}"))
        if not is_safe:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as _fscan:
                    _content = _fscan.read()
                found_patterns = [p for p in DANGEROUS_PATTERNS if re.search(p, _content, re.IGNORECASE)]
                pattern_lines = '\n'.join(f"  ⚠️ `{p}`" for p in found_patterns[:10])
                if len(found_patterns) > 10:
                    pattern_lines += f"\n  ... and `{len(found_patterns) - 10}` more"
                danger_detail = f"🚨 *Dangerous Patterns Found:* `{len(found_patterns)}`\n{pattern_lines}"
            except Exception:
                danger_detail = f"🚨 *Security Issue:* `{security_msg}`"
        else:
            danger_detail = "✅ *Security:* No dangerous patterns detected"
        warning = (f"🔔 *New File Upload — Review Required*\n\n"
                   f"👤 User: `{user_id}`\n"
                   f"📦 Project: `{project_name}`\n"
                   f"📁 File: `{file_name}` (`.{file_ext.lstrip('.')}`)\n\n"
                   f"{danger_detail}")
        for aid in admin_ids:
            try: bot.send_message(aid, warning, reply_markup=markup, parse_mode='Markdown')
            except Exception: pass
        bot.send_message(chat_id, M('queued', project=project_name))

def _queue_zip_for_approval(file_content, file_name_zip, user_id, project_name, main_file, message):
    """Scan and queue a ZIP upload for admin approval."""
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_")
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as f: f.write(file_content)

        is_safe, security_msg = scan_zip_security(zip_path)

        all_found = []
        try:
            with zipfile.ZipFile(zip_path, 'r') as _zref:
                for _fi in _zref.infolist():
                    if _fi.filename.endswith(('.py', '.js', '.zip', '.txt', '.sh', '.bat', '.cmd')):
                        with _zref.open(_fi.filename) as _f:
                            try:
                                _content = _f.read().decode('utf-8', errors='ignore')
                            except Exception:
                                continue
                            for _p in DANGEROUS_PATTERNS:
                                if _p not in all_found and re.search(_p, _content, re.IGNORECASE):
                                    all_found.append(_p)
        except Exception:
            pass

        if user_id not in pending_zip_files: pending_zip_files[user_id] = {}
        pending_zip_files[user_id][project_name] = {
            'content': file_content,
            'patterns': all_found,
            'file_name_zip': file_name_zip,
            'project_name': project_name,
            'main_file': main_file,
        }
        save_pending_zip_db(user_id, project_name, pending_zip_files[user_id][project_name])

        if _should_auto_approve(is_safe and not all_found, user_id):
            if _approve_zip_core(user_id, project_name, message):
                _notify_auto_approved(user_id, project_name, 'zip'); return

        markup_approval = types.InlineKeyboardMarkup()
        markup_approval.row(
            types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_zip_{user_id}_{project_name}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_zip_{user_id}_{project_name}")
        )
        markup_approval.row(types.InlineKeyboardButton("📋 View in Pending Files", callback_data=f"pending_user_{user_id}"))

        if all_found:
            pattern_lines = '\n'.join(f"  ⚠️ `{p}`" for p in all_found[:10])
            if len(all_found) > 10:
                pattern_lines += f"\n  ... and `{len(all_found) - 10}` more"
            danger_detail = f"🚨 *Dangerous Patterns Found:* `{len(all_found)}`\n{pattern_lines}"
        else:
            danger_detail = "✅ *Security:* No dangerous patterns detected"

        warning = (f"🔔 *New ZIP Upload — Review Required*\n\n"
                   f"👤 User: `{user_id}`\n"
                   f"📦 Project: `{project_name}`\n"
                   f"📁 File: `{file_name_zip}`\n\n"
                   f"{danger_detail}")
        for aid in admin_ids:
            try: bot.send_message(aid, warning, reply_markup=markup_approval, parse_mode='Markdown')
            except Exception: pass
        bot.send_message(message.chat.id,
            f"✅ Project `{project_name}` is under review. You'll be notified upon approval.",
            parse_mode='Markdown')

    except zipfile.BadZipFile as e:
        bot.send_message(message.chat.id, f"❌ Invalid/corrupted ZIP: {e}")
    except Exception as e:
        logger.error(f"❌ Error queuing zip for {user_id}: {e}", exc_info=True)
        bot.send_message(message.chat.id, f"❌ Error processing zip: {str(e)}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir)
            except Exception: pass

# ============================================================
# --- Callback Query Handler ---
# ============================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    touch_user(call.from_user)
    data = call.data
    logger.info(f"Callback: User={user_id}, Data='{data}'")

    if is_user_banned(user_id) and data not in ['back_to_main']:
        bot.answer_callback_query(call.id, M('banned'), show_alert=True)
        return

    if bot_locked and user_id not in admin_ids and data not in ['back_to_main', 'speed', 'stats', 'my_info']:
        bot.answer_callback_query(call.id, "⚠️ Bot locked by admin.", show_alert=True)
        return

    try:
        # Plans system (view plans, buy, deposit, free plan, admin plan/payment tools)
        if handle_plan_callbacks(call): return

        if data == 'upload': upload_callback(call)
        elif data.startswith('lb_'): leaderboard_callback(call)
        elif data.startswith('rp_'): points_callback(call)
        elif data.startswith('pbuy'): points_buy_callback(call)
        elif data == 'check_files': check_files_callback(call)
        elif data.startswith('file_'): file_control_callback(call)
        elif data.startswith('umfile_'): um_file_control_callback(call)
        elif data.startswith('changemain_'): change_main_file_callback(call)
        elif data.startswith('start_'): start_bot_callback(call)
        elif data.startswith('stop_'): stop_bot_callback(call)
        elif data.startswith('restart_'): restart_bot_callback(call)
        elif data.startswith('delete_'): delete_bot_callback(call)
        elif data == 'live_menu': live_menu_callback(call)
        elif data.startswith('livestop_'): live_stop_callback(call)
        elif data.startswith('live_'): live_logs_callback(call)
        elif data.startswith(('exp_', 'expd_', 'expf_', 'imp_')): project_data_callback(call)
        elif data.startswith('logs_'): logs_bot_callback(call)
        elif data == 'speed': speed_callback(call)
        elif data in ('my_info', 'mi_hist'): my_info_callback(call)
        elif data == 'redeem_start': redeem_user_start(call)
        elif data.startswith('cd_'): admin_required_callback(call, redeem_admin_callback)
        elif data.startswith('bk_'): admin_required_callback(call, button_color_callback)
        elif data.startswith('mx_'): admin_required_callback(call, message_editor_callback)
        elif data.startswith('ap_'): admin_required_callback(call, toolbox_callback)
        elif data.startswith('sm_'): admin_required_callback(call, monitor_callback)
        elif data == 'ar_me': admin_required_callback(call, roles_me_callback)
        elif data.startswith('ar_'): owner_required_callback(call, roles_callback)
        elif data.startswith('bkp_'): owner_required_callback(call, backup_callback)
        elif data == 'back_to_main': back_to_main_callback(call)
        elif data.startswith('confirm_broadcast_'): handle_confirm_broadcast(call)
        elif data == 'cancel_broadcast': handle_cancel_broadcast(call)
        elif data == 'noop': bot.answer_callback_query(call.id)
        elif data == 'manual_install':
            bot.answer_callback_query(call.id)
            manual_install_module_init(call.message)
        # Admin callbacks
        elif data == 'subscription': admin_required_callback(call, subscription_management_callback)
        elif data == 'stats': stats_callback(call)
        elif data == 'lock_bot': admin_required_callback(call, lock_bot_callback)
        elif data == 'unlock_bot': admin_required_callback(call, unlock_bot_callback)
        elif data == 'run_all_scripts': admin_required_callback(call, run_all_scripts_callback)
        elif data == 'broadcast': admin_required_callback(call, broadcast_init_callback)
        elif data == 'admin_panel': admin_required_callback(call, admin_panel_callback)
        elif data.startswith(('adm_', 'adt_')): admin_required_callback(call, admin_tools_callback)
        elif data.startswith('bc_'): admin_required_callback(call, button_cfg_callback)
        elif data.startswith('ua_'): admin_required_callback(call, upload_approval_callback)
        elif data == 'ud_home' or data.startswith('ud_'): admin_required_callback(call, users_directory_callback)
        elif data == 'add_admin': owner_required_callback(call, add_admin_init_callback)
        elif data == 'remove_admin': owner_required_callback(call, remove_admin_init_callback)
        elif data == 'list_admins': admin_required_callback(call, list_admins_callback)
        elif data == 'add_subscription': admin_required_callback(call, add_subscription_init_callback)
        elif data == 'remove_subscription': admin_required_callback(call, remove_subscription_init_callback)
        elif data == 'check_subscription': admin_required_callback(call, check_subscription_init_callback)
        # User Management callbacks
        elif data == 'user_management': admin_required_callback(call, user_management_callback)
        elif data == 'ban_user': admin_required_callback(call, ban_user_callback)
        elif data == 'unban_user': admin_required_callback(call, unban_user_callback)
        elif data == 'user_info': admin_required_callback(call, user_info_callback)
        elif data == 'all_users': admin_required_callback(call, all_users_callback)
        elif data == 'set_user_limit': admin_required_callback(call, set_user_limit_callback)
        elif data == 'remove_user_limit': admin_required_callback(call, remove_user_limit_callback)
        elif data.startswith('users_page_'): admin_required_callback(call, handle_users_page)
        elif data == 'view_user_files': admin_required_callback(call, view_user_files_callback)
        elif data == 'pending_files': admin_required_callback(call, pending_files_callback)
        elif data.startswith('pending_user_'): admin_required_callback(call, pending_user_callback)
        elif data.startswith('chat_user_'): admin_required_callback(call, chat_user_callback)
        elif data.startswith('admin_user_files_'): admin_required_callback(call, admin_user_files_callback)
        # File Approval callbacks
        elif data.startswith('approve_file_'): admin_required_callback(call, process_approve_file)
        elif data.startswith('reject_file_'): admin_required_callback(call, process_reject_file)
        elif data.startswith('approve_zip_'): admin_required_callback(call, process_approve_zip)
        elif data.startswith('reject_zip_'): admin_required_callback(call, process_reject_zip)
        # Force Join Channel callbacks
        elif data == 'channel_add': admin_required_callback(call, lambda c: _logic_channel_add(c.message, override_user_id=c.from_user.id))
        elif data == 'set_force_join': admin_required_callback(call, set_force_join_callback)
        elif data.startswith('remove_force_join_'): admin_required_callback(call, remove_force_join_callback)
        elif data == 'check_joined': check_joined_callback(call)
        else:
            bot.answer_callback_query(call.id, "Unknown action.")
            logger.warning(f"Unhandled callback: {data} from {user_id}")
    except Exception as e:
        logger.error(f"Error handling callback '{data}' for {user_id}: {e}", exc_info=True)
        try: bot.answer_callback_query(call.id, "Error processing request.", show_alert=True)
        except Exception: pass

def admin_required_callback(call, func_to_run):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin permissions required.", show_alert=True)
        return
    func_to_run(call)

def owner_required_callback(call, func_to_run):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "⚠️ Owner permissions required.", show_alert=True)
        return
    func_to_run(call)

# ============================================================
# --- User Callbacks ---
# ============================================================
def change_main_file_callback(call):
    """Let the user change the main file of an existing project."""
    try:
        _, script_owner_id_str, project_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == project_name for f in user_files_list):
            bot.answer_callback_query(call.id, "⚠️ Project not found.", show_alert=True); return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            f"📁 *Change Main File — {project_name}*\n\n"
            f"Send the new main script filename to run:\n"
            f"• Python: `bot.py`, `main.py`, `app.py`…\n"
            f"• Node.js: `index.js`, `bot.js`…\n\n"
            f"The file must already exist inside the project folder.\n\n"
            f"/cancel to abort.",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(msg, process_change_main_file, script_owner_id, project_name, call.message)
    except Exception as e:
        logger.error(f"Error in change_main_file_callback: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error.", show_alert=True)

def process_change_main_file(message, script_owner_id, project_name, original_msg):
    """Process the new main file name provided by the user."""
    if message.text and message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Change cancelled.")
        return
    new_main_file = (message.text or '').strip()
    if not (new_main_file.endswith('.py') or new_main_file.endswith('.js')):
        msg = bot.reply_to(message, "⚠️ File must end in `.py` or `.js`. Try again or /cancel.", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_change_main_file, script_owner_id, project_name, original_msg)
        return
    project_folder = get_user_folder(script_owner_id, project_name)
    new_file_path = os.path.join(project_folder, new_main_file)
    if not os.path.exists(new_file_path):
        msg = bot.reply_to(message,
            f"⚠️ `{new_main_file}` not found inside project `{project_name}`.\n"
            f"Make sure the file was uploaded as part of the project. Try again or /cancel.",
            parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_change_main_file, script_owner_id, project_name, original_msg)
        return
    if update_main_file_db(script_owner_id, project_name, new_main_file):
        bot.reply_to(message, f"✅ Main file for project `{project_name}` updated to `{new_main_file}`.\nRestart the project to apply the change.", parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ Failed to update main file. Please try again.")

def upload_callback(call):
    user_id = call.from_user.id
    if is_user_banned(user_id):
        bot.answer_callback_query(call.id, "🚫 You are banned.", show_alert=True); return
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.answer_callback_query(call.id, f"⚠️ Project limit ({current_files}/{limit_str}) reached. Upgrade via 💎 View Plans.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, M('upload_prompt', **_upl_vars(user_id)))

def check_files_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.answer_callback_query(call.id, "⚠️ No projects uploaded.", show_alert=True)
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main'))
            bot.edit_message_text(_projects_text(user_id, True), chat_id,
                                  call.message.message_id, reply_markup=markup, parse_mode='HTML')
        except Exception: pass
        return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    for project_name, main_file, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, project_name)
        status_icon = "🟢" if is_running else "🔴"
        markup.add(types.InlineKeyboardButton(f"{status_icon} {project_name}", callback_data=f'file_{user_id}_{project_name}'))
    markup.add(types.InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main'))
    try:
        bot.edit_message_text(_projects_text(user_id), chat_id, call.message.message_id,
                              reply_markup=markup, parse_mode='HTML')
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e): logger.error(f"Error editing file list: {e}")

def _project_panel_text(owner_id, project_name, main_file, file_type, status_text):
    esc = _hmx.escape
    st = str(status_text).replace('*', '')
    lines = [f"📄 Main file ▸ <code>{esc(str(main_file))}</code> · {esc(str(file_type))}", f"👤 Owner ▸ <code>{owner_id}</code>", f"📡 Status ▸ <b>{esc(st)}</b>"]
    try:
        bu = project_bot_username(owner_id, project_name)
        if bu: lines.append(f"🤖 Bot ▸ @{esc(bu.lstrip('@'))}")
        info = bot_scripts.get(f"{owner_id}_{project_name}")
        if info and info.get('start_time') and is_bot_running(owner_id, project_name):
            lines.append(f"⏱ Uptime ▸ <b>{_format_uptime((datetime.now() - info['start_time']).total_seconds())}</b>")
        r = _db_q("SELECT uploaded_at FROM project_meta WHERE user_id=? AND project_name=?", (owner_id, project_name), one=True)
        if r and r[0]: lines.append(f"🗓 Deployed ▸ {str(r[0])[:10]}")
    except Exception: pass
    return (f"✦ <b>𝗣𝗥𝗢𝗝𝗘𝗖𝗧  𝗖𝗢𝗡𝗦𝗢𝗟𝗘</b> ✦\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n<b>{esc(str(project_name))}</b>\n"
            "<blockquote>" + "\n".join(lines) + "</blockquote>")

def file_control_callback(call):
    """File control panel opened from Check Files."""
    try:
        _, script_owner_id_str, project_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ You can only manage your own projects.", show_alert=True)
            check_files_callback(call); return
        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == project_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "⚠️ Project not found.", show_alert=True)
            check_files_callback(call); return
        bot.answer_callback_query(call.id)
        _, main_file, file_type = file_info
        is_running = is_bot_running(script_owner_id, project_name)
        status_text = '🟢 Running' if is_running else '🔴 Stopped'
        try:
            bot.edit_message_text(
                _project_panel_text(script_owner_id, project_name, main_file, file_type, status_text),
                call.message.chat.id, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, project_name, is_running, 'check_files'),
                parse_mode='HTML'
            )
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e): raise
    except (ValueError, IndexError) as ve:
        logger.error(f"Error parsing file control: {ve}")
        bot.answer_callback_query(call.id, "Error: Invalid action data.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in file_control_callback: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "An error occurred.", show_alert=True)

def um_file_control_callback(call):
    """File control panel opened from User Management."""
    try:
        _, script_owner_id_str, project_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        if call.from_user.id not in admin_ids:
            bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True); return
        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == project_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "⚠️ Project not found.", show_alert=True)
            _show_user_files_admin_inline(call.message.chat.id, call.message.message_id, script_owner_id); return
        bot.answer_callback_query(call.id)
        _, main_file, file_type = file_info
        is_running = is_bot_running(script_owner_id, project_name)
        status_text = '🟢 Running' if is_running else '🔴 Stopped'
        try:
            bot.edit_message_text(
                _project_panel_text(script_owner_id, project_name, main_file, file_type, status_text),
                call.message.chat.id, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, project_name, is_running, f'admin_user_files_{script_owner_id}'),
                parse_mode='HTML'
            )
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e): raise
    except (ValueError, IndexError) as ve:
        logger.error(f"Error parsing um file control: {ve}")
        bot.answer_callback_query(call.id, "Error: Invalid action data.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in um_file_control_callback: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "An error occurred.", show_alert=True)

def start_bot_callback(call):
    try:
        _, script_owner_id_str, project_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == project_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "⚠️ Project not found.", show_alert=True); check_files_callback(call); return
        _, main_file, file_type = file_info
        user_folder = get_user_folder(script_owner_id, project_name)
        file_path = os.path.join(user_folder, main_file)
        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, f"⚠️ Main file `{main_file}` missing! Re-upload.", show_alert=True)
            remove_user_file_db(script_owner_id, project_name); check_files_callback(call); return
        if is_bot_running(script_owner_id, project_name):
            bot.answer_callback_query(call.id, f"⚠️ Project already running.", show_alert=True)
            try: bot.edit_message_reply_markup(chat_id_for_reply, call.message.message_id,
                                               reply_markup=create_control_buttons(script_owner_id, project_name, True, _extract_back_callback(call)))
            except Exception: pass
            return
        bot.answer_callback_query(call.id, f"⏳ Starting {project_name}...")

        def _start_with_deps():
            if file_type == 'py':
                if not install_requirements_if_present(user_folder, script_owner_id, call.message):
                    return
                run_script(file_path, script_owner_id, user_folder, project_name, call.message,
                           attempt=1, skip_deps_install=True)
            elif file_type == 'js':
                if not install_package_json_if_present(user_folder, script_owner_id, call.message):
                    return
                run_js_script(file_path, script_owner_id, user_folder, project_name, call.message,
                              attempt=1, skip_deps_install=True)
            else:
                bot.send_message(chat_id_for_reply, f"❌ Unknown file type `{file_type}`.", parse_mode='Markdown')

        threading.Thread(target=_start_with_deps).start()
        time.sleep(1.5)
        is_now_running = is_bot_running(script_owner_id, project_name)
        status_text = '🟢 Running' if is_now_running else '🟡 Starting...'
        try:
            bot.edit_message_text(
                _project_panel_text(script_owner_id, project_name, main_file, file_type, status_text),
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, project_name, is_now_running, _extract_back_callback(call)), parse_mode='HTML'
            )
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e): raise
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing start callback: {e}")
        bot.answer_callback_query(call.id, "Error: Invalid start command.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in start_bot_callback: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error starting project.", show_alert=True)

def stop_bot_callback(call):
    try:
        _, script_owner_id_str, project_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == project_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "⚠️ Project not found.", show_alert=True); return
        _, main_file, file_type = file_info
        script_key = f"{script_owner_id}_{project_name}"
        stopped_text = _project_panel_text(script_owner_id, project_name, main_file, file_type, '🔴 Stopped')
        if not is_bot_running(script_owner_id, project_name):
            bot.answer_callback_query(call.id, f"⚠️ Project already stopped.", show_alert=True)
            try:
                bot.edit_message_text(stopped_text, chat_id_for_reply, call.message.message_id,
                    reply_markup=create_control_buttons(script_owner_id, project_name, False, _extract_back_callback(call)), parse_mode='HTML')
            except Exception: pass
            return
        bot.answer_callback_query(call.id, f"⏳ Stopping {project_name}...")
        process_info = bot_scripts.get(script_key)
        if process_info:
            kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]
        try:
            bot.edit_message_text(stopped_text, chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, project_name, False, _extract_back_callback(call)), parse_mode='HTML')
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e): raise
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing stop callback: {e}")
        bot.answer_callback_query(call.id, "Error: Invalid stop command.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in stop_bot_callback: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error stopping project.", show_alert=True)

def restart_bot_callback(call):
    try:
        _, script_owner_id_str, project_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == project_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "⚠️ Project not found.", show_alert=True); check_files_callback(call); return
        _, main_file, file_type = file_info
        user_folder = get_user_folder(script_owner_id, project_name)
        file_path = os.path.join(user_folder, main_file)
        script_key = f"{script_owner_id}_{project_name}"
        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, f"⚠️ Main file `{main_file}` missing! Re-upload.", show_alert=True)
            remove_user_file_db(script_owner_id, project_name)
            if script_key in bot_scripts: del bot_scripts[script_key]
            check_files_callback(call); return
        bot.answer_callback_query(call.id, f"⏳ Restarting {project_name}...")
        if is_bot_running(script_owner_id, project_name):
            process_info = bot_scripts.get(script_key)
            if process_info: kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]
            time.sleep(1.5)
        if file_type == 'py':
            threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, project_name, call.message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, project_name, call.message)).start()
        else:
            bot.send_message(chat_id_for_reply, f"❌ Unknown type `{file_type}`.", parse_mode='Markdown'); return
        time.sleep(1.5)
        is_now_running = is_bot_running(script_owner_id, project_name)
        status_text = '🟢 Running' if is_now_running else '🟡 Starting...'
        try:
            bot.edit_message_text(
                _project_panel_text(script_owner_id, project_name, main_file, file_type, status_text),
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, project_name, is_now_running, _extract_back_callback(call)), parse_mode='HTML'
            )
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e): raise
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing restart callback: {e}")
        bot.answer_callback_query(call.id, "Error: Invalid restart command.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in restart_bot_callback: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error restarting.", show_alert=True)

def delete_bot_callback(call):
    try:
        _, script_owner_id_str, project_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == project_name for f in user_files_list):
            bot.answer_callback_query(call.id, "⚠️ Project not found.", show_alert=True); check_files_callback(call); return
        bot.answer_callback_query(call.id, f"🗑️ Deleting {project_name}...")
        script_key = f"{script_owner_id}_{project_name}"
        if is_bot_running(script_owner_id, project_name):
            process_info = bot_scripts.get(script_key)
            if process_info: kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]
            time.sleep(0.5)
        project_folder = get_user_folder(script_owner_id, project_name)
        if os.path.exists(project_folder):
            try: shutil.rmtree(project_folder)
            except OSError as e: logger.error(f"Error deleting project folder {project_folder}: {e}")
        remove_user_file_db(script_owner_id, project_name)
        try:
            bot.edit_message_text(
                f"🗑️ Project `{project_name}` (User `{script_owner_id}`) deleted.",
                chat_id_for_reply, call.message.message_id, reply_markup=None, parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error editing msg after delete: {e}")
            bot.send_message(chat_id_for_reply, f"🗑️ Project `{project_name}` deleted.", parse_mode='Markdown')
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing delete callback: {e}")
        bot.answer_callback_query(call.id, "Error: Invalid delete command.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in delete_bot_callback: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error deleting.", show_alert=True)

def logs_bot_callback(call):
    try:
        _, script_owner_id_str, project_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == project_name for f in user_files_list):
            bot.answer_callback_query(call.id, "⚠️ Project not found.", show_alert=True); check_files_callback(call); return
        user_folder = get_user_folder(script_owner_id, project_name)
        log_path = os.path.join(user_folder, f"{project_name}.log")
        if not os.path.exists(log_path):
            bot.answer_callback_query(call.id, f"⚠️ No logs for '{project_name}'.", show_alert=True); return
        bot.answer_callback_query(call.id)
        try:
            log_content = ""
            file_size = os.path.getsize(log_path)
            max_log_kb = 100; max_tg_msg = 4000
            if file_size == 0:
                log_content = "(Log is empty)"
            elif file_size > max_log_kb * 1024:
                with open(log_path, 'rb') as f:
                    f.seek(-max_log_kb * 1024, os.SEEK_END)
                    log_bytes = f.read()
                log_content = f"(Last {max_log_kb}KB)\n...\n" + log_bytes.decode('utf-8', errors='ignore')
            else:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    log_content = f.read()
            if len(log_content) > max_tg_msg:
                log_content = log_content[-max_tg_msg:]
                first_nl = log_content.find('\n')
                if first_nl != -1: log_content = "...\n" + log_content[first_nl+1:]
                else: log_content = "...\n" + log_content
            if not log_content.strip(): log_content = "(No visible content)"
            bot.send_message(chat_id_for_reply,
                             f"📜 *Logs for project* `{project_name}` *(User* `{script_owner_id}`*):\n*\n```\n{log_content}\n```",
                             parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error reading/sending log: {e}")
            bot.send_message(chat_id_for_reply, f"❌ Error reading log for `{project_name}`.", parse_mode='Markdown')
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing logs callback: {e}")
        bot.answer_callback_query(call.id, "Error: Invalid logs command.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in logs_bot_callback: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error fetching logs.", show_alert=True)

def speed_callback(call):
    started = time.time()
    try:
        bot.answer_callback_query(call.id, "🔄 Refreshing...")
        r, tg, sy = _speed_measure(started)
        try:
            bot.edit_message_text(_speed_text(call.from_user.id, r, tg, sy), call.message.chat.id,
                                  call.message.message_id, parse_mode='HTML', reply_markup=_speed_markup())
        except Exception as e:
            if 'not modified' not in str(e): raise
    except Exception as e:
        logger.error(f"Error during speed test (cb): {e}")

def back_to_main_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if is_user_banned(user_id):
        bot.answer_callback_query(call.id, "🚫 You are banned.", show_alert=True); return
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    user_status, expiry_info = _user_rank(user_id)
    _pl = lambda x: _hmx.escape(str(x).replace('\\', '').replace('*', '').replace('`', ''))
    main_menu_text = M('welcome_back', name=call.from_user.first_name, id=user_id, status=_pl(user_status), expiry=_pl(expiry_info),
                       files=f"{current_files} / {limit_str}", _raw=('status', 'expiry'))
    try:
        bot.answer_callback_query(call.id)
        bot.edit_message_text(main_menu_text, chat_id, call.message.message_id,
                              reply_markup=create_main_menu_inline(user_id), parse_mode='Markdown')
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e): logger.error(f"API error on back_to_main: {e}")
    except Exception as e: logger.error(f"Error handling back_to_main: {e}")

# ============================================================
# --- Admin Tools (33 extra admin-panel options) ---
# ============================================================
import collections as _collections
import csv as _csv2
import html as _hh2

class _RingHandler(logging.Handler):
    """Keeps the most recent log records in memory for the Admin Tools log viewers."""
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.buf = _collections.deque(maxlen=400)
    def emit(self, record):
        try:
            self.buf.append((record.levelno, datetime.fromtimestamp(record.created).strftime('%H:%M:%S'),
                             record.levelname, record.getMessage()[:300]))
        except Exception:
            pass

_RING = _RingHandler()
logging.getLogger().addHandler(_RING)

def _e(x):
    return _hh2.escape(str(x if x is not None else ''))

ADMIN_TOOL_GROUPS = [
    ("📊 Monitoring", [
        ('server', '🖥️ Server Status'), ('running', '🤖 Running Bots'), ('hogs', '🔥 Resource Hogs'),
        ('storage', '💾 Storage Usage'), ('info', 'ℹ️ Bot Info'), ('errors', '🚨 Recent Errors'),
        ('activity', '📜 Activity Log'), ('report', '📰 Daily Report')]),
    ("👥 Users", [
        ('premium', '💎 Premium Users'), ('expiring', '⏰ Expiring Soon'), ('banned', '🚫 Banned List'),
        ('topup', '🏆 Top Uploaders'), ('inactive', '😴 Inactive Users'), ('plandist', '📊 Plan Distribution'),
        ('growth', '📈 Growth Stats'), ('exportusers', '📤 Export Users CSV'), ('gift', '🎁 Gift Days')]),
    ("💬 Messaging", [
        ('msguser', '✉️ Message a User'), ('bcpremium', '📣 Broadcast: Premium'),
        ('bcfree', '📣 Broadcast: Free'), ('welcomenote', '📝 Welcome Note')]),
    ("🤖 Bots", [
        ('stopall', '⏹️ Stop All Scripts'), ('restartall', '🔄 Restart All Running'),
        ('stopuser', "🛑 Stop a User's Bots"), ('search', '🔎 Search Project'), ('clearlogs', '🧹 Clear Stopped Logs')]),
    ("⚙️ System", [
        ('backup', '💽 Backup Database'), ('autobackup', '🕒 Auto-Backup'), ('freelimit', '📦 Free Project Limit'),
        ('maxupload', '📏 Max Upload Size'), ('reg', '🆕 Registrations'), ('newalerts', '🔔 New-User Alerts'),
        ('restartbot', '♻️ Restart Bot')]),
]
ADMIN_TOOL_COUNT = sum(len(g[1]) for g in ADMIN_TOOL_GROUPS)
OWNER_ONLY_TOOLS = {'backup', 'autobackup', 'exportusers', 'restartbot', 'stopall', 'restartall'}

def _tk(label_key):
    for gi, (_, tools) in enumerate(ADMIN_TOOL_GROUPS):
        for k, lab in tools:
            if k == label_key: return gi, lab
    return 0, label_key

def _back_markup(group=None):
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🔙 Back to Tools", callback_data=f"adm_g{group}" if group is not None else "adm_home"))
    return m

def _atool_send(chat_id, text, group=None, markup=None):
    chunks = [text[i:i + 3800] for i in range(0, len(text), 3800)] or ['—']
    for i, ch in enumerate(chunks):
        mk = (markup or _back_markup(group)) if i == len(chunks) - 1 else None
        bot.send_message(chat_id, ch, parse_mode='HTML', reply_markup=mk)

def _fmt_size(n):
    n = float(n)
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or u == 'GB': return f"{n:.1f} {u}" if u != 'B' else f"{int(n)} B"
        n /= 1024

def _dir_size(path):
    total = 0
    for root, _d, files in os.walk(path):
        for f in files:
            try: total += os.path.getsize(os.path.join(root, f))
            except Exception: pass
    return total

def _running_list():
    out = []
    for key, info in list(bot_scripts.items()):
        oid, pn = info.get('script_owner_id'), info.get('project_name')
        if info.get('process') and is_bot_running(oid, pn):
            out.append(info)
    return out

def _join_dates():
    return _db_q("SELECT user_id, join_date, last_seen FROM active_users")

# ---------------- menus ----------------
def admin_tools_home_text():
    return (f"🧰 <b>Admin Tools</b>\n\n{ADMIN_TOOL_COUNT} extra tools in {len(ADMIN_TOOL_GROUPS)} groups.\n"
            f"👥 Users: <b>{len(active_users)}</b> • 🤖 Running: <b>{len(_running_list())}</b> • 💎 Premium: <b>{sum(1 for u in user_subscriptions if has_active_sub(u))}</b>\n\nChoose a group:")

def admin_tools_home_markup():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(*[types.InlineKeyboardButton(f"{g[0]} ({len(g[1])})", callback_data=f"adm_g{i}") for i, g in enumerate(ADMIN_TOOL_GROUPS)])
    m.add(types.InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel"))
    return m

def _group_view(gi):
    name, tools = ADMIN_TOOL_GROUPS[gi]
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(*[types.InlineKeyboardButton(lab, callback_data=f"adt_{k}") for k, lab in tools])
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_home"))
    return f"🧰 <b>{_e(name)}</b>\nPick a tool:", m

# ---------------- simple read-only tools ----------------
def tool_server(chat_id):
    cpu = psutil.cpu_percent(interval=0.6)
    vm = psutil.virtual_memory()
    du = psutil.disk_usage(BASE_DIR)
    try: load = ", ".join(f"{x:.2f}" for x in os.getloadavg())
    except Exception: load = "n/a"
    proc = psutil.Process(os.getpid())
    boot = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
    txt = (f"🖥️ <b>Server Status</b>\n━━━━━━━━━━━━━━━━\n"
           f"⚙️ CPU: <b>{cpu:.0f}%</b> ({psutil.cpu_count()} cores)\n📈 Load avg: <code>{load}</code>\n"
           f"🧠 RAM: <b>{vm.percent:.0f}%</b> ({_fmt_size(vm.used)} / {_fmt_size(vm.total)})\n"
           f"💽 Disk: <b>{du.percent:.0f}%</b> ({_fmt_size(du.used)} / {_fmt_size(du.total)})\n"
           f"🤖 Bot process: <b>{_fmt_size(proc.memory_info().rss)}</b> RAM, {proc.num_threads()} threads\n"
           f"⏱️ Bot uptime: <b>{_format_uptime(time.time() - BOT_START_TIME)}</b>\n🖧 Server uptime: <b>{_format_uptime(boot.total_seconds())}</b>")
    _atool_send(chat_id, txt, 0)

def tool_running(chat_id):
    items = _running_list()
    if not items:
        _atool_send(chat_id, "🤖 <b>Running Bots</b>\n\nNothing is running right now.", 0); return
    lines = [f"🤖 <b>Running Bots ({len(items)})</b>\n"]
    for i in sorted(items, key=lambda x: x.get('start_time') or datetime.now())[:40]:
        up = _format_uptime((datetime.now() - i['start_time']).total_seconds()) if i.get('start_time') else '?'
        lines.append(f"🟢 <code>{i.get('script_owner_id')}</code> • <b>{_e(i.get('project_name'))}</b> • {up} • pid {i['process'].pid}")
    if len(items) > 40: lines.append(f"... and {len(items) - 40} more")
    _atool_send(chat_id, "\n".join(lines), 0)

def tool_hogs(chat_id):
    rows = []
    for i in _running_list():
        try:
            p = psutil.Process(i['process'].pid)
            procs = [p] + p.children(recursive=True)
            rss = sum(x.memory_info().rss for x in procs if x.is_running())
            cpu = sum(x.cpu_percent(interval=None) for x in procs if x.is_running())
            rows.append((rss, cpu, i))
        except Exception: pass
    time.sleep(0.4)
    rows2 = []
    for rss, _c, i in rows:
        try:
            p = psutil.Process(i['process'].pid)
            procs = [p] + p.children(recursive=True)
            cpu = sum(x.cpu_percent(interval=None) for x in procs if x.is_running())
            rows2.append((rss, cpu, i))
        except Exception: pass
    if not rows2:
        _atool_send(chat_id, "🔥 <b>Resource Hogs</b>\n\nNo running bots.", 0); return
    rows2.sort(key=lambda r: r[0], reverse=True)
    lines = ["🔥 <b>Top resource users</b> (by RAM)\n"]
    for rss, cpu, i in rows2[:10]:
        lines.append(f"• <code>{i.get('script_owner_id')}</code> <b>{_e(i.get('project_name'))}</b> — {_fmt_size(rss)} • CPU {cpu:.0f}%")
    _atool_send(chat_id, "\n".join(lines), 0)

def tool_storage(chat_id):
    sizes = []
    try:
        for d in os.listdir(UPLOAD_BOTS_DIR):
            p = os.path.join(UPLOAD_BOTS_DIR, d)
            if os.path.isdir(p): sizes.append((d, _dir_size(p)))
    except Exception: pass
    total = sum(s for _, s in sizes)
    sizes.sort(key=lambda x: x[1], reverse=True)
    lines = [f"💾 <b>Storage Usage</b>\nTotal projects: <b>{_fmt_size(total)}</b>\nDB: <b>{_fmt_size(os.path.getsize(DATABASE_PATH)) if os.path.exists(DATABASE_PATH) else '0 B'}</b>\n\n<b>Top users</b>"]
    lines += [f"• <code>{_e(d)}</code> — {_fmt_size(s)}" for d, s in sizes[:10]] or ["(empty)"]
    _atool_send(chat_id, "\n".join(lines), 0)

def tool_info(chat_id):
    def cnt(t):
        try: return _db_q(f"SELECT COUNT(*) FROM {t}", one=True)[0]
        except Exception: return 0
    txt = (f"ℹ️ <b>Bot Info</b>\n━━━━━━━━━━━━━━━━\n🐍 Python: <b>{sys.version.split()[0]}</b>\n🐧 OS: <b>{_e(sys.platform)}</b>\n"
           f"📚 telebot: <b>{_e(getattr(telebot, '__version__', '?'))}</b>\n👑 Owner: <code>{OWNER_ID}</code>\n"
           f"👥 Users: <b>{cnt('active_users')}</b>\n🛡️ Admins: <b>{len(admin_ids)}</b>\n🚫 Banned: <b>{len(banned_users)}</b>\n"
           f"📁 Projects: <b>{sum(len(v) for v in user_files.values())}</b>\n🤖 Running: <b>{len(_running_list())}</b>\n"
           f"💎 Active subs: <b>{sum(1 for u in user_subscriptions if has_active_sub(u))}</b>\n🛍️ Plans: <b>{cnt('plans')}</b>\n"
           f"🧾 Payments logged: <b>{cnt('payments')}</b>\n🔒 Locked: <b>{'Yes' if bot_locked else 'No'}</b>")
    _atool_send(chat_id, txt, 0)

def _log_view(chat_id, min_level, title, n=18):
    rows = [r for r in list(_RING.buf) if r[0] >= min_level][-n:]
    if not rows:
        _atool_send(chat_id, f"{title}\n\n✅ Nothing to show.", 0); return
    body = "\n".join(f"{t} [{lv[:4]}] {m}" for _, t, lv, m in rows)
    _atool_send(chat_id, f"{title}\n<pre>{_e(body[-3400:])}</pre>", 0)

def tool_errors(chat_id): _log_view(chat_id, logging.WARNING, "🚨 <b>Recent warnings & errors</b>")
def tool_activity(chat_id): _log_view(chat_id, logging.INFO, "📜 <b>Recent activity</b>", 22)

def _revenue_today():
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    r = _db_q("SELECT COUNT(*), COALESCE(SUM(amount_base),0) FROM payments WHERE created_at >= ?", (start,), one=True)
    return r[0], r[1]

def _report_text():
    today = datetime.now().date().isoformat()
    new_today = sum(1 for _, jd, _ in _join_dates() if str(jd or '').startswith(today))
    sales, rev = _revenue_today()
    pend_pay = _db_q("SELECT COUNT(*) FROM manual_payments WHERE status='pending'", one=True)[0]
    pend_files = _db_q("SELECT COUNT(*) FROM pending_scripts", one=True)[0] + _db_q("SELECT COUNT(*) FROM pending_zips", one=True)[0]
    return (f"📰 <b>Daily Report</b> — {datetime.now():%d-%m-%Y}\n━━━━━━━━━━━━━━━━\n"
            f"🆕 New users today: <b>{new_today}</b>\n👥 Total users: <b>{len(active_users)}</b>\n"
            f"💎 Active premium: <b>{sum(1 for u in user_subscriptions if has_active_sub(u))}</b>\n"
            f"🤖 Running bots: <b>{len(_running_list())}</b>\n💰 Sales today: <b>{sales}</b> ({rev:g} {_e(get_base_curr())})\n"
            f"⏳ Pending payments: <b>{pend_pay}</b>\n📋 Pending files: <b>{pend_files}</b>")

def tool_report(chat_id): _atool_send(chat_id, _report_text(), 0)

# ---------------- users ----------------
def tool_premium(chat_id):
    now = datetime.now()
    subs = sorted([(u, s) for u, s in user_subscriptions.items() if has_active_sub(u)], key=lambda x: x[1]['expiry'])
    if not subs:
        _atool_send(chat_id, "💎 <b>Premium Users</b>\n\nNo active subscriptions.", 1); return
    lines = [f"💎 <b>Premium Users ({len(subs)})</b>\n"]
    for u, s in subs[:40]:
        lines.append(f"<code>{u}</code> • {_e(s.get('plan_name') or 'Premium')} • {(s['expiry'] - now).days}d left")
    _atool_send(chat_id, "\n".join(lines), 1)

def tool_expiring(chat_id):
    now = datetime.now()
    subs = [(u, s) for u, s in user_subscriptions.items() if s.get('expiry') and now < s['expiry'] <= now + timedelta(days=7)]
    if not subs:
        _atool_send(chat_id, "⏰ <b>Expiring Soon</b>\n\nNobody expires in the next 7 days.", 1); return
    subs.sort(key=lambda x: x[1]['expiry'])
    lines = [f"⏰ <b>Expiring within 7 days ({len(subs)})</b>\n"]
    lines += [f"<code>{u}</code> • {_e(s.get('plan_name') or 'Premium')} • {s['expiry']:%d-%m} ({(s['expiry'] - now).days}d)" for u, s in subs[:40]]
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("📩 Send renewal reminder to all", callback_data="adt_expiring_remind"))
    m.add(types.InlineKeyboardButton("🔙 Back to Tools", callback_data="adm_g1"))
    _atool_send(chat_id, "\n".join(lines), 1, m)

def tool_expiring_remind(chat_id):
    now = datetime.now(); sent = 0
    mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("💎 Renew Now", callback_data="view_plans_cb"))
    for u, s in list(user_subscriptions.items()):
        if s.get('expiry') and now < s['expiry'] <= now + timedelta(days=7):
            try:
                bot.send_message(u, f"⏰ <b>Your plan expires on {s['expiry']:%d-%m-%Y}.</b> Renew to keep your bots running!", parse_mode='HTML', reply_markup=mk)
                sent += 1
            except Exception: pass
            time.sleep(0.05)
    _atool_send(chat_id, f"✅ Reminder sent to <b>{sent}</b> user(s).", 1)

def tool_banned(chat_id):
    rows = _db_q("SELECT user_id, reason, ban_date FROM banned_users ORDER BY ban_date DESC LIMIT 40")
    if not rows:
        _atool_send(chat_id, "🚫 <b>Banned Users</b>\n\nNobody is banned.", 1); return
    lines = [f"🚫 <b>Banned Users ({len(banned_users)})</b>\n"] + [f"<code>{u}</code> • {_e(r or '-')[:40]} • {str(d)[:10]}" for u, r, d in rows]
    _atool_send(chat_id, "\n".join(lines), 1)

def tool_topup(chat_id):
    top = sorted(((u, len(f)) for u, f in user_files.items() if f), key=lambda x: x[1], reverse=True)[:10]
    if not top:
        _atool_send(chat_id, "🏆 <b>Top Uploaders</b>\n\nNo projects yet.", 1); return
    medals = ["🥇", "🥈", "🥉"] + ["▫️"] * 7
    _atool_send(chat_id, "🏆 <b>Top Uploaders</b>\n\n" + "\n".join(f"{medals[i]} <code>{u}</code> — {n} project(s)" for i, (u, n) in enumerate(top)), 1)

def tool_inactive(chat_id):
    ids = [u for u in active_users if not user_files.get(u)]
    lines = [f"😴 <b>Users with no projects: {len(ids)}</b> of {len(active_users)}\n"]
    lines += [f"<code>{u}</code>" for u in ids[:40]]
    if len(ids) > 40: lines.append(f"... and {len(ids) - 40} more")
    _atool_send(chat_id, "\n".join(lines), 1)

def tool_plandist(chat_id):
    dist = _collections.Counter()
    for u, s in user_subscriptions.items():
        if has_active_sub(u): dist[str(s.get('plan_name') or 'Premium')] += 1
    prem = sum(dist.values())
    lines = ["📊 <b>Plan Distribution</b>\n"] + [f"💎 {_e(k)}: <b>{v}</b>" for k, v in dist.most_common()]
    lines.append(f"🆓 Free users: <b>{max(0, len(active_users) - prem)}</b>")
    lines.append(f"\nTotal users: <b>{len(active_users)}</b> • Paid conversion: <b>{(prem / len(active_users) * 100) if active_users else 0:.1f}%</b>")
    _atool_send(chat_id, "\n".join(lines), 1)

def tool_growth(chat_id):
    now = datetime.now(); dates = []
    for _, jd, _ in _join_dates():
        try: dates.append(datetime.fromisoformat(jd))
        except Exception: pass
    def since(d): return sum(1 for x in dates if x >= now - timedelta(days=d))
    lines = [f"📈 <b>Growth</b>\n\n🆕 Last 24h: <b>{since(1)}</b>\n📅 Last 7 days: <b>{since(7)}</b>\n🗓️ Last 30 days: <b>{since(30)}</b>\n👥 Total: <b>{len(active_users)}</b>\n\n<b>Daily joins (7d)</b>"]
    for i in range(6, -1, -1):
        d = (now - timedelta(days=i)).date()
        n = sum(1 for x in dates if x.date() == d)
        lines.append(f"<code>{d:%d-%m}</code> {'█' * min(n, 20)} {n}")
    _atool_send(chat_id, "\n".join(lines), 1)

def tool_exportusers(chat_id):
    jd = {u: (j, l) for u, j, l in _join_dates()}
    path = os.path.join(tempfile.gettempdir(), f"users_{int(time.time())}.csv")
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = _csv2.writer(f); w.writerow(["user_id", "joined", "last_seen", "projects", "plan", "expiry", "banned"])
        for u in sorted(active_users):
            s = user_subscriptions.get(u) or {}
            w.writerow([u, (jd.get(u) or ('', ''))[0], (jd.get(u) or ('', ''))[1], len(user_files.get(u, [])),
                        s.get('plan_name', '') if has_active_sub(u) else '', s.get('expiry', '') if has_active_sub(u) else '', u in banned_users])
    with open(path, 'rb') as f: bot.send_document(chat_id, f, caption=f"📤 {len(active_users)} users")
    try: os.remove(path)
    except Exception: pass

def process_gift(message):
    if not message.text or message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    try:
        uid_s, days_s = [p.strip() for p in message.text.split('|')][:2]
        uid, days = int(uid_s), int(days_s)
        if not (1 <= days <= 3650): raise ValueError
    except Exception:
        bot.reply_to(message, "❌ Use `USER_ID | DAYS` e.g. `123456789 | 7`", parse_mode='Markdown'); return
    now = datetime.now(); cur = user_subscriptions.get(uid)
    if cur and cur['expiry'] > now:
        expiry, pname, lim = cur['expiry'] + timedelta(days=days), cur.get('plan_name'), cur.get('file_limit')
    else:
        expiry, pname, lim = now + timedelta(days=days), "Gift", SUBSCRIBED_USER_LIMIT
    save_subscription(uid, expiry, pname, lim)
    try: bot.send_message(uid, f"🎁 <b>You received {days} free day(s) of premium!</b>\nActive until <b>{expiry:%d-%m-%Y}</b>.", parse_mode='HTML')
    except Exception: pass
    bot.reply_to(message, f"✅ Gifted {days} day(s) to <code>{uid}</code> (until {expiry:%d-%m-%Y}).", parse_mode='HTML')

# ---------------- messaging ----------------
def process_msg_user(message):
    if not message.text or message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    try:
        uid_s, text = message.text.split('|', 1)
        uid = int(uid_s.strip()); text = text.strip()
        if not text: raise ValueError
    except Exception:
        bot.reply_to(message, "❌ Use `USER_ID | message text`", parse_mode='Markdown'); return
    try:
        bot.send_message(uid, f"📩 <b>Message from admin</b>\n\n{_e(text)}", parse_mode='HTML')
        bot.reply_to(message, "✅ Message delivered.")
    except Exception as e:
        bot.reply_to(message, f"❌ Could not deliver: {_e(e)}", parse_mode='HTML')

def _audience(kind):
    prem = {u for u in active_users if has_active_sub(u)}
    return sorted(prem) if kind == 'premium' else sorted(u for u in active_users if u not in prem and u not in banned_users)

def process_segment_broadcast(message, kind):
    if not message.text or message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    ids = _audience(kind); text = message.text
    status = bot.reply_to(message, f"📣 Sending to {len(ids)} user(s)...")
    def work():
        ok = fail = 0
        for u in ids:
            try: bot.send_message(u, text); ok += 1
            except Exception: fail += 1
            time.sleep(0.05)
        try: bot.send_message(message.chat.id, f"✅ Broadcast to <b>{kind}</b> users done: {ok} sent, {fail} failed.", parse_mode='HTML')
        except Exception: pass
    threading.Thread(target=work, daemon=True).start()

def process_welcome_note(message):
    if not message.text or message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    val = message.text.strip()
    if val in ('-', 'off', 'none', 'clear'): val = ''
    set_setting('WELCOME_NOTE', val)
    bot.reply_to(message, "✅ Welcome note cleared." if not val else "✅ Welcome note saved — it now shows on /start.")

# ---------------- bots ----------------
def _stop_script_key(key):
    info = bot_scripts.get(key)
    if info:
        kill_process_tree(info)
        bot_scripts.pop(key, None)

def tool_stopall_do(chat_id):
    items = _running_list()
    for i in items: _stop_script_key(f"{i.get('script_owner_id')}_{i.get('project_name')}")
    _atool_send(chat_id, f"⏹️ Stopped <b>{len(items)}</b> running script(s).", 3)

def tool_restartall_do(chat_id, anchor_msg):
    items = _running_list(); n = 0
    for i in items:
        oid, pn = i.get('script_owner_id'), i.get('project_name')
        fi = next((f for f in user_files.get(oid, []) if f[0] == pn), None)
        if not fi: continue
        _, main_file, ftype = fi
        folder = get_user_folder(oid, pn); path = os.path.join(folder, main_file)
        if not os.path.exists(path): continue
        _stop_script_key(f"{oid}_{pn}"); time.sleep(0.5)
        target = run_script if ftype == 'py' else run_js_script
        threading.Thread(target=target, args=(path, oid, folder, pn, anchor_msg), daemon=True).start()
        n += 1; time.sleep(0.7)
    _atool_send(chat_id, f"🔄 Restarted <b>{n}</b> of {len(items)} script(s).", 3)

def process_stop_user(message):
    if not message.text or message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    try: uid = int(message.text.strip())
    except Exception:
        bot.reply_to(message, "❌ Send a numeric user ID."); return
    n = 0
    for i in _running_list():
        if i.get('script_owner_id') == uid:
            _stop_script_key(f"{uid}_{i.get('project_name')}"); n += 1
    bot.reply_to(message, f"🛑 Stopped <b>{n}</b> bot(s) of <code>{uid}</code>.", parse_mode='HTML')

def process_search_project(message):
    if not message.text or message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    q = message.text.strip().lower()
    hits = [(u, f[0], f[2]) for u, fl in user_files.items() for f in fl if q in f[0].lower() or q in str(f[1]).lower()]
    if not hits:
        bot.reply_to(message, "🔎 No matching projects."); return
    lines = [f"🔎 <b>{len(hits)} match(es)</b>\n"]
    for u, pn, ft in hits[:40]:
        lines.append(f"{'🟢' if is_bot_running(u, pn) else '🔴'} <code>{u}</code> • <b>{_e(pn)}</b> ({ft})")
    bot.reply_to(message, "\n".join(lines), parse_mode='HTML')

def tool_clearlogs(chat_id):
    freed = n = 0
    for u, fl in user_files.items():
        for f in fl:
            pn = f[0]
            if is_bot_running(u, pn): continue
            p = os.path.join(get_user_folder(u, pn), f"{pn}.log")
            try:
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    freed += os.path.getsize(p); open(p, 'w').close(); n += 1
            except Exception: pass
    _atool_send(chat_id, f"🧹 Cleared <b>{n}</b> log file(s) of stopped bots, freed <b>{_fmt_size(freed)}</b>.", 3)

# ---------------- system ----------------
def _make_backup():
    path = os.path.join(tempfile.gettempdir(), f"bot_backup_{datetime.now():%Y%m%d_%H%M%S}.db")
    src = sqlite3.connect(DATABASE_PATH); dst = sqlite3.connect(path)
    with DB_LOCK: src.backup(dst)
    dst.close(); src.close()
    return path

def send_backup(chat_id, caption="💽 Database backup"):
    path = _make_backup()
    try:
        with open(path, 'rb') as f: bot.send_document(chat_id, f, caption=f"{caption} • {_fmt_size(os.path.getsize(path))}")
    finally:
        try: os.remove(path)
        except Exception: pass

def _flag_s(key, default='0'):
    return str(get_setting(key, default)) == '1'

def process_int_setting(message, key, lo, hi, label):
    if not message.text or message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    try:
        n = int(float(message.text.strip()))
        if not (lo <= n <= hi): raise ValueError
    except Exception:
        bot.reply_to(message, f"❌ Send a whole number between {lo} and {hi}."); return
    set_setting(key, str(n))
    bot.reply_to(message, f"✅ {label} set to <b>{n}</b>.", parse_mode='HTML')

def get_free_limit():
    try: return int(get_setting('FREE_LIMIT', FREE_USER_LIMIT))
    except Exception: return FREE_USER_LIMIT

def get_max_upload_bytes():
    try: mb = max(1, min(20, int(get_setting('MAX_UPLOAD_MB', 20))))
    except Exception: mb = 20
    return mb * 1024 * 1024

def tool_toggle_view(chat_id, key, title, on_text, off_text, default, back_group=4, cb=None):
    on = _flag_s(key, default)
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🔴 Turn OFF" if on else "🟢 Turn ON", callback_data=f"adt_tog_{key}"))
    m.add(types.InlineKeyboardButton("🔙 Back to Tools", callback_data=f"adm_g{back_group}"))
    bot.send_message(chat_id, f"{title}\n\nStatus: <b>{'ON ✅' if on else 'OFF ❌'}</b>\n{_e(on_text if on else off_text)}", parse_mode='HTML', reply_markup=m)

TOGGLES = {
    'AUTO_BACKUP':      ("🕒 <b>Auto-Backup</b>", "A database backup is sent to the owner every 24 hours.", "No automatic backups.", '0'),
    'REG_OPEN':         ("🆕 <b>New Registrations</b>", "New users can start the bot.", "New users are blocked (existing users unaffected).", '1'),
    'NOTIFY_NEW_USERS': ("🔔 <b>New-User Alerts</b>", "The owner is notified when someone joins.", "No join notifications.", '1'),
}

def restart_bot_process(chat_id):
    try: bot.send_message(chat_id, "♻️ Restarting the bot process... back in a few seconds.")
    except Exception: pass
    time.sleep(1)
    os.execv(sys.executable, [sys.executable] + sys.argv)

def admin_housekeeping():
    """Daily auto-backup to the owner (if enabled)."""
    while True:
        try:
            if _flag_s('AUTO_BACKUP', '0'):
                last = get_setting('LAST_BACKUP', '')
                due = True
                if last:
                    try: due = datetime.now() - datetime.fromisoformat(last) >= timedelta(hours=24)
                    except Exception: due = True
                if due:
                    send_backup(OWNER_ID, "🕒 Auto-backup")
                    set_setting('LAST_BACKUP', datetime.now().isoformat())
        except Exception as e:
            logger.error(f"auto-backup failed: {e}")
        time.sleep(1800)

def _confirm_view(chat_id, text, yes_cb, group):
    m = types.InlineKeyboardMarkup()
    m.row(types.InlineKeyboardButton("✅ Yes, do it", callback_data=yes_cb), types.InlineKeyboardButton("❌ Cancel", callback_data=f"adm_g{group}"))
    bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=m)

def _ask(chat_id, prompt, handler, *args):
    msg = bot.send_message(chat_id, prompt + "\n\n/cancel to abort.", parse_mode='Markdown')
    bot.register_next_step_handler(msg, handler, *args)

def admin_tools_callback(call):
    data = call.data
    uid = call.from_user.id
    chat_id = call.message.chat.id
    mid = call.message.message_id
    try:
        if data == 'adm_home':
            bot.answer_callback_query(call.id)
            _send_or_edit(chat_id, admin_tools_home_text(), admin_tools_home_markup(), mid); return
        if data.startswith('adm_g'):
            bot.answer_callback_query(call.id)
            txt, mk = _group_view(int(data[5:])); _send_or_edit(chat_id, txt, mk, mid); return
        if not data.startswith('adt_'): return
        key = data[4:]
        base = key.split('_')[0]
        if base in OWNER_ONLY_TOOLS and uid != OWNER_ID:
            bot.answer_callback_query(call.id, "👑 Owner only.", show_alert=True); return
        bot.answer_callback_query(call.id)
        simple = {'server': tool_server, 'running': tool_running, 'hogs': tool_hogs, 'storage': tool_storage, 'info': tool_info,
                  'errors': tool_errors, 'activity': tool_activity, 'report': tool_report, 'premium': tool_premium,
                  'expiring': tool_expiring, 'banned': tool_banned, 'topup': tool_topup, 'inactive': tool_inactive,
                  'plandist': tool_plandist, 'growth': tool_growth, 'exportusers': tool_exportusers, 'clearlogs': tool_clearlogs}
        if key in simple: simple[key](chat_id); return
        if key == 'expiring_remind': tool_expiring_remind(chat_id); return
        if key == 'gift': _ask(chat_id, "🎁 Send: `USER_ID | DAYS`\nExample: `123456789 | 7`", process_gift)
        elif key == 'msguser': _ask(chat_id, "✉️ Send: `USER_ID | message text`", process_msg_user)
        elif key == 'bcpremium': _ask(chat_id, f"📣 Send the message for *{len(_audience('premium'))} premium* users:", process_segment_broadcast, 'premium')
        elif key == 'bcfree': _ask(chat_id, f"📣 Send the message for *{len(_audience('free'))} free* users:", process_segment_broadcast, 'free')
        elif key == 'welcomenote': _ask(chat_id, f"📝 Send the note to show under the /start welcome.\nCurrent: `{(get_setting('WELCOME_NOTE','') or '—')[:100]}`\nSend `-` to clear.", process_welcome_note)
        elif key == 'stopall': _confirm_view(chat_id, f"⚠️ Stop <b>all {len(_running_list())}</b> running scripts?", "adt_stopall_yes", 3)
        elif key == 'stopall_yes': tool_stopall_do(chat_id)
        elif key == 'restartall': _confirm_view(chat_id, f"⚠️ Restart <b>all {len(_running_list())}</b> running scripts?", "adt_restartall_yes", 3)
        elif key == 'restartall_yes': threading.Thread(target=tool_restartall_do, args=(chat_id, call.message), daemon=True).start()
        elif key == 'stopuser': _ask(chat_id, "🛑 Send the *user ID* whose bots should be stopped:", process_stop_user)
        elif key == 'search': _ask(chat_id, "🔎 Send part of a project or file name:", process_search_project)
        elif key == 'backup': send_backup(chat_id)
        elif key == 'autobackup': tool_toggle_view(chat_id, 'AUTO_BACKUP', *TOGGLES['AUTO_BACKUP'])
        elif key == 'reg': tool_toggle_view(chat_id, 'REG_OPEN', *TOGGLES['REG_OPEN'])
        elif key == 'newalerts': tool_toggle_view(chat_id, 'NOTIFY_NEW_USERS', *TOGGLES['NOTIFY_NEW_USERS'])
        elif key.startswith('tog_'):
            k = key[4:]
            if k == 'AUTO_BACKUP' and uid != OWNER_ID:
                bot.send_message(chat_id, "👑 Owner only."); return
            if k in TOGGLES:
                set_setting(k, '0' if _flag_s(k, TOGGLES[k][3]) else '1')
                try: bot.delete_message(chat_id, mid)
                except Exception: pass
                tool_toggle_view(chat_id, k, *TOGGLES[k])
        elif key == 'freelimit': _ask(chat_id, f"📦 Send the project limit for *free users* (0-100).\nCurrent: `{get_free_limit()}`", process_int_setting, 'FREE_LIMIT', 0, 100, 'Free project limit')
        elif key == 'maxupload': _ask(chat_id, f"📏 Send the max upload size in *MB* (1-20, Telegram's bot limit).\nCurrent: `{get_max_upload_bytes() // 1048576}`", process_int_setting, 'MAX_UPLOAD_MB', 1, 20, 'Max upload size (MB)')
        elif key == 'restartbot': _confirm_view(chat_id, "⚠️ <b>Restart the whole bot process?</b>\nRunning user scripts may be interrupted.", "adt_restartbot_yes", 4)
        elif key == 'restartbot_yes': restart_bot_process(chat_id)
    except Exception as e:
        logger.error(f"Admin tool error ({data}): {e}", exc_info=True)
        try: bot.send_message(chat_id, f"❌ Tool error: {_e(e)}", parse_mode='HTML')
        except Exception: pass


# ============================================================
# --- Admin Callbacks ---
# ============================================================
def subscription_management_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("💳 *Subscription Management*\nSelect action:",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=create_subscription_menu(), parse_mode='Markdown')
    except Exception as e: logger.error(f"Error showing sub menu: {e}")

def stats_callback(call):
    bot.answer_callback_query(call.id)
    _logic_statistics(call.message)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                      reply_markup=create_main_menu_inline(call.from_user.id))
    except Exception: pass

def _set_lock_state(call, locked):
    global bot_locked
    bot_locked = locked
    user_id = call.from_user.id
    logger.warning(f"Bot {'locked' if locked else 'unlocked'} by Admin {user_id}")
    bot.answer_callback_query(call.id, "🔒 Bot is now Locked." if locked else "🔓 Bot is now Unlocked.")
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    menu_text = (f"〽️ *Main Menu*\n\n"
                 f"🆔 ID: `{user_id}`\n"
                 f"🔰 Status: 🛡️ Admin\n"
                 f"📁 Files: *{current_files} / {limit_str}*\n\n"
                 f"{'🔒 *Bot has been Locked.*' if locked else '🔓 *Bot has been Unlocked.*'}\n"
                 f"👇 Use the menu buttons below.")
    try:
        bot.edit_message_text(menu_text, call.message.chat.id, call.message.message_id,
                              reply_markup=create_main_menu_inline(user_id), parse_mode='Markdown')
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error updating inline keyboard after lock toggle: {e}")
    except Exception as e:
        logger.error(f"Error in lock toggle callback: {e}")
    try:
        bot.send_message(call.message.chat.id,
                         "🔒 Bot locked. Reply keyboard updated." if locked else "🔓 Bot unlocked. Reply keyboard updated.",
                         reply_markup=create_reply_keyboard_main_menu(user_id))
    except Exception as e:
        logger.error(f"Error refreshing reply keyboard after lock toggle: {e}")

def lock_bot_callback(call): _set_lock_state(call, True)
def unlock_bot_callback(call): _set_lock_state(call, False)

def run_all_scripts_callback(call):
    _logic_run_all_scripts(call)

def broadcast_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📢 Send message to broadcast.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def admin_panel_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text(_admin_panel_text(),
                              call.message.chat.id, call.message.message_id,
                              reply_markup=create_admin_panel(), parse_mode='Markdown')
    except Exception as e: logger.error(f"Error showing admin panel: {e}")

def add_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "👑 Enter User ID to promote to Admin.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_add_admin_id)

def process_add_admin_id(message):
    if message.from_user.id != OWNER_ID: bot.reply_to(message, "⚠️ Owner only."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Admin promotion cancelled."); return
    try:
        new_admin_id = int(message.text.strip())
        if new_admin_id <= 0: raise ValueError("ID must be positive")
        if new_admin_id == OWNER_ID: bot.reply_to(message, "⚠️ Owner is already Owner."); return
        if new_admin_id in admin_ids: bot.reply_to(message, f"⚠️ User `{new_admin_id}` is already an Admin.", parse_mode='Markdown'); return
        add_admin_db(new_admin_id)
        bot.reply_to(message, f"✅ User `{new_admin_id}` promoted to Admin.", parse_mode='Markdown')
        try: bot.send_message(new_admin_id, f"🎉 Congrats! You are now <b>{_adm_rank(new_admin_id)}</b>.\nOpen <b>👑 Admin Panel</b> — you will see the tools the owner gave you (tap 🔑 My Access to review).", parse_mode='HTML')
        except Exception: pass
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID. Send numerical ID or /cancel.")
        msg = bot.send_message(message.chat.id, "👑 Enter User ID to promote or /cancel.")
        bot.register_next_step_handler(msg, process_add_admin_id)
    except Exception as e: logger.error(f"Error adding admin: {e}"); bot.reply_to(message, "❌ Error.")

def remove_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "👑 Enter User ID of Admin to remove.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_remove_admin_id)

def process_remove_admin_id(message):
    if message.from_user.id != OWNER_ID: bot.reply_to(message, "⚠️ Owner only."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Admin removal cancelled."); return
    try:
        admin_id_remove = int(message.text.strip())
        if admin_id_remove <= 0: raise ValueError("ID must be positive")
        if admin_id_remove == OWNER_ID: bot.reply_to(message, "⚠️ Cannot remove Owner."); return
        if admin_id_remove not in admin_ids: bot.reply_to(message, f"⚠️ User `{admin_id_remove}` is not an Admin.", parse_mode='Markdown'); return
        if remove_admin_db(admin_id_remove):
            bot.reply_to(message, f"✅ Admin `{admin_id_remove}` removed.", parse_mode='Markdown')
            try: bot.send_message(admin_id_remove, "ℹ️ You are no longer an Admin.")
            except Exception: pass
        else: bot.reply_to(message, f"❌ Failed to remove admin `{admin_id_remove}`.", parse_mode='Markdown')
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID. Send numerical ID or /cancel.")
        msg = bot.send_message(message.chat.id, "👑 Enter Admin ID to remove or /cancel.")
        bot.register_next_step_handler(msg, process_remove_admin_id)
    except Exception as e: logger.error(f"Error removing admin: {e}"); bot.reply_to(message, "❌ Error.")

def list_admins_callback(call):
    bot.answer_callback_query(call.id)
    try:
        admin_list_str = "\n".join(
            f"• `{aid}` {_adm_rank(aid)}"
            for aid in sorted(list(admin_ids))
        )
        if not admin_list_str: admin_list_str = "(No admins configured)"
        bot.edit_message_text(f"👑 *Current Admins:*\n\n{admin_list_str}",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=create_admin_panel(), parse_mode='Markdown')
    except Exception as e: logger.error(f"Error listing admins: {e}")

def add_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Enter User ID & days (e.g., `12345678 30`).\n/cancel to abort.", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_add_subscription_details)

def process_add_subscription_details(message):
    if message.from_user.id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Sub add cancelled."); return
    try:
        parts = message.text.split()
        if len(parts) != 2: raise ValueError("Incorrect format")
        sub_user_id = int(parts[0].strip()); days = int(parts[1].strip())
        if sub_user_id <= 0 or days <= 0: raise ValueError("User ID/days must be positive")
        _g = _ar_guard(message.from_user.id, 'grant', days)
        if _g: bot.reply_to(message, _g); return
        current_expiry = user_subscriptions.get(sub_user_id, {}).get('expiry')
        start_date = datetime.now()
        if current_expiry and current_expiry > start_date: start_date = current_expiry
        new_expiry = start_date + timedelta(days=days)
        save_subscription(sub_user_id, new_expiry)
        bot.reply_to(message, f"✅ Sub for `{sub_user_id}` extended by `{days}` days.\nNew expiry: `{new_expiry:%Y-%m-%d}`", parse_mode='Markdown')
        try: bot.send_message(sub_user_id, f"🎉 Sub activated/extended by {days} days! Expires: `{new_expiry:%Y-%m-%d}`.", parse_mode='Markdown')
        except Exception: pass
    except ValueError as e:
        bot.reply_to(message, f"⚠️ Invalid: {md_escape(e)}. Format: `ID days` or /cancel.", parse_mode='Markdown')
        msg = bot.send_message(message.chat.id, "💳 Enter User ID & days, or /cancel.")
        bot.register_next_step_handler(msg, process_add_subscription_details)
    except Exception as e: logger.error(f"Error adding sub: {e}"); bot.reply_to(message, "❌ Error.")

def remove_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Enter User ID to remove sub.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_remove_subscription_id)

def process_remove_subscription_id(message):
    if message.from_user.id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Sub removal cancelled."); return
    try:
        sub_user_id = int(message.text.strip())
        if sub_user_id not in user_subscriptions: bot.reply_to(message, f"⚠️ User `{sub_user_id}` has no active sub.", parse_mode='Markdown'); return
        remove_subscription_db(sub_user_id)
        bot.reply_to(message, f"✅ Sub for `{sub_user_id}` removed.", parse_mode='Markdown')
        try: bot.send_message(sub_user_id, "ℹ️ Your subscription was removed by admin.")
        except Exception: pass
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID. Send numerical ID or /cancel.")
        msg = bot.send_message(message.chat.id, "💳 Enter User ID to remove sub, or /cancel.")
        bot.register_next_step_handler(msg, process_remove_subscription_id)
    except Exception as e: logger.error(f"Error removing sub: {e}"); bot.reply_to(message, "❌ Error.")

def check_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Enter User ID to check sub.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_check_subscription_id)

def process_check_subscription_id(message):
    if message.from_user.id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Sub check cancelled."); return
    try:
        sub_user_id = int(message.text.strip())
        if sub_user_id in user_subscriptions:
            expiry_dt = user_subscriptions[sub_user_id].get('expiry')
            plan = _md(get_plan_label(sub_user_id))
            if expiry_dt:
                if expiry_dt > datetime.now():
                    days_left = (expiry_dt - datetime.now()).days
                    bot.reply_to(message, f"✅ User `{sub_user_id}` has active sub (*{plan}*).\nExpires: `{expiry_dt:%Y-%m-%d %H:%M}` (`{days_left}` days left).", parse_mode='Markdown')
                else:
                    bot.reply_to(message, f"⚠️ User `{sub_user_id}` sub expired on `{expiry_dt:%Y-%m-%d}`.", parse_mode='Markdown')
                    remove_subscription_db(sub_user_id)
            else: bot.reply_to(message, f"⚠️ User `{sub_user_id}` in sub list but expiry missing.", parse_mode='Markdown')
        else: bot.reply_to(message, f"ℹ️ User `{sub_user_id}` has no subscription.", parse_mode='Markdown')
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID. Send numerical ID or /cancel.")
        msg = bot.send_message(message.chat.id, "💳 Enter User ID to check, or /cancel.")
        bot.register_next_step_handler(msg, process_check_subscription_id)
    except Exception as e: logger.error(f"Error checking sub: {e}"); bot.reply_to(message, "❌ Error.")

# ============================================================
# --- User Management Callbacks ---
# ============================================================
def user_management_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text(
            "👥 *User Management*\nSelect an action:",
            call.message.chat.id, call.message.message_id,
            reply_markup=create_user_management_menu(), parse_mode='Markdown'
        )
    except Exception as e: logger.error(f"Error showing user management: {e}")

def view_user_files_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔍 Enter User ID to view their files:\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_view_user_files_id)

def ban_user_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id,
                           "🚫 Enter User ID and reason to ban.\n"
                           "Format: `user_id reason`\nExample: `12345678 Spamming`\n/cancel to abort.",
                           parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_ban_user)

def process_ban_user(message):
    admin_id = message.from_user.id
    if admin_id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Ban cancelled."); return
    try:
        parts = message.text.strip().split(None, 1)
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Format: `user_id reason`\nExample: `12345678 Spamming`", parse_mode='Markdown')
            return
        user_id = int(parts[0])
        reason = parts[1]
        if user_id <= 0: raise ValueError("ID must be positive")
        if user_id == OWNER_ID: bot.reply_to(message, "⚠️ Cannot ban the Owner."); return
        if user_id in admin_ids: bot.reply_to(message, "⚠️ Cannot ban an Admin."); return
        if ban_user_db(user_id, reason, admin_id):
            bot.reply_to(message, f"✅ User `{user_id}` banned.\n📝 Reason: {reason}", parse_mode='Markdown')
            for project_name, _, _ in user_files.get(user_id, []):
                script_key = f"{user_id}_{project_name}"
                if script_key in bot_scripts:
                    kill_process_tree(bot_scripts[script_key])
                    del bot_scripts[script_key]
            try: bot.send_message(user_id, f"🚫 You have been banned from this bot.\nReason: {reason}")
            except Exception: pass
        else:
            bot.reply_to(message, "❌ Failed to ban user.")
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid user ID. Must be a number.")
    except Exception as e:
        logger.error(f"Error banning user: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)}")

def unban_user_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "✅ Enter User ID to unban.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_unban_user)

def process_unban_user(message):
    admin_id = message.from_user.id
    if admin_id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Unban cancelled."); return
    try:
        user_id = int(message.text.strip())
        if user_id not in banned_users:
            bot.reply_to(message, f"ℹ️ User `{user_id}` is not banned.", parse_mode='Markdown'); return
        if unban_user_db(user_id):
            bot.reply_to(message, f"✅ User `{user_id}` has been unbanned.", parse_mode='Markdown')
            try: bot.send_message(user_id, "✅ Your ban has been lifted. You can use the bot again.")
            except Exception: pass
        else:
            bot.reply_to(message, "❌ Failed to unban user.")
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid user ID. Must be a number.")
    except Exception as e:
        logger.error(f"Error unbanning user: {e}"); bot.reply_to(message, f"❌ Error: {str(e)}")

def user_info_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "👤 Enter User ID to get info.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_user_info)

def process_user_info(message):
    if message.from_user.id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Info request cancelled."); return
    try:
        user_id = int(message.text.strip())
        if user_id <= 0: raise ValueError("ID must be positive")
        parts = [f"👤 *User ID:* `{user_id}`"]
        if user_id == OWNER_ID: parts.append("👑 *Status:* Owner")
        elif user_id in admin_ids: parts.append("🛡️ *Status:* Admin")
        elif user_id in banned_users: parts.append("🚫 *Status:* Banned")
        elif user_id in user_subscriptions:
            expiry = user_subscriptions[user_id].get('expiry')
            if expiry and expiry > datetime.now():
                days_left = (expiry - datetime.now()).days
                parts.append(f"⭐ *Status:* {_md(get_plan_label(user_id))} (Expires in `{days_left}` days)")
            else: parts.append("🆓 *Status:* Free User (Expired sub)")
        else: parts.append("🆓 *Status:* Free User")
        file_count = get_user_file_count(user_id)
        file_limit = get_user_file_limit(user_id)
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        parts.append(f"📁 *Files:* `{file_count}/{limit_str}`")
        if user_id in user_limits: parts.append(f"⚙️ *Custom Limit:* `{user_limits[user_id]}`")
        running = sum(1 for pn, _, _ in user_files.get(user_id, []) if is_bot_running(user_id, pn))
        parts.append(f"🤖 *Running Scripts:* `{running}`")
        if user_id in active_users: parts.append("🟢 *Activity:* Active user")
        bot.reply_to(message, "\n".join(parts), parse_mode='Markdown')
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid user ID. Must be a number.")
    except Exception as e:
        logger.error(f"Error getting user info: {e}"); bot.reply_to(message, f"❌ Error: {str(e)}")

def all_users_callback(call):
    bot.answer_callback_query(call.id)
    try:
        if not active_users:
            bot.edit_message_text("👥 *No active users yet.*", call.message.chat.id,
                                  call.message.message_id, parse_mode='Markdown')
            return
        users_list = list(active_users)
        chunk_size = 20
        total_pages = (len(users_list) + chunk_size - 1) // chunk_size
        display_users_list(call.message.chat.id, call.message.message_id, users_list, 0, total_pages, chunk_size)
    except Exception as e:
        logger.error(f"Error displaying all users: {e}")

def display_users_list(chat_id, message_id, users_list, page, total_pages, chunk_size):
    start_idx = page * chunk_size
    end_idx = min(start_idx + chunk_size, len(users_list))
    user_chunk = users_list[start_idx:end_idx]
    msg_text = f"👥 *Active Users* (Page `{page + 1}/{total_pages}`)\n"
    msg_text += f"📊 Total: `{len(users_list)}` | 🚫 Banned: `{len(banned_users)}`\n\n"
    msg_text += "👇 Tap any user to open their file control panel:"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid in user_chunk:
        if uid == OWNER_ID: s = "👑"
        elif uid in admin_ids: s = "🛡️"
        elif uid in banned_users: s = "🚫"
        elif has_active_sub(uid): s = "⭐"
        else: s = "🆓"
        file_count = get_user_file_count(uid)
        running = sum(1 for pn, _, _ in user_files.get(uid, []) if is_bot_running(uid, pn))
        markup.add(types.InlineKeyboardButton(
            f"{s} {uid}  |  📁 {file_count}  |  🟢 {running}",
            callback_data=f"admin_user_files_{uid}"
        ))
    if total_pages > 1:
        page_buttons = []
        if page > 0:
            page_buttons.append(types.InlineKeyboardButton("⬅️", callback_data=f"users_page_{page-1}"))
        page_buttons.append(types.InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            page_buttons.append(types.InlineKeyboardButton("➡️", callback_data=f"users_page_{page+1}"))
        markup.row(*page_buttons)
    markup.row(types.InlineKeyboardButton("🔙 Back to User Mgmt", callback_data='user_management'))
    try:
        bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode='Markdown')
    except Exception as e: logger.error(f"Error editing users list: {e}")

def admin_user_files_callback(call):
    """Open full file control panel for a user clicked from All Users list."""
    bot.answer_callback_query(call.id)
    try:
        target_user_id = int(call.data.split('_')[3])
        _show_user_files_admin_inline(call.message.chat.id, call.message.message_id, target_user_id)
    except Exception as e:
        logger.error(f"Error in admin_user_files_callback: {e}")

def _show_user_files_admin_inline(chat_id, message_id, target_user_id):
    """Show full file control panel for a user (edits current message)."""
    files_list = user_files.get(target_user_id, [])
    if target_user_id == OWNER_ID: s = "👑 Owner"
    elif target_user_id in admin_ids: s = _adm_rank(target_user_id)
    elif target_user_id in banned_users: s = "🚫 Banned"
    elif has_active_sub(target_user_id): s = f"⭐ {_md(get_plan_label(target_user_id))}"
    else: s = "🆓 Free User"
    running_count = sum(1 for pn, _, _ in files_list if is_bot_running(target_user_id, pn))
    file_limit = get_user_file_limit(target_user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "∞"
    text = (f"👤 *User Project Control Panel*\n\n"
            f"🆔 ID: `{target_user_id}`\n"
            f"🔰 Status: {s}\n"
            f"📁 Projects: `{len(files_list)}/{limit_str}` | 🟢 Running: `{running_count}`\n\n")
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not files_list:
        text += "_(No projects uploaded yet)_"
    else:
        text += "Tap a project to manage:"
        for project_name, main_file, file_type in sorted(files_list):
            is_running = is_bot_running(target_user_id, project_name)
            status_icon = "🟢" if is_running else "🔴"
            markup.add(types.InlineKeyboardButton(
                f"{status_icon} {project_name}",
                callback_data=f"umfile_{target_user_id}_{project_name}"
            ))
    markup.row(types.InlineKeyboardButton("🔙 Back to All Users", callback_data='all_users'))
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error showing user files admin inline: {e}")
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')

def handle_users_page(call):
    try:
        page = int(call.data.split('_')[2])
        users_list = list(active_users)
        chunk_size = 20
        total_pages = (len(users_list) + chunk_size - 1) // chunk_size
        if 0 <= page < total_pages:
            bot.answer_callback_query(call.id)
            display_users_list(call.message.chat.id, call.message.message_id, users_list, page, total_pages, chunk_size)
    except Exception as e:
        logger.error(f"Error handling users page: {e}")
        bot.answer_callback_query(call.id, "Error.", show_alert=True)

def set_user_limit_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id,
                           "🔧 Enter User ID and new limit.\nFormat: `user_id limit`\n/cancel to abort.",
                           parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_set_user_limit)

def pending_files_callback(call):
    bot.answer_callback_query(call.id)
    _show_pending_files(call.message.chat.id, call.message.message_id)

def _show_pending_files(chat_id, message_id=None):
    """Show users who have pending files awaiting admin approval."""
    users_with_pending = set()
    for uid, files in pending_script_files.items():
        if files: users_with_pending.add(uid)
    for uid, files in pending_zip_files.items():
        if files: users_with_pending.add(uid)

    back_markup = types.InlineKeyboardMarkup()
    back_markup.row(types.InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main'))

    if not users_with_pending:
        text = "📋 *Pending Files*\n\n✅ No files awaiting approval."
        if message_id:
            try: bot.edit_message_text(text, chat_id, message_id, reply_markup=back_markup, parse_mode='Markdown')
            except Exception: bot.send_message(chat_id, text, reply_markup=back_markup, parse_mode='Markdown')
        else:
            bot.send_message(chat_id, text, reply_markup=back_markup, parse_mode='Markdown')
        return

    total_files = sum(
        len(pending_script_files.get(uid, {})) + len(pending_zip_files.get(uid, {}))
        for uid in users_with_pending
    )
    text = (f"📋 *Pending Files*\n\n"
            f"📊 `{total_files}` file(s) from `{len(users_with_pending)}` user(s) awaiting review\n\n"
            f"👇 Tap a user to review their files:")

    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid in sorted(users_with_pending):
        script_count = len(pending_script_files.get(uid, {}))
        zip_count = len(pending_zip_files.get(uid, {}))
        total = script_count + zip_count
        has_danger = (
            any(not info.get('is_safe', True) for info in pending_script_files.get(uid, {}).values())
            or any(
                bool(entry.get('patterns')) if isinstance(entry, dict) else False
                for entry in pending_zip_files.get(uid, {}).values()
            )
        )
        danger_icon = "🚨 " if has_danger else "📁 "
        markup.add(types.InlineKeyboardButton(
            f"{danger_icon}User {uid} — {total} file(s)" + (" [DANGER]" if has_danger else ""),
            callback_data=f"pending_user_{uid}"
        ))
    markup.row(types.InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main'))

    if message_id:
        try: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode='Markdown')
        except Exception: bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')

def _show_pending_user_files(chat_id, message_id, target_user_id):
    """Show all pending files for a specific user with security details, approve/reject, and chat."""
    script_files = dict(pending_script_files.get(target_user_id, {}))
    zip_files_dict = dict(pending_zip_files.get(target_user_id, {}))

    back_markup = types.InlineKeyboardMarkup()
    back_markup.row(types.InlineKeyboardButton("🔙 Back to Pending", callback_data='pending_files'))

    if not script_files and not zip_files_dict:
        try: bot.edit_message_text(f"✅ No pending projects for User `{target_user_id}`.", chat_id, message_id, reply_markup=back_markup, parse_mode='Markdown')
        except Exception: bot.send_message(chat_id, f"✅ No pending projects for User `{target_user_id}`.", reply_markup=back_markup, parse_mode='Markdown')
        return

    text = f"📋 *Pending Projects — User* `{target_user_id}`\n\n"
    markup = types.InlineKeyboardMarkup(row_width=2)

    for project_name, info in script_files.items():
        ftype = info.get('type', '?')
        main_file = info.get('main_file', project_name)
        is_safe = info.get('is_safe', True)
        security_msg_raw = info.get('security_msg', '')

        if is_safe:
            safety_line = "🛡️ Security: ✅ *Safe*"
        else:
            file_path = info.get('path', '')
            found_patterns = []
            if file_path and os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    found_patterns = [p for p in DANGEROUS_PATTERNS if re.search(p, content, re.IGNORECASE)]
                except Exception:
                    pass
            if found_patterns:
                pattern_lines = '\n'.join(f"  ⚠️ `{p}`" for p in found_patterns[:15])
                if len(found_patterns) > 15:
                    pattern_lines += f"\n  ... and `{len(found_patterns) - 15}` more"
                safety_line = f"🚨 *DANGEROUS* — `{len(found_patterns)}` pattern(s):\n{pattern_lines}"
            else:
                safety_line = f"🚨 *DANGEROUS*\n  ⚠️ `{security_msg_raw}`"

        text += f"📦 *Project:* `{project_name}`\n📄 *Main File:* `{main_file}` (`{ftype}`)\n{safety_line}\n\n"
        danger_label = "🚨 " if not is_safe else ""
        markup.add(types.InlineKeyboardButton(f"📦 {danger_label}{project_name}", callback_data='noop'))
        markup.row(
            types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_file_{target_user_id}_{project_name}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_file_{target_user_id}_{project_name}")
        )

    for project_name, zip_entry in zip_files_dict.items():
        zip_found_patterns = zip_entry.get('patterns', []) if isinstance(zip_entry, dict) else []
        main_file = zip_entry.get('main_file', '(auto-detect)') if isinstance(zip_entry, dict) else '(auto-detect)'
        file_name_zip = zip_entry.get('file_name_zip', f"{project_name}.zip") if isinstance(zip_entry, dict) else f"{project_name}.zip"

        if zip_found_patterns:
            zip_pattern_lines = '\n'.join(f"  ⚠️ `{p}`" for p in zip_found_patterns[:15])
            if len(zip_found_patterns) > 15:
                zip_pattern_lines += f"\n  ... and `{len(zip_found_patterns) - 15}` more"
            zip_safety_line = f"🚨 *DANGEROUS* — `{len(zip_found_patterns)}` pattern(s):\n{zip_pattern_lines}"
            zip_danger_label = "🚨 "
        else:
            zip_safety_line = "🛡️ Security: ✅ *Safe*"
            zip_danger_label = ""

        text += f"📦 *Project:* `{project_name}`\n📁 *Archive:* `{file_name_zip}`\n📄 *Main File:* `{main_file or '(auto-detect)'}`\n{zip_safety_line}\n\n"
        markup.add(types.InlineKeyboardButton(f"📦 {zip_danger_label}{project_name}", callback_data='noop'))
        markup.row(
            types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_zip_{target_user_id}_{project_name}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_zip_{target_user_id}_{project_name}")
        )

    markup.row(types.InlineKeyboardButton(f"💬 Chat with User {target_user_id}", callback_data=f"chat_user_{target_user_id}"))
    markup.row(types.InlineKeyboardButton("🔙 Back to Pending Users", callback_data='pending_files'))

    try: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode='Markdown')
    except Exception: bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')

def pending_user_callback(call):
    """Handle click on a user in the pending files list."""
    try: bot.answer_callback_query(call.id)
    except Exception: pass
    try:
        target_user_id = int(call.data.split('_')[2])
        threading.Thread(
            target=_show_pending_user_files,
            args=(call.message.chat.id, call.message.message_id, target_user_id),
            daemon=True
        ).start()
    except Exception as e:
        logger.error(f"Error in pending_user_callback: {e}")

def chat_user_callback(call):
    """Allow admin to send a chat message to a user."""
    bot.answer_callback_query(call.id)
    try:
        target_user_id = int(call.data.split('_')[2])
        msg = bot.send_message(
            call.message.chat.id,
            f"💬 *Send message to User* `{target_user_id}`\n\nType your message below, or /cancel to abort.",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(msg, lambda m: process_admin_chat_user(m, target_user_id))
    except Exception as e:
        logger.error(f"Error in chat_user_callback: {e}")

def process_admin_chat_user(message, target_user_id):
    """Process and send admin's message to a user."""
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Message cancelled."); return
    try:
        bot.send_message(target_user_id,
                         f"📨 *Message from Admin:*\n\n{message.text or '(Media message)'}",
                         parse_mode='Markdown')
        bot.reply_to(message, f"✅ Message sent to User `{target_user_id}` successfully.", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to deliver message: `{md_escape(e)}`", parse_mode='Markdown')

def process_set_user_limit(message):
    if message.from_user.id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    try:
        parts = message.text.split()
        if len(parts) != 2: raise ValueError("Format: user_id limit")
        user_id = int(parts[0]); limit = int(parts[1])
        if user_id <= 0 or limit <= 0: raise ValueError("ID and limit must be positive")
        _g = _ar_guard(message.from_user.id, 'setlimit', limit)
        if _g: bot.reply_to(message, _g); return
        if set_user_limit_db(user_id, limit, message.from_user.id):
            bot.reply_to(message, f"✅ File limit set to `{limit}` for user `{user_id}`.", parse_mode='Markdown')
            try: bot.send_message(user_id, f"⚙️ Your file limit has been set to `{limit}`.", parse_mode='Markdown')
            except Exception: pass
        else: bot.reply_to(message, "❌ Failed to set limit.")
    except ValueError as e:
        bot.reply_to(message, f"⚠️ Invalid input: {md_escape(e)}\nFormat: `user_id limit`", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error setting limit: {e}"); bot.reply_to(message, f"❌ Error: {str(e)}")

def remove_user_limit_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🗑️ Enter User ID to remove custom limit.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_remove_user_limit)

def process_remove_user_limit(message):
    if message.from_user.id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    try:
        user_id = int(message.text.strip())
        if user_id not in user_limits:
            bot.reply_to(message, f"ℹ️ User `{user_id}` has no custom limit.", parse_mode='Markdown'); return
        if remove_user_limit_db(user_id):
            bot.reply_to(message, f"✅ Custom limit removed for user `{user_id}`.", parse_mode='Markdown')
            try: bot.send_message(user_id, "⚙️ Your custom file limit has been removed.")
            except Exception: pass
        else: bot.reply_to(message, "❌ Failed to remove limit.")
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid user ID. Must be a number.")
    except Exception as e:
        logger.error(f"Error removing limit: {e}"); bot.reply_to(message, f"❌ Error: {str(e)}")

# ============================================================
# --- File Approval Callbacks ---
# ============================================================
def process_approve_file(call):
    """Approve a pending .py or .js file."""
    data_parts = call.data.split('_', 3)
    if len(data_parts) < 4:
        bot.answer_callback_query(call.id, "❌ Invalid data.", show_alert=True); return
    user_id = int(data_parts[2])
    project_name = data_parts[3]
    if user_id not in pending_script_files or project_name not in pending_script_files[user_id]:
        bot.answer_callback_query(call.id, "❌ Pending entry not found.", show_alert=True); return
    entry = pending_script_files[user_id][project_name]
    file_path = entry['path']
    file_type = entry['type']
    main_file = entry.get('main_file', os.path.basename(file_path))
    project_folder = os.path.dirname(file_path)
    if not os.path.exists(file_path):
        bot.answer_callback_query(call.id, "❌ File not found.", show_alert=True); return
    try:
        if file_type == 'js': handle_js_file(file_path, user_id, project_folder, main_file, call.message, project_name)
        elif file_type == 'py': handle_py_file(file_path, user_id, project_folder, main_file, call.message, project_name)
        del pending_script_files[user_id][project_name]
        if not pending_script_files[user_id]: del pending_script_files[user_id]
        remove_pending_script_db(user_id, project_name)
        bot.answer_callback_query(call.id, "✅ Project approved!")
        bot.edit_message_text(M('approved_admin', project=project_name, user=user_id),
                              call.message.chat.id, call.message.message_id)
        try: bot.send_message(user_id, M('approved_user', project=project_name))
        except Exception: pass
        remaining = len(pending_script_files.get(user_id, {})) + len(pending_zip_files.get(user_id, {}))
        if remaining > 0:
            try: _show_pending_user_files(call.message.chat.id, call.message.message_id, user_id)
            except Exception: pass
    except Exception as e:
        logger.error(f"Error processing approved file: {e}")
        bot.answer_callback_query(call.id, "❌ Error processing file.", show_alert=True)

def process_reject_file(call):
    """Reject a pending .py or .js file."""
    data_parts = call.data.split('_', 3)
    if len(data_parts) < 4:
        bot.answer_callback_query(call.id, "❌ Invalid data.", show_alert=True); return
    user_id = int(data_parts[2])
    project_name = data_parts[3]
    if user_id in pending_script_files and project_name in pending_script_files[user_id]:
        entry = pending_script_files[user_id][project_name]
        file_path = entry.get('path', '')
        if file_path and os.path.exists(file_path):
            try: os.remove(file_path)
            except Exception as e: logger.error(f"Error deleting rejected file: {e}")
        del pending_script_files[user_id][project_name]
        if not pending_script_files[user_id]: del pending_script_files[user_id]
        remove_pending_script_db(user_id, project_name)
    bot.answer_callback_query(call.id, "❌ Project rejected!")
    bot.edit_message_text(f"❌ Project `{project_name}` rejected for user `{user_id}`.",
                          call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    try: bot.send_message(user_id, f"❌ Your project `{project_name}` was rejected for security reasons.", parse_mode='Markdown')
    except Exception: pass
    remaining = len(pending_script_files.get(user_id, {})) + len(pending_zip_files.get(user_id, {}))
    if remaining > 0:
        try: _show_pending_user_files(call.message.chat.id, call.message.message_id, user_id)
        except Exception: pass

def process_approve_zip(call):
    """Approve a pending ZIP file."""
    data_parts = call.data.split('_', 3)
    if len(data_parts) < 4:
        bot.answer_callback_query(call.id, "❌ Invalid data.", show_alert=True); return
    user_id = int(data_parts[2])
    project_name = data_parts[3]
    if user_id in pending_zip_files and project_name in pending_zip_files[user_id]:
        zip_entry = pending_zip_files[user_id][project_name]
        file_content = zip_entry['content'] if isinstance(zip_entry, dict) else zip_entry
        file_name_zip = zip_entry.get('file_name_zip', f"{project_name}.zip") if isinstance(zip_entry, dict) else f"{project_name}.zip"
        main_file = zip_entry.get('main_file') if isinstance(zip_entry, dict) else None
        user_folder = get_user_folder(user_id)
        try:
            del pending_zip_files[user_id][project_name]
            if not pending_zip_files[user_id]: del pending_zip_files[user_id]
            remove_pending_zip_db(user_id, project_name)
            bot.answer_callback_query(call.id, "✅ Archive approved!")
            bot.edit_message_text(M('zip_approved_admin', project=project_name, user=user_id),
                                  call.message.chat.id, call.message.message_id)
            try: bot.send_message(user_id, M('zip_approved_user', project=project_name))
            except Exception: pass
            threading.Thread(target=process_zip_file, args=(file_content, file_name_zip, user_id, user_folder, call.message, project_name, main_file)).start()
        except Exception as e:
            logger.error(f"Error processing approved zip: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "❌ Error processing archive.", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "❌ File content not found. Ask user to re-upload.", show_alert=True)

def process_reject_zip(call):
    """Reject a pending ZIP file."""
    data_parts = call.data.split('_', 3)
    if len(data_parts) < 4:
        bot.answer_callback_query(call.id, "❌ Invalid data.", show_alert=True); return
    user_id = int(data_parts[2])
    project_name = data_parts[3]
    if user_id in pending_zip_files and project_name in pending_zip_files[user_id]:
        del pending_zip_files[user_id][project_name]
        if not pending_zip_files[user_id]: del pending_zip_files[user_id]
        remove_pending_zip_db(user_id, project_name)
    bot.answer_callback_query(call.id, "❌ Archive rejected!")
    bot.edit_message_text(f"❌ Archive for project `{project_name}` rejected for user `{user_id}`.",
                          call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    try: bot.send_message(user_id, f"❌ Your project `{project_name}` archive was rejected for security reasons.", parse_mode='Markdown')
    except Exception: pass

# ============================================================
# --- Users Directory (admin): profiles, bots, files, downloads ---
# ============================================================
import html as _hd
import csv as _csv3

_PROFILE_SEEN = {}   # user_id -> ((first_name, username), timestamp)

def touch_user(u):
    """Remember a user's current name/username (cheap: writes only when changed or every 10 min)."""
    try:
        if not u: return
        key = ((u.first_name or ''), (u.username or ''))
        prev = _PROFILE_SEEN.get(u.id)
        if prev and prev[0] == key and time.time() - prev[1] < 600: return
        _PROFILE_SEEN[u.id] = (key, time.time())
        _db_exec("UPDATE active_users SET first_name=?, username=?, last_seen=? WHERE user_id=?",
                 (key[0], key[1], datetime.now().isoformat(), u.id))
    except Exception as e:
        logger.debug(f"touch_user failed: {e}")

def _hx(x):
    return _hd.escape(str(x if x is not None else ''))

def get_profile(uid, fetch=True):
    """(first_name, username, join_date, last_seen) - fetches from Telegram once if unknown."""
    row = _db_q("SELECT first_name, username, join_date, last_seen FROM active_users WHERE user_id=?", (uid,), one=True)
    fn, un, jd, ls = (row if row else (None, None, None, None))
    if not fn and not un and fetch:
        try:
            ch = bot.get_chat(uid)
            fn = (getattr(ch, 'first_name', None) or getattr(ch, 'title', None) or '')
            un = getattr(ch, 'username', None) or ''
            _db_exec("UPDATE active_users SET first_name=?, username=? WHERE user_id=?", (fn, un, uid))
        except Exception:
            fn, un = '', ''
    return (fn or ''), (un or ''), jd, ls

def rank_plain(uid):
    if uid == OWNER_ID: return "👑 Owner"
    if uid in admin_ids: return _adm_rank(uid)
    if has_active_sub(uid): return f"⭐ {get_plan_label(uid)}"
    return "🆓 Free"

def project_bot_username(uid, pn):
    r = _db_q("SELECT bot_username FROM project_meta WHERE user_id=? AND project_name=?", (uid, pn), one=True)
    return r[0] if r and r[0] else ''

def _all_user_ids():
    ids = set(active_users) | set(user_files.keys())
    return sorted(ids)

def _ud_filter(ids, flt, query=None):
    out = []
    q = (query or '').strip().lower().lstrip('@')
    for u in ids:
        files = user_files.get(u, [])
        if flt == 'prem' and not has_active_sub(u): continue
        if flt == 'free' and (has_active_sub(u) or u in admin_ids): continue
        if flt == 'ban' and u not in banned_users: continue
        if flt == 'bots' and not files: continue
        if flt == 'nobots' and files: continue
        if flt == 'adm' and u not in admin_ids: continue
        if q:
            fn, un, _, _ = get_profile(u, fetch=False)
            hay = [str(u), fn.lower(), un.lower()] + [project_bot_username(u, f[0]).lower().lstrip('@') for f in files] + [f[0].lower() for f in files]
            if not any(q in h for h in hay): continue
        out.append(u)
    def sortkey(u):
        r = _db_q("SELECT join_date FROM active_users WHERE user_id=?", (u,), one=True)
        return (r[0] if r and r[0] else '')
    out.sort(key=sortkey, reverse=True)
    return out

UD_FILTERS = [('all', '👥 All'), ('prem', '💎 Premium'), ('free', '🆓 Free'), ('bots', '🤖 With bots'),
              ('nobots', '😴 No bots'), ('ban', '🚫 Banned'), ('adm', '🛡️ Admins')]
UD_PAGE = 8
_UD_SEARCH = {}   # admin_id -> last search query

def _ud_list_view(admin_id, flt='all', page=0):
    q = _UD_SEARCH.get(admin_id)
    ids = _ud_filter(_all_user_ids(), flt, q)
    pages = max(1, (len(ids) + UD_PAGE - 1) // UD_PAGE)
    page = max(0, min(page, pages - 1))
    chunk = ids[page * UD_PAGE:(page + 1) * UD_PAGE]
    total_files = sum(len(v) for v in user_files.values())
    lines = [f"👥 <b>Users Directory</b>", f"Users: <b>{len(_all_user_ids())}</b> • Projects: <b>{total_files}</b> • Showing: <b>{len(ids)}</b>",
             f"Filter: <b>{dict(UD_FILTERS)[flt]}</b>" + (f" • 🔎 <code>{_hx(q)}</code>" if q else ""), ""]
    m = types.InlineKeyboardMarkup(row_width=2)
    for u in chunk:
        fn, un, _, _ = get_profile(u)
        n = len(user_files.get(u, []))
        label = f"{'🚫' if u in banned_users else ''}{(fn or 'User')[:14]}{(' @' + un) if un else ''} · {n}📁 · {rank_plain(u).split(' ')[0]}"
        m.add(types.InlineKeyboardButton(label[:60], callback_data=f"ud_u_{u}"))
    if not chunk: lines.append("<i>No users match.</i>")
    nav = []
    if page > 0: nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"ud_l_{flt}_{page - 1}"))
    nav.append(types.InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1: nav.append(types.InlineKeyboardButton("➡️", callback_data=f"ud_l_{flt}_{page + 1}"))
    m.row(*nav)
    frow = [types.InlineKeyboardButton(("• " if k == flt else "") + lab, callback_data=f"ud_l_{k}_0") for k, lab in UD_FILTERS]
    for i in range(0, len(frow), 3): m.row(*frow[i:i + 3])
    m.row(types.InlineKeyboardButton("🔎 Search" if not q else "🔎 Search (clear)", callback_data="ud_s" if not q else "ud_sc"),
          types.InlineKeyboardButton("📤 Export CSV", callback_data="ud_csv"))
    m.row(types.InlineKeyboardButton("🤖 All Bots", callback_data="ud_bots_0"),
          types.InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel"))
    return "\n".join(lines), m

def _ud_user_view(uid):
    fn, un, jd, ls = get_profile(uid)
    files = sorted(user_files.get(uid, []))
    lim = get_user_file_limit(uid)
    lim_s = "∞" if lim == float('inf') else str(lim)
    sub = user_subscriptions.get(uid)
    lines = [f"👤 <b>{_hx(fn or 'Unknown')}</b>",
             f"🔗 Username: {('@' + _hx(un)) if un else '—'}",
             f"🆔 ID: <code>{uid}</code>",
             f"🏖️ Rank: <b>{_hx(rank_plain(uid))}</b>" + (f" (until {sub['expiry']:%d-%m-%Y})" if sub and has_active_sub(uid) else ""),
             f"📅 Joined: {str(jd)[:10] if jd else '—'} • Last seen: {str(ls)[:16].replace('T', ' ') if ls else '—'}",
             f"📁 Files uploaded: <b>{len(files)}</b> / {lim_s}",
             f"🚫 Banned: <b>{'Yes' if uid in banned_users else 'No'}</b>", ""]
    m = types.InlineKeyboardMarkup(row_width=2)
    if files:
        lines.append("🤖 <b>Projects</b>")
        for pn, mf, ft in files:
            run = is_bot_running(uid, pn)
            bu = project_bot_username(uid, pn)
            lines.append(f"{'🟢' if run else '🔴'} <b>{_hx(pn)}</b> · {('@' + _hx(bu.lstrip('@'))) if bu else 'bot: —'} · <code>{_hx(mf)}</code> ({ft})")
            m.row(types.InlineKeyboardButton(f"📥 {pn}"[:30], callback_data=f"ud_dl_{uid}_{pn}"),
                  types.InlineKeyboardButton("🛠 Manage", callback_data=f"file_{uid}_{pn}"))
        m.add(types.InlineKeyboardButton("📦 Download ALL files (zip)", callback_data=f"ud_dlall_{uid}"))
    else:
        lines.append("<i>No projects uploaded.</i>")
    m.row(types.InlineKeyboardButton("✉️ Message", callback_data=f"ud_msg_{uid}"),
          types.InlineKeyboardButton("✅ Unban" if uid in banned_users else "🚫 Ban", callback_data=f"ud_unban_{uid}" if uid in banned_users else f"ud_ban_{uid}"))
    m.row(types.InlineKeyboardButton("🎁 +7 days", callback_data=f"ud_gift_{uid}_7"), types.InlineKeyboardButton("🎁 +30 days", callback_data=f"ud_gift_{uid}_30"))
    m.row(types.InlineKeyboardButton("⏹ Stop all bots", callback_data=f"ud_stop_{uid}"),
          types.InlineKeyboardButton("🔄 Refresh", callback_data=f"ud_u_{uid}"))
    m.add(types.InlineKeyboardButton("🔙 Back to list", callback_data="ud_l_all_0"))
    return "\n".join(lines), m

_SKIP_DIRS = {'node_modules', '__pycache__', '.git', 'venv', '.venv', 'env', '.cache'}

def _zip_folder(folder, zf, arc_prefix=''):
    n = 0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fl in files:
            if fl.endswith('.log') or fl.endswith('.pyc'): continue
            full = os.path.join(root, fl)
            try:
                zf.write(full, os.path.join(arc_prefix, os.path.relpath(full, folder)))
                n += 1
            except Exception: pass
    return n

def _send_project_download(chat_id, uid, pn):
    fi = next((f for f in user_files.get(uid, []) if f[0] == pn), None)
    if not fi:
        bot.send_message(chat_id, "❌ Project not found."); return
    folder = get_user_folder(uid, pn)
    if not os.path.isdir(folder):
        bot.send_message(chat_id, "❌ Project folder is missing on the server."); return
    contents = [f for f in os.listdir(folder) if not f.endswith('.log') and f not in _SKIP_DIRS and f != '__pycache__']
    main_path = os.path.join(folder, fi[1])
    cap = f"📥 {pn} · user {uid}"
    if len(contents) == 1 and os.path.isfile(main_path):
        if os.path.getsize(main_path) > 49 * 1024 * 1024:
            bot.send_message(chat_id, "❌ File is bigger than Telegram's 50 MB limit."); return
        with open(main_path, 'rb') as f: bot.send_document(chat_id, f, caption=cap)
        return
    path = os.path.join(tempfile.gettempdir(), f"{uid}_{pn}_{int(time.time())}.zip")
    try:
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf: n = _zip_folder(folder, zf)
        if os.path.getsize(path) > 49 * 1024 * 1024:
            bot.send_message(chat_id, "❌ Zipped project is bigger than Telegram's 50 MB limit."); return
        with open(path, 'rb') as f: bot.send_document(chat_id, f, caption=f"{cap} ({n} files)")
    finally:
        try: os.remove(path)
        except Exception: pass

def _send_all_downloads(chat_id, uid):
    files = user_files.get(uid, [])
    if not files:
        bot.send_message(chat_id, "ℹ️ This user has no files."); return
    path = os.path.join(tempfile.gettempdir(), f"user_{uid}_{int(time.time())}.zip")
    try:
        total = 0
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for pn, _mf, _ft in files:
                folder = get_user_folder(uid, pn)
                if os.path.isdir(folder): total += _zip_folder(folder, zf, pn)
        if os.path.getsize(path) > 49 * 1024 * 1024:
            bot.send_message(chat_id, "❌ Combined zip is bigger than Telegram's 50 MB limit. Download projects one by one."); return
        with open(path, 'rb') as f: bot.send_document(chat_id, f, caption=f"📦 All files of user {uid} ({len(files)} projects, {total} files)")
    finally:
        try: os.remove(path)
        except Exception: pass

def _bots_directory(page):
    rows = []
    for uid in _all_user_ids():
        for pn, mf, ft in sorted(user_files.get(uid, [])):
            rows.append((uid, pn, mf, ft))
    per = 10
    pages = max(1, (len(rows) + per - 1) // per); page = max(0, min(page, pages - 1))
    lines = [f"🤖 <b>All Bots ({len(rows)})</b>\n"]
    for uid, pn, mf, ft in rows[page * per:(page + 1) * per]:
        fn, un, _, _ = get_profile(uid, fetch=False)
        bu = project_bot_username(uid, pn)
        lines.append(f"{'🟢' if is_bot_running(uid, pn) else '🔴'} <b>{_hx(pn)}</b> · {('@' + _hx(bu.lstrip('@'))) if bu else '—'}\n    👤 {_hx(fn or uid)} <code>{uid}</code>")
    if not rows: lines.append("<i>No bots yet.</i>")
    m = types.InlineKeyboardMarkup()
    nav = []
    if page > 0: nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"ud_bots_{page - 1}"))
    nav.append(types.InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1: nav.append(types.InlineKeyboardButton("➡️", callback_data=f"ud_bots_{page + 1}"))
    m.row(*nav)
    m.add(types.InlineKeyboardButton("🔙 Directory", callback_data="ud_l_all_0"))
    return "\n".join(lines), m

def _ud_export(chat_id):
    path = os.path.join(tempfile.gettempdir(), f"directory_{int(time.time())}.csv")
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = _csv3.writer(f)
        w.writerow(["user_id", "name", "username", "rank", "joined", "last_seen", "banned", "files", "project", "bot_username", "main_file", "type", "running"])
        for uid in _all_user_ids():
            fn, un, jd, ls = get_profile(uid, fetch=False)
            base = [uid, fn, un, rank_plain(uid), jd or '', ls or '', uid in banned_users, len(user_files.get(uid, []))]
            files = sorted(user_files.get(uid, []))
            if not files: w.writerow(base + ['', '', '', '', ''])
            for pn, mf, ft in files:
                w.writerow(base + [pn, project_bot_username(uid, pn), mf, ft, is_bot_running(uid, pn)])
    with open(path, 'rb') as f: bot.send_document(chat_id, f, caption="📤 Users & bots directory")
    try: os.remove(path)
    except Exception: pass

def _ud_msg_step(message, uid):
    if not message.text or message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    try:
        bot.send_message(uid, f"📩 <b>Message from admin</b>\n\n{_hx(message.text)}", parse_mode='HTML')
        bot.reply_to(message, "✅ Delivered.")
    except Exception as e:
        bot.reply_to(message, f"❌ Could not deliver: {_hx(e)}", parse_mode='HTML')

def _ud_search_step(message):
    if not message.text or message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    _UD_SEARCH[message.from_user.id] = message.text.strip()
    txt, mk = _ud_list_view(message.from_user.id, 'all', 0)
    bot.send_message(message.chat.id, txt, reply_markup=mk, parse_mode='HTML')

def users_directory_callback(call):
    data, chat_id, mid, aid = call.data, call.message.chat.id, call.message.message_id, call.from_user.id
    try:
        if data == 'ud_home' or data.startswith('ud_l_'):
            bot.answer_callback_query(call.id)
            flt, page = 'all', 0
            if data.startswith('ud_l_'):
                _, _, flt, page = data.split('_'); page = int(page)
            txt, mk = _ud_list_view(aid, flt, page); _send_or_edit(chat_id, txt, mk, mid); return
        if data.startswith('ud_u_'):
            bot.answer_callback_query(call.id)
            txt, mk = _ud_user_view(int(data[5:])); _send_or_edit(chat_id, txt, mk, mid); return
        if data.startswith('ud_bots_'):
            bot.answer_callback_query(call.id)
            txt, mk = _bots_directory(int(data[8:])); _send_or_edit(chat_id, txt, mk, mid); return
        if data == 'ud_s':
            bot.answer_callback_query(call.id)
            _ask(chat_id, "🔎 Send a name, @username, user ID, bot username or project name to search:", _ud_search_step); return
        if data == 'ud_sc':
            bot.answer_callback_query(call.id, "Search cleared"); _UD_SEARCH.pop(aid, None)
            txt, mk = _ud_list_view(aid, 'all', 0); _send_or_edit(chat_id, txt, mk, mid); return
        if data == 'ud_csv':
            bot.answer_callback_query(call.id, "Preparing..."); _ud_export(chat_id); return
        if data.startswith('ud_dl_'):
            _, _, uid_s, pn = data.split('_', 3)
            bot.answer_callback_query(call.id, "Sending file..."); _send_project_download(chat_id, int(uid_s), pn); return
        if data.startswith('ud_dlall_'):
            bot.answer_callback_query(call.id, "Zipping...")
            threading.Thread(target=_send_all_downloads, args=(chat_id, int(data[9:])), daemon=True).start(); return
        if data.startswith('ud_msg_'):
            bot.answer_callback_query(call.id)
            _ask(chat_id, "✉️ Send the message for this user:", _ud_msg_step, int(data[7:])); return
        if data.startswith(('ud_ban_', 'ud_unban_')):
            ban = data.startswith('ud_ban_'); uid = int(data.split('_')[2])
            if uid == OWNER_ID or (ban and uid in admin_ids and aid != OWNER_ID):
                bot.answer_callback_query(call.id, "⚠️ You can't ban this user.", show_alert=True); return
            if ban: ban_user_db(uid, "Banned via directory", aid); banned_users.add(uid)
            else: unban_user_db(uid); banned_users.discard(uid)
            bot.answer_callback_query(call.id, "Banned" if ban else "Unbanned")
            txt, mk = _ud_user_view(uid); _send_or_edit(chat_id, txt, mk, mid); return
        if data.startswith('ud_gift_'):
            _, _, uid_s, days_s = data.split('_'); uid, days = int(uid_s), int(days_s)
            now = datetime.now(); cur = user_subscriptions.get(uid)
            if cur and cur['expiry'] > now: expiry, pname, lim = cur['expiry'] + timedelta(days=days), cur.get('plan_name'), cur.get('file_limit')
            else: expiry, pname, lim = now + timedelta(days=days), "Gift", SUBSCRIBED_USER_LIMIT
            save_subscription(uid, expiry, pname, lim)
            try: bot.send_message(uid, f"🎁 <b>You received {days} free day(s) of premium!</b>\nActive until <b>{expiry:%d-%m-%Y}</b>.", parse_mode='HTML')
            except Exception: pass
            bot.answer_callback_query(call.id, f"+{days} days")
            txt, mk = _ud_user_view(uid); _send_or_edit(chat_id, txt, mk, mid); return
        if data.startswith('ud_stop_'):
            uid = int(data[8:]); n = 0
            for pn, _mf, _ft in list(user_files.get(uid, [])):
                if is_bot_running(uid, pn):
                    info = bot_scripts.get(f"{uid}_{pn}")
                    if info: kill_process_tree(info)
                    bot_scripts.pop(f"{uid}_{pn}", None); n += 1
            bot.answer_callback_query(call.id, f"Stopped {n} bot(s)")
            txt, mk = _ud_user_view(uid); _send_or_edit(chat_id, txt, mk, mid); return
    except Exception as e:
        logger.error(f"Users directory error ({data}): {e}", exc_info=True)
        try: bot.send_message(chat_id, f"❌ Error: {_hx(e)}", parse_mode='HTML')
        except Exception: pass

# ---- bot username step of the upload flow ----
_BOT_USERNAME_RE = re.compile(r"^@?[A-Za-z][A-Za-z0-9_]{3,31}$")

def _ask_bot_username(chat_id, user_id):
    ask = bot.send_message(chat_id, M('up_username'))
    _track_upload_msg(user_id, chat_id, ask.message_id)
    bot.register_next_step_handler(ask, process_upload_bot_username)

def process_upload_bot_username(message):
    user_id = message.from_user.id
    if message.text and message.text.strip().lower() == '/cancel':
        _cleanup_upload_msgs(pending_file_uploads.pop(user_id, None))
        bot.reply_to(message, M('up_cancelled')); return
    if user_id not in pending_file_uploads:
        bot.reply_to(message, "⚠️ No pending upload found. Please send your file again."); return
    _track_upload_msg(user_id, message.chat.id, message.message_id)
    raw = (message.text or '').strip()
    if raw.lower().startswith('https://t.me/'): raw = raw.split('/')[-1]
    if not _BOT_USERNAME_RE.match(raw) or not raw.lower().endswith('bot'):
        msg = bot.reply_to(message, M('up_username_bad'))
        _track_upload_msg(user_id, message.chat.id, msg.message_id)
        bot.register_next_step_handler(msg, process_upload_bot_username); return
    state = pending_file_uploads[user_id]
    state['bot_username'] = '@' + raw.lstrip('@')
    _cleanup_upload_msgs(state)          # username prompt + reply are deleted immediately
    state['cleanup'] = []
    ask = bot.send_message(message.chat.id, M('up_project'))
    _track_upload_msg(user_id, message.chat.id, ask.message_id)
    bot.register_next_step_handler(ask, process_upload_project_name)

# ============================================================
# --- Project data import / export (user panel) ---
# ============================================================
DATA_EXTS = {'.json', '.db', '.sqlite', '.sqlite3', '.txt', '.csv', '.yaml', '.yml', '.xml', '.ini', '.cfg',
             '.toml', '.dat', '.pkl', '.pickle', '.md', '.tsv', '.env', '.session', '.session-journal', '.jsonl', '.log.txt'}
IMPORT_MAX_FILES = 2000
IMPORT_MAX_UNZIPPED = 100 * 1024 * 1024
_DATA_SKIP_DIRS = {'node_modules', '__pycache__', '.git', 'venv', '.venv', 'env', '.cache'}

def _is_data_file(name):
    low = name.lower()
    return any(low.endswith(e) for e in DATA_EXTS)

def _data_can_manage(call_user, owner_id):
    return call_user == owner_id or call_user in admin_ids

def _project_exists(owner_id, pn):
    return any(f[0] == pn for f in user_files.get(owner_id, []))

def _build_project_zip(folder, path, data_only):
    n = 0
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in _DATA_SKIP_DIRS]
            for fl in files:
                if fl.endswith(('.log', '.pyc')): continue
                if data_only and not _is_data_file(fl): continue
                full = os.path.join(root, fl)
                try: zf.write(full, os.path.relpath(full, folder)); n += 1
                except Exception: pass
    return n

def _export_project_data(chat_id, owner_id, pn, data_only):
    folder = get_user_folder(owner_id, pn)
    if not os.path.isdir(folder):
        bot.send_message(chat_id, "❌ Project folder not found."); return
    path = os.path.join(tempfile.gettempdir(), f"{pn}_{'data' if data_only else 'full'}_{int(time.time())}.zip")
    try:
        n = _build_project_zip(folder, path, data_only)
        if n == 0:
            bot.send_message(chat_id, "ℹ️ No data files found in this project yet (json, db, txt, csv...).\nUse *Full project* to back up everything.", parse_mode='Markdown'); return
        size = os.path.getsize(path)
        if size > 49 * 1024 * 1024:
            bot.send_message(chat_id, f"❌ Export is {size // 1048576} MB — Telegram allows up to 50 MB for bots."); return
        stamp = datetime.now().strftime('%d-%m-%Y')
        with open(path, 'rb') as f:
            bot.send_document(chat_id, f, visible_file_name=f"{pn}_{'data' if data_only else 'backup'}_{stamp}.zip",
                              caption=f"📤 {'Data' if data_only else 'Full project'} export • {pn}\n{n} file(s) • {size / 1024:.1f} KB\n\nRe-import it any time with 📥 Import Data.")
    finally:
        try: os.remove(path)
        except Exception: pass

def _safe_target(folder, rel):
    rel = rel.replace('\\', '/').lstrip('/')
    if not rel or rel.endswith('/') or any(p in ('..', '') for p in rel.split('/')): return None
    target = os.path.normpath(os.path.join(folder, rel))
    if not target.startswith(os.path.normpath(folder) + os.sep): return None
    return target

def process_import_data(message, owner_id, pn):
    uid = message.from_user.id
    if message.text and message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Import cancelled."); return
    if not _data_can_manage(uid, owner_id) or not _project_exists(owner_id, pn):
        bot.reply_to(message, "⚠️ Project not found or no permission."); return
    doc = message.document
    if not doc:
        msg = bot.reply_to(message, "⚠️ Please send a *.zip* (or a single data file), or /cancel.", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_import_data, owner_id, pn); return
    if doc.file_size and doc.file_size > get_max_upload_bytes():
        bot.reply_to(message, f"❌ File too large (max {get_max_upload_bytes() // 1048576} MB)."); return
    folder = get_user_folder(owner_id, pn)
    os.makedirs(folder, exist_ok=True)
    status = bot.reply_to(message, "⏳ Importing...")
    try:
        raw = bot.download_file(bot.get_file(doc.file_id).file_path)
    except Exception as e:
        bot.edit_message_text(f"❌ Download failed: {e}", message.chat.id, status.message_id); return
    imported, skipped = [], []
    name = doc.file_name or 'data.bin'
    try:
        if name.lower().endswith('.zip'):
            tmp = os.path.join(tempfile.gettempdir(), f"imp_{owner_id}_{int(time.time())}.zip")
            with open(tmp, 'wb') as f: f.write(raw)
            try:
                with zipfile.ZipFile(tmp) as zf:
                    infos = [i for i in zf.infolist() if not i.is_dir()]
                    if len(infos) > IMPORT_MAX_FILES or sum(i.file_size for i in infos) > IMPORT_MAX_UNZIPPED:
                        bot.edit_message_text("❌ Archive is too large (max 2000 files / 100 MB unzipped).", message.chat.id, status.message_id); return
                    for i in infos:
                        target = _safe_target(folder, i.filename)
                        base = os.path.basename(i.filename)
                        if target is None: skipped.append(f"{i.filename} (unsafe path)"); continue
                        if not _is_data_file(base): skipped.append(f"{i.filename} (code/unsupported)"); continue
                        if any(p in _DATA_SKIP_DIRS for p in i.filename.replace('\\', '/').split('/')): skipped.append(f"{i.filename} (skipped folder)"); continue
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with zf.open(i) as src, open(target, 'wb') as dst: shutil.copyfileobj(src, dst)
                        imported.append(i.filename)
            finally:
                try: os.remove(tmp)
                except Exception: pass
        else:
            base = os.path.basename(name)
            if not _is_data_file(base):
                bot.edit_message_text("❌ That file type isn't allowed for data import (code files must be uploaded with 📤 Upload File so they get reviewed).", message.chat.id, status.message_id); return
            with open(os.path.join(folder, base), 'wb') as f: f.write(raw)
            imported.append(base)
    except zipfile.BadZipFile:
        bot.edit_message_text("❌ That isn't a valid zip file.", message.chat.id, status.message_id); return
    except Exception as e:
        logger.error(f"Data import failed: {e}", exc_info=True)
        bot.edit_message_text(f"❌ Import failed: {e}", message.chat.id, status.message_id); return
    lines = [f"✅ <b>Import finished</b> — {_hx(pn)}", f"📥 Imported: <b>{len(imported)}</b> file(s)"]
    if imported: lines.append("<code>" + _hx("\n".join(imported[:12]) + (f"\n... +{len(imported) - 12} more" if len(imported) > 12 else "")) + "</code>")
    if skipped:
        lines.append(f"⏭️ Skipped: <b>{len(skipped)}</b>")
        lines.append("<code>" + _hx("\n".join(skipped[:8]) + (f"\n... +{len(skipped) - 8} more" if len(skipped) > 8 else "")) + "</code>")
    lines.append("\n🔄 Restart the bot so it picks up the new data.")
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("🔄 Restart bot now", callback_data=f"restart_{owner_id}_{pn}"))
    mk.add(types.InlineKeyboardButton("🔙 Back to project", callback_data=f"file_{owner_id}_{pn}"))
    try: bot.edit_message_text("\n".join(lines), message.chat.id, status.message_id, parse_mode='HTML', reply_markup=mk)
    except Exception: bot.send_message(message.chat.id, "\n".join(lines), parse_mode='HTML', reply_markup=mk)

def project_data_callback(call):
    data, chat_id, mid = call.data, call.message.chat.id, call.message.message_id
    try:
        kind, owner_s, pn = data.split('_', 2)
        owner_id = int(owner_s)
    except Exception:
        bot.answer_callback_query(call.id, "Invalid action.", show_alert=True); return
    if not _data_can_manage(call.from_user.id, owner_id):
        bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
    if not _project_exists(owner_id, pn):
        bot.answer_callback_query(call.id, "⚠️ Project not found.", show_alert=True); return
    if kind == 'exp':
        bot.answer_callback_query(call.id)
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("🗄️ Data only (json, db, txt, csv…)", callback_data=f"expd_{owner_id}_{pn}"),
              types.InlineKeyboardButton("📦 Full project backup (code + data)", callback_data=f"expf_{owner_id}_{pn}"),
              types.InlineKeyboardButton("🔙 Back", callback_data=f"file_{owner_id}_{pn}"))
        _send_or_edit(chat_id, f"📤 <b>Export — {_hx(pn)}</b>\n\n🗄️ <b>Data only</b>: your bot's data files (databases, JSON, text…).\n📦 <b>Full project</b>: everything, as a backup.", m, mid)
    elif kind in ('expd', 'expf'):
        bot.answer_callback_query(call.id, "Preparing export...")
        threading.Thread(target=_export_project_data, args=(chat_id, owner_id, pn, kind == 'expd'), daemon=True).start()
    elif kind == 'imp':
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id,
            f"📥 *Import data — {pn}*\n\nSend a *.zip* exported from this bot (or a single data file).\n"
            "✅ Allowed: json, db, sqlite, txt, csv, yaml, xml, ini, toml, pkl…\n"
            "⛔ Code files (.py, .js …) are skipped — upload code with 📤 Upload File so it gets reviewed.\n"
            "Existing files with the same name are overwritten.\n\n/cancel to abort.", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_import_data, owner_id, pn)

# ============================================================
# --- Upload approval mode (Automatic / Manual) ---
# ============================================================
def _upload_mode():
    return 'auto' if str(get_setting('UPLOAD_APPROVAL', 'manual')) == 'auto' else 'manual'

def _auto_safe_only():
    return str(get_setting('AUTO_SAFE_ONLY', '1')) == '1'

def _should_auto_approve(is_safe):
    return _upload_mode() == 'auto' and (is_safe or not _auto_safe_only())

def _approve_file_core(user_id, project_name, reply_msg):
    """Approve a pending .py/.js file without needing an admin callback. Returns True on success."""
    entry = pending_script_files.get(user_id, {}).get(project_name)
    if not entry or not os.path.exists(entry['path']): return False
    file_path, file_type = entry['path'], entry['type']
    main_file = entry.get('main_file', os.path.basename(file_path))
    folder = os.path.dirname(file_path)
    try:
        if file_type == 'js': handle_js_file(file_path, user_id, folder, main_file, reply_msg, project_name)
        else: handle_py_file(file_path, user_id, folder, main_file, reply_msg, project_name)
    except Exception as e:
        logger.error(f"Auto-approve file failed: {e}", exc_info=True); return False
    pending_script_files.get(user_id, {}).pop(project_name, None)
    if user_id in pending_script_files and not pending_script_files[user_id]: del pending_script_files[user_id]
    remove_pending_script_db(user_id, project_name)
    return True

def _approve_zip_core(user_id, project_name, reply_msg):
    """Approve a pending ZIP without an admin callback. Returns True when processing was started."""
    entry = pending_zip_files.get(user_id, {}).get(project_name)
    if entry is None: return False
    content = entry['content'] if isinstance(entry, dict) else entry
    zname = entry.get('file_name_zip', f"{project_name}.zip") if isinstance(entry, dict) else f"{project_name}.zip"
    main_file = entry.get('main_file') if isinstance(entry, dict) else None
    pending_zip_files[user_id].pop(project_name, None)
    if not pending_zip_files[user_id]: del pending_zip_files[user_id]
    remove_pending_zip_db(user_id, project_name)
    threading.Thread(target=process_zip_file, args=(content, zname, user_id, get_user_folder(user_id), reply_msg, project_name, main_file), daemon=True).start()
    return True

def _notify_auto_approved(user_id, project_name, kind):
    try: bot.send_message(user_id, f"✅ Your project `{project_name}` was approved automatically{' and is being processed' if kind == 'zip' else ' and started'}!", parse_mode='Markdown')
    except Exception: pass
    for aid in admin_ids:
        try: bot.send_message(aid, f"🤖 Auto-approved {kind}: project `{project_name}` of user `{user_id}`.", parse_mode='Markdown', disable_notification=True)
        except Exception: pass

def _ua_markup():
    auto = _upload_mode() == 'auto'
    pend = sum(len(v) for v in pending_script_files.values()) + sum(len(v) for v in pending_zip_files.values())
    m = types.InlineKeyboardMarkup(row_width=2)
    m.row(types.InlineKeyboardButton(("✅ " if auto else "") + "🤖 Automatic", callback_data="ua_set_auto"),
          types.InlineKeyboardButton(("" if auto else "✅ ") + "✋ Manual", callback_data="ua_set_manual"))
    m.add(types.InlineKeyboardButton(f"🛡️ Auto-approve safe files only: {'ON ✅' if _auto_safe_only() else 'OFF ❌'}", callback_data="ua_safe"))
    m.add(types.InlineKeyboardButton(f"⚡ Approve all pending now ({pend})", callback_data="ua_all"))
    m.add(types.InlineKeyboardButton("📋 Pending Files", callback_data="pending_files"))
    m.add(types.InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel"))
    return m

def _ua_text():
    auto = _upload_mode() == 'auto'
    return ("🛂 <b>Upload Approval</b>\n\n"
            f"Current mode: <b>{'🤖 Automatic' if auto else '✋ Manual'}</b>\n\n"
            "🤖 <b>Automatic</b> — uploaded files are approved and started immediately.\n"
            "✋ <b>Manual</b> — every upload waits for an admin to approve it.\n\n"
            f"🛡️ Safe-only: <b>{'ON' if _auto_safe_only() else 'OFF'}</b> — "
            + ("files that trip the security scan are still sent to admins for review." if _auto_safe_only()
               else "<b>everything</b> is approved, even files flagged as dangerous!"))

def upload_approval_callback(call):
    data, chat_id, mid = call.data, call.message.chat.id, call.message.message_id
    try:
        if data == 'ua_set_auto' or data == 'ua_set_manual':
            set_setting('UPLOAD_APPROVAL', 'auto' if data == 'ua_set_auto' else 'manual')
            bot.answer_callback_query(call.id, "Mode updated")
        elif data == 'ua_safe':
            set_setting('AUTO_SAFE_ONLY', '0' if _auto_safe_only() else '1')
            bot.answer_callback_query(call.id, "Updated")
        elif data == 'ua_all':
            bot.answer_callback_query(call.id)
            m = types.InlineKeyboardMarkup()
            m.row(types.InlineKeyboardButton("✅ Yes, approve", callback_data="ua_all_yes"), types.InlineKeyboardButton("❌ Cancel", callback_data="ua_home"))
            bot.send_message(chat_id, "⚠️ Approve all pending uploads now?" + (" (only files that passed the security scan)" if _auto_safe_only() else " (<b>including flagged ones</b>)"),
                             parse_mode='HTML', reply_markup=m); return
        elif data == 'ua_all_yes':
            bot.answer_callback_query(call.id, "Working...")
            ok = skipped = 0
            for uid, projs in list(pending_script_files.items()):
                for pn, e in list(projs.items()):
                    if not e.get('is_safe', False) and _auto_safe_only(): skipped += 1; continue
                    if _approve_file_core(uid, pn, call.message): _notify_auto_approved(uid, pn, 'file'); ok += 1
            for uid, projs in list(pending_zip_files.items()):
                for pn, e in list(projs.items()):
                    flagged = bool(e.get('patterns')) if isinstance(e, dict) else False
                    if flagged and _auto_safe_only(): skipped += 1; continue
                    if _approve_zip_core(uid, pn, call.message): _notify_auto_approved(uid, pn, 'zip'); ok += 1
            bot.send_message(chat_id, f"✅ Approved <b>{ok}</b> upload(s). Skipped (flagged): <b>{skipped}</b>.", parse_mode='HTML'); return
        else:
            bot.answer_callback_query(call.id)
        _send_or_edit(chat_id, _ua_text(), _ua_markup(), mid)
    except Exception as e:
        logger.error(f"Upload approval callback error: {e}", exc_info=True)

# ============================================================
# --- Force Join Channel Callbacks ---
# ============================================================
def set_force_join_callback(call):
    """Admin: prompt to add a mandatory join channel via username, chat ID, or forwarded message."""
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        "📢 *Add Force Channel*\n"
        "──────────────────────\n"
        "Send the channel in any of these ways:\n\n"
        "🔗 *Username*  →  `@mychannel`\n"
        "🆔 *Chat ID*   →  `-1001234567890`\n"
        "📨 *Forward*   →  Forward any message from the channel\n\n"
        "──────────────────────\n"
        "⚠️ Make sure this bot is an *admin* in that channel first.\n\n"
        "❌ /cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_set_force_join)

def process_set_force_join(message):
    global force_join_channels
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text and message.text.strip().lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return

    channel = None
    if message.forward_from_chat and message.forward_from_chat.type == 'channel':
        channel = message.forward_from_chat.username
        if channel:
            channel = f"@{channel}"
        else:
            channel = str(message.forward_from_chat.id)
    elif message.text:
        raw = message.text.strip()
        if raw.lstrip('-').isdigit():
            channel = raw
        else:
            channel = raw if raw.startswith('@') else f"@{raw}"
    else:
        bot.reply_to(message,
            "⚠️ Could not detect channel.\n"
            "Send a `@username`, a chat ID like `-1001234567890`, or forward a message from the channel.",
            parse_mode='Markdown')
        return

    try:
        chat_info = bot.get_chat(channel)
        channel = f"@{chat_info.username}" if chat_info.username else str(chat_info.id)
        title = chat_info.title or channel
    except Exception:
        bot.reply_to(message,
            f"❌ *Could not access* `{channel}`\n"
            "──────────────────────\n"
            "Please check that:\n\n"
            "› Channel *exists*\n"
            "› This bot is an *admin* in the channel\n"
            "› The username/ID is *correct*",
            parse_mode='Markdown')
        return

    try:
        invite_link = bot.export_chat_invite_link(channel)
    except Exception:
        invite_link = f"https://t.me/{channel.lstrip('@')}" if channel.startswith('@') else None

    if any(e['channel'] == channel for e in force_join_channels):
        bot.reply_to(message, f"ℹ️ *{title}* is already in the mandatory join list.", parse_mode='Markdown')
        return

    force_join_channels.append({'channel': channel, 'title': title, 'invite_link': invite_link})
    add_force_join_channel_db(channel, title, invite_link, message.from_user.id)
    bot.reply_to(message,
        f"✅ *{title}* added to mandatory join list.\n"
        f"📋 Total channels: *{len(force_join_channels)}*",
        parse_mode='Markdown')
    logger.info(f"Force join channel added: {title} ({channel}) by {message.from_user.id}")

def remove_force_join_callback(call):
    """Admin: remove a specific channel from the mandatory join list."""
    global force_join_channels
    channel = call.data[len('remove_force_join_'):]
    entry = next((e for e in force_join_channels if e['channel'] == channel), None)
    if not entry:
        bot.answer_callback_query(call.id, "ℹ️ Channel not in list.", show_alert=True); return
    force_join_channels.remove(entry)
    remove_force_join_channel_db(channel)
    bot.answer_callback_query(call.id, f"✅ {entry['title']} removed!")
    logger.info(f"Force join channel removed: {entry['title']} ({channel}) by {call.from_user.id}")
    text, markup = _channel_add_panel(force_join_channels)
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              parse_mode='Markdown', reply_markup=markup)
    except Exception: pass

def check_joined_callback(call):
    """User presses 'I've Joined All' — re-check membership for all channels."""
    user_id = call.from_user.id
    if not force_join_channels:
        bot.answer_callback_query(call.id, "✅ No restriction active.")
        return
    unjoined = [e for e in force_join_channels if not is_user_in_channel(user_id, e['channel'])]
    if not unjoined:
        bot.answer_callback_query(call.id, "✅ Verified! Welcome.", show_alert=True)
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception: pass
        bot.send_message(call.message.chat.id, "✅ Access granted! Use /start to continue.")
    else:
        titles = ', '.join(e['title'] for e in unjoined)
        bot.answer_callback_query(call.id, f"❌ Still not joined: {titles}", show_alert=True)

# ============================================================
# --- Cleanup ---
# ============================================================
def cleanup():
    logger.warning("Shutdown. Cleaning up processes...")
    script_keys_to_stop = list(bot_scripts.keys())
    if not script_keys_to_stop: logger.info("No scripts running."); return
    for key in script_keys_to_stop:
        if key in bot_scripts:
            logger.info(f"Stopping: {key}")
            kill_process_tree(bot_scripts[key])
    logger.warning("Cleanup finished.")
atexit.register(cleanup)

# ============================================================
# --- Main Execution ---
# ============================================================

# ============================================================
# --- ADMIN TOOLBOX: 100+ reports, controls and maintenance tools ---
# ============================================================
AP_DEF = {'UP_ENABLED': '1', 'UP_ALLOW_PY': '1', 'UP_ALLOW_JS': '1', 'UP_ALLOW_ZIP': '1', 'UP_PREMIUM_ONLY': '0', 'UP_REQUIRE_USERNAME': '0',
          'UP_FWD_OWNER': '1', 'UP_COOLDOWN_SEC': '0', 'UP_DAILY_LIMIT': '0', 'UP_NAME_MAXLEN': '40', 'UP_MAXMB_FREE': '0',
          'SEC_SCAN_ON': '1', 'SEC_BLOCK_WORDS': '', 'SEC_LOG_ADMIN': '1',
          'RUN_BLOCK_START': '0', 'RUN_MAX_PER_USER': '0', 'RUN_MAX_TOTAL': '0', 'RUN_AUTO_STOP_EXPIRED': '0', 'RUN_AUTO_RESTART': '0',
          'RUN_RESTART_MAX': '5', 'RUN_MAX_HOURS_FREE': '0', 'RUN_MEM_LIMIT_MB': '0', 'RUN_NOTIFY_CRASH': '1', 'RUN_LOG_MAX_MB': '0',
          'USR_TRIAL_DAYS': '0', 'USR_SIGNUP_POINTS': '0', 'FJ_ENABLED': '1', 'USR_NOTIFY_BAN': '1',
          'NTF_EXPIRY_ADMIN': '0', 'NTF_DAILY_REPORT': '0', 'NTF_DAILY_HOUR': '9', 'NTF_STARTUP_DM': '1', 'NTF_ERROR_DM': '1', 'NTF_CRASH_ADMIN': '0'}
LB_DEF.update(AP_DEF)

def _ap_init():
    _db_exec("CREATE TABLE IF NOT EXISTS ap_uploads (user_id INTEGER, ts TEXT)")
    _db_exec("CREATE TABLE IF NOT EXISTS ap_admin_log (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, ts TEXT)")
    _db_exec("CREATE TABLE IF NOT EXISTS ap_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, note TEXT, by_admin INTEGER, ts TEXT)")
    _db_exec("CREATE TABLE IF NOT EXISTS ap_tempban (user_id INTEGER PRIMARY KEY, until TEXT)")

# ---------- small helpers ----------
def _apn(uid):
    fn, un, _, _ = get_profile(uid, fetch=False)
    return _hmx.escape((fn or '') + (f" @{un}" if un else '') or f"User{str(uid)[-4:]}").strip()
def _now(): return datetime.now()
def _iso_ago(**kw): return (_now() - timedelta(**kw)).isoformat()
def _today(): return _now().strftime('%Y-%m-%d')
def _cnt(sql, p=()): return (_db_q(sql, p, one=True) or [0])[0] or 0
def _say(chat, text, mk=None):
    for i in range(0, len(text), 3800):
        bot.send_message(chat, text[i:i + 3800], parse_mode='HTML', reply_markup=mk if i + 3800 >= len(text) else None)
def _rows_text(title, rows, empty="<i>Nothing to show.</i>"):
    return f"<b>{title}</b>\n━━━━━━━━━━━━━━━━━━\n" + ("\n".join(rows) if rows else empty)
def _money(v): return fmt_money(v) if v else "0"
def _is_prem(u): return has_active_sub(u)

# ---------- hooks (enforcement of the toggles / numbers) ----------
def _ap_upload_gate(message, ext=None, size=None):
    uid = message.from_user.id
    if uid in admin_ids: return True
    def no(txt): bot.reply_to(message, txt); return False
    if not _lbf('UP_ENABLED'): return no("⏸️ Uploads are temporarily disabled by the admin.")
    if _lbf('UP_PREMIUM_ONLY') and not _is_prem(uid): return no("💎 Uploads are for premium members only. Tap View Plans to upgrade.")
    if _lbf('UP_REQUIRE_USERNAME') and not message.from_user.username: return no("✳️ Please set a Telegram @username in your profile settings before uploading.")
    if ext:
        k = {'.py': 'UP_ALLOW_PY', '.js': 'UP_ALLOW_JS', '.zip': 'UP_ALLOW_ZIP'}.get(ext)
        if k and not _lbf(k): return no(f"🚫 <code>{ext}</code> uploads are currently disabled.".replace('<code>', '').replace('</code>', ''))
        cd = _lbi('UP_COOLDOWN_SEC')
        if cd > 0:
            last = _db_q("SELECT ts FROM ap_uploads WHERE user_id=? ORDER BY ts DESC LIMIT 1", (uid,), one=True)
            if last:
                left = cd - (_now() - datetime.fromisoformat(last[0])).total_seconds()
                if left > 0: return no(f"⏳ Please wait {int(left) + 1}s before your next upload.")
        dl = _lbi('UP_DAILY_LIMIT')
        if dl > 0 and _cnt("SELECT COUNT(*) FROM ap_uploads WHERE user_id=? AND ts >= ?", (uid, _today())) >= dl:
            return no(f"📅 Daily upload limit reached ({dl}). Try again tomorrow.")
        mf = _lbi('UP_MAXMB_FREE')
        if mf > 0 and size and not _is_prem(uid) and size > mf * 1048576: return no(f"⚠️ Free users can upload up to {mf} MB. Upgrade for more.")
        _db_exec("INSERT INTO ap_uploads (user_id, ts) VALUES (?, ?)", (uid, _now().isoformat()))
    return True

def _ap_namelen():
    return max(5, min(60, _lbi('UP_NAME_MAXLEN') or 40))

def _ap_run_gate(owner_id, msg_obj, project):
    if owner_id in admin_ids: return True
    def no(t):
        try: bot.send_message(msg_obj.chat.id, t)
        except Exception: pass
        return False
    if _lbf('RUN_BLOCK_START'): return no("⏸️ Starting bots is temporarily paused by the admin.")
    mu = _lbi('RUN_MAX_PER_USER')
    if mu > 0:
        n = sum(1 for pn, _m, _t in user_files.get(owner_id, []) if pn != project and is_bot_running(owner_id, pn))
        if n >= mu: return no(f"⚠️ You can run up to {mu} bot(s) at the same time. Stop one first.")
    mt = _lbi('RUN_MAX_TOTAL')
    if mt > 0:
        total = sum(1 for k in list(bot_scripts) if is_bot_running(int(k.split('_', 1)[0]), k.split('_', 1)[1]))
        if total >= mt: return no("⚠️ The server is full right now. Please try again later.")
    return True

_ap_orig_fj = check_force_join
def check_force_join(message):
    if not _lbf('FJ_ENABLED'): return True
    return _ap_orig_fj(message)

_ap_orig_scan = scan_code_security
def scan_code_security(content):
    if not _lbf('SEC_SCAN_ON'): return [], 0
    labels, score = _ap_orig_scan(content)
    words = [w.strip().lower() for w in str(get_setting('SEC_BLOCK_WORDS', '') or '').split(',') if w.strip()]
    low = content.lower()
    hit = [w for w in words if w in low]
    if hit: labels = labels + [f"blocked word: {w}" for w in hit[:3]]; score += SECURITY_SCORE_THRESHOLD
    return labels, score

_ap_orig_fwd = bot.forward_message
def _fwd(chat_id, *a, **k):
    if chat_id == OWNER_ID and not _lbf('UP_FWD_OWNER'): return None
    return _ap_orig_fwd(chat_id, *a, **k)
bot.forward_message = _fwd

_ap_orig_add_user = add_active_user
def add_active_user(user_id):
    was = user_id in active_users
    _ap_orig_add_user(user_id)
    if was or user_id in admin_ids: return
    try:
        d = _lbi('USR_TRIAL_DAYS')
        if d > 0 and not has_active_sub(user_id):
            save_subscription(user_id, _now() + timedelta(days=d), 'Trial', SUBSCRIBED_USER_LIMIT)
            bot.send_message(user_id, f"🎁 <b>Welcome gift!</b> You got <b>{d} day(s)</b> of premium for free.", parse_mode='HTML')
        p = _lbi('USR_SIGNUP_POINTS')
        if p > 0 and _rp_on():
            _lb_add_points(user_id, p, 'signup_bonus')
            bot.send_message(user_id, f"⭐ Signup bonus: <b>+{p} points</b>!", parse_mode='HTML')
    except Exception as e: logger.warning(f"signup bonus failed: {e}")

_ap_orig_ban = ban_user_db
def ban_user_db(user_id, reason, banned_by):
    ok = _ap_orig_ban(user_id, reason, banned_by)
    if ok and _lbf('USR_NOTIFY_BAN'):
        try: bot.send_message(user_id, f"🚫 <b>Your account was banned.</b>\nReason: {_hmx.escape(str(reason))}", parse_mode='HTML')
        except Exception: pass
    return ok
_ap_orig_unban = unban_user_db
def unban_user_db(user_id):
    ok = _ap_orig_unban(user_id)
    if ok and _lbf('USR_NOTIFY_BAN'):
        try: bot.send_message(user_id, "✅ <b>Your account was unbanned.</b> Welcome back!", parse_mode='HTML')
        except Exception: pass
    return ok

_ap_orig_arc = admin_required_callback
def admin_required_callback(call, func_to_run):
    try:
        if call.from_user.id in admin_ids and _lbf('SEC_LOG_ADMIN') and not str(call.data).startswith(('ap_',)):
            _db_exec("INSERT INTO ap_admin_log (admin_id, action, ts) VALUES (?,?,?)", (call.from_user.id, str(call.data)[:60], _now().isoformat()))
    except Exception: pass
    return _ap_orig_arc(call, func_to_run)

_ap_orig_kill = kill_process_tree
def kill_process_tree(process_info):
    try: process_info['manual_stop'] = True
    except Exception: pass
    return _ap_orig_kill(process_info)

# ---------- background watcher ----------
_AP_SEEN = {}; _AP_RESTARTS = {}; _AP_STATE = {'report_day': '', 'exp_notified': set()}
class _FakeMsg:
    def __init__(self, chat_id): self.chat = types.Chat(chat_id, 'private') if hasattr(types, 'Chat') else type('C', (), {'id': chat_id})(); self.message_id = None; self.from_user = type('U', (), {'id': chat_id})()

def _ap_restart(owner, project):
    fi = next((f for f in user_files.get(owner, []) if f[0] == project), None)
    if not fi: return False
    _, main_file, ftype = fi
    folder = get_user_folder(owner, project); path = os.path.join(folder, main_file)
    if not os.path.exists(path): return False
    fake = type('M', (), {})(); fake.chat = type('C', (), {'id': owner})(); fake.message_id = None
    if ftype == 'js': threading.Thread(target=run_js_script, args=(path, owner, folder, project, fake), kwargs={'skip_deps_install': True}, daemon=True).start()
    else: threading.Thread(target=run_script, args=(path, owner, folder, project, fake), kwargs={'skip_deps_install': True}, daemon=True).start()
    return True

def _ap_daily_report():
    tot = len(active_users); prem = sum(1 for u in active_users if has_active_sub(u))
    run = sum(1 for k in list(bot_scripts) if is_bot_running(int(k.split('_', 1)[0]), k.split('_', 1)[1]))
    return (f"📰 <b>Daily Report · {_now():%d %b %Y}</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"👥 Users: <b>{tot}</b> (+{_cnt('SELECT COUNT(*) FROM active_users WHERE join_date >= ?', (_today(),))} today)\n"
            f"⭐ Premium: <b>{prem}</b>\n🤖 Running bots: <b>{run}</b>\n"
            f"💰 Revenue today: <b>{_money(_cnt('SELECT SUM(amount_base) FROM payments WHERE created_at >= ?', (_today(),)))}</b>\n"
            f"🛒 Sales today: <b>{_cnt('SELECT COUNT(*) FROM payments WHERE created_at >= ?', (_today(),))}</b>")

def _ap_tick():
    now = _now()
    # 1) crashes / auto restart / limits
    for key, info in list(bot_scripts.items()):
        _AP_SEEN[key] = info
    for key, info in list(_AP_SEEN.items()):
        try:
            owner, project = info.get('script_owner_id'), info.get('project_name')
            proc = info.get('process')
            if info.get('manual_stop'): _AP_SEEN.pop(key, None); continue
            if proc is not None and proc.poll() is not None:                       # process ended on its own
                _AP_SEEN.pop(key, None); bot_scripts.pop(key, None)
                rc = proc.returncode
                if rc == 0: continue
                if _lbf('RUN_NOTIFY_CRASH'):
                    try: bot.send_message(owner, f"⚠️ <b>Your project {_hmx.escape(str(project))} stopped unexpectedly</b> (exit code {rc}). Check 📜 Logs.", parse_mode='HTML')
                    except Exception: pass
                if _lbf('NTF_CRASH_ADMIN'):
                    for a in list(admin_ids)[:3]:
                        try: bot.send_message(a, f"💥 Crash: <code>{owner}</code> · {_hmx.escape(str(project))} (exit {rc})", parse_mode='HTML')
                        except Exception: pass
                if _lbf('RUN_AUTO_RESTART'):
                    hist = [t for t in _AP_RESTARTS.get(key, []) if time.time() - t < 3600]
                    if len(hist) < max(1, _lbi('RUN_RESTART_MAX')):
                        hist.append(time.time()); _AP_RESTARTS[key] = hist
                        if _ap_restart(owner, project):
                            try: bot.send_message(owner, f"🔄 Auto-restarting <b>{_hmx.escape(str(project))}</b>…", parse_mode='HTML')
                            except Exception: pass
                continue
            if proc is None or owner in admin_ids: continue
            stop_reason = None
            sub = user_subscriptions.get(owner)
            if _lbf('RUN_AUTO_STOP_EXPIRED') and sub and sub.get('expiry') and sub['expiry'] < now: stop_reason = "your plan expired"
            mh = _lbi('RUN_MAX_HOURS_FREE')
            if not stop_reason and mh > 0 and not has_active_sub(owner) and info.get('start_time') and (now - info['start_time']).total_seconds() > mh * 3600:
                stop_reason = f"free bots can run up to {mh}h in a row"
            ml = _lbi('RUN_MEM_LIMIT_MB')
            if not stop_reason and ml > 0:
                try:
                    p = psutil.Process(proc.pid); rss = p.memory_info().rss + sum(c.memory_info().rss for c in p.children(recursive=True))
                    if rss > ml * 1048576: stop_reason = f"it used more than {ml} MB of RAM"
                except Exception: pass
            if stop_reason:
                kill_process_tree(info); bot_scripts.pop(key, None); _AP_SEEN.pop(key, None)
                try: bot.send_message(owner, f"⏹️ <b>{_hmx.escape(str(project))} was stopped</b> because {stop_reason}.", parse_mode='HTML')
                except Exception: pass
        except Exception as e: logger.debug(f"ap_tick bot error: {e}")
    # 2) log size cap
    lm = _lbi('RUN_LOG_MAX_MB')
    if lm > 0:
        for key, info in list(bot_scripts.items()):
            try:
                lp = os.path.join(info.get('user_folder', ''), f"{info.get('project_name')}.log")
                if os.path.exists(lp) and os.path.getsize(lp) > lm * 1048576: os.truncate(lp, 0)
            except Exception: pass
    # 3) temp bans
    for uid, until in _db_q("SELECT user_id, until FROM ap_tempban"):
        if until < now.isoformat():
            _db_exec("DELETE FROM ap_tempban WHERE user_id=?", (uid,)); unban_user_db(uid)
    # 4) plan expired -> admins
    if _lbf('NTF_EXPIRY_ADMIN'):
        for uid, sub in list(user_subscriptions.items()):
            exp = sub.get('expiry')
            if exp and exp < now and (uid, exp.isoformat()) not in _AP_STATE['exp_notified'] and now - exp < timedelta(days=1):
                _AP_STATE['exp_notified'].add((uid, exp.isoformat()))
                for a in list(admin_ids)[:3]:
                    try: bot.send_message(a, f"⌛ Plan expired: <code>{uid}</code> {_apn(uid)} ({_hmx.escape(str(sub.get('plan_name')))})", parse_mode='HTML')
                    except Exception: pass
    # 5) daily report
    if _lbf('NTF_DAILY_REPORT') and now.hour == _lbi('NTF_DAILY_HOUR') and _AP_STATE['report_day'] != _today():
        _AP_STATE['report_day'] = _today()
        try: bot.send_message(OWNER_ID, _ap_daily_report(), parse_mode='HTML')
        except Exception: pass

def _ap_watcher():
    while True:
        try: _ap_tick()
        except Exception as e: logger.warning(f"ap_watcher: {e}")
        time.sleep(30)

# ============================================================
# --- Admin Toolbox: option registry ---
# ============================================================
AP_OPTS = []
AP_CATS = [('rep', '📊 Reports'), ('rev', '💰 Revenue'), ('upl', '📤 Uploads & Security'), ('run', '🤖 Hosting Control'),
           ('usr', '👥 Users & Access'), ('ntf', '🔔 Notifications'), ('mnt', '🧹 Maintenance')]

def _ap(cat, kind, label, **kw):
    AP_OPTS.append(dict(cat=cat, kind=kind, label=label, **kw))

def R(cat, label):            # report: fn() -> text
    def d(f): _ap(cat, 'rep', label, fn=f); return f
    return d
def A(cat, label):            # instant action: fn(call) -> text
    def d(f): _ap(cat, 'act', label, fn=f); return f
    return d
def Q(cat, label, prompt):    # asks the admin for text, fn(message, text) -> text
    def d(f): _ap(cat, 'ask', label, fn=f, prompt=prompt); return f
    return d
def C(cat, label, warn):      # needs a confirm tap, fn(call) -> text
    def d(f): _ap(cat, 'cfm', label, fn=f, warn=warn); return f
    return d
def TOG(cat, label, key): _ap(cat, 'tog', label, key=key)
def NUM(cat, label, key, lo=0, hi=10 ** 7, unit=''): _ap(cat, 'num', label, key=key, lo=lo, hi=hi, unit=unit)

def _u(uid): return f"<code>{uid}</code> {_apn(uid)}"
def _since(days): return (_now() - timedelta(days=days)).isoformat()
def _top(title, sql, fmt, p=()):
    return _rows_text(title, [fmt(i + 1, r) for i, r in enumerate(_db_q(sql, p))])
def _parse_uid(text):
    parts = str(text).split(None, 1)
    return int(parts[0]), (parts[1].strip() if len(parts) > 1 else '')
def _is_running(k):
    try: return is_bot_running(int(k.split('_', 1)[0]), k.split('_', 1)[1])
    except Exception: return False
def _dir_size(path):
    t = 0
    for r, _d, fs in os.walk(path):
        for f in fs:
            try: t += os.path.getsize(os.path.join(r, f))
            except Exception: pass
    return t
def _mb(b): return f"{b / 1048576:.1f} MB"

# ---------------- 📊 REPORTS ----------------
@R('rep', '🆕 New Users Today')
def _r1(): return f"🆕 <b>New users today:</b> {_cnt('SELECT COUNT(*) FROM active_users WHERE join_date >= ?', (_today(),))}"
@R('rep', '🆕 New Users 7d')
def _r2(): return f"🆕 <b>New users (7 days):</b> {_cnt('SELECT COUNT(*) FROM active_users WHERE join_date >= ?', (_since(7),))}"
@R('rep', '🆕 New Users 30d')
def _r3(): return f"🆕 <b>New users (30 days):</b> {_cnt('SELECT COUNT(*) FROM active_users WHERE join_date >= ?', (_since(30),))}"
@R('rep', '🟢 Active 24h')
def _r4(): return f"🟢 <b>Active in 24h:</b> {_cnt('SELECT COUNT(*) FROM active_users WHERE last_seen >= ?', (_since(1),))}"
@R('rep', '🟢 Active 7d')
def _r5(): return f"🟢 <b>Active in 7 days:</b> {_cnt('SELECT COUNT(*) FROM active_users WHERE last_seen >= ?', (_since(7),))}"
@R('rep', '🟢 Active 30d')
def _r6(): return f"🟢 <b>Active in 30 days:</b> {_cnt('SELECT COUNT(*) FROM active_users WHERE last_seen >= ?', (_since(30),))}"
@R('rep', '😴 Inactive 30d+')
def _r7(): return f"😴 <b>Not seen for 30+ days:</b> {_cnt('SELECT COUNT(*) FROM active_users WHERE last_seen < ? OR last_seen IS NULL', (_since(30),))}"
@R('rep', '⭐ Premium vs Free')
def _r8():
    tot = len(active_users); p = sum(1 for u in active_users if has_active_sub(u))
    return f"⭐ <b>Premium vs Free</b>\n━━━━━━━━━━━━━━━━━━\n⭐ Premium: <b>{p}</b> ({(p * 100 / tot) if tot else 0:.1f}%)\n🆓 Free: <b>{tot - p}</b>\n👥 Total: <b>{tot}</b>"
@R('rep', '📁 Top Uploaders')
def _r9(): return _top('📁 Top Uploaders', "SELECT user_id, COUNT(*) c FROM user_files GROUP BY user_id ORDER BY c DESC LIMIT 10", lambda i, r: f"{i}. {_u(r[0])} — <b>{r[1]}</b>")
@R('rep', '🔗 Top Referrers')
def _r10(): return _top('🔗 Top Referrers', "SELECT inviter, COUNT(*) c FROM referrals GROUP BY inviter ORDER BY c DESC LIMIT 10", lambda i, r: f"{i}. {_u(r[0])} — <b>{r[1]}</b>")
@R('rep', '⭐ Top Points')
def _r11(): return _top('⭐ Top Points', "SELECT user_id, points FROM user_points ORDER BY points DESC LIMIT 10", lambda i, r: f"{i}. {_u(r[0])} — <b>{r[1]:g}</b>")
@R('rep', '💸 Top Spenders')
def _r12(): return _top('💸 Top Spenders', "SELECT user_id, SUM(amount_base) s FROM payments GROUP BY user_id ORDER BY s DESC LIMIT 10", lambda i, r: f"{i}. {_u(r[0])} — <b>{_money(r[1])}</b>")
@R('rep', '🕒 Recent Signups')
def _r13(): return _top('🕒 Recent Signups', "SELECT user_id, join_date FROM active_users ORDER BY join_date DESC LIMIT 10", lambda i, r: f"{i}. {_u(r[0])} · {str(r[1])[:16]}")
@R('rep', '🗂 File Types')
def _r14(): return _top('🗂 Project Types', "SELECT file_type, COUNT(*) FROM user_files GROUP BY file_type ORDER BY 2 DESC", lambda i, r: f"• {r[0] or '?'}: <b>{r[1]}</b>")
@R('rep', '📈 Uploads / Day (7d)')
def _r15(): return _top('📈 Projects Created per Day', "SELECT substr(uploaded_at,1,10) d, COUNT(*) FROM project_meta WHERE uploaded_at >= ? GROUP BY d ORDER BY d DESC", lambda i, r: f"• {r[0]}: <b>{r[1]}</b>", (_since(7),))
@R('rep', '📊 Avg Projects/User')
def _r16():
    n = sum(len(v) for v in user_files.values()); u = len(user_files)
    return f"📊 <b>Projects:</b> {n}\n👤 <b>Owners:</b> {u}\n➗ <b>Average per owner:</b> {(n / u) if u else 0:.2f}\n➗ <b>Average per user:</b> {(n / len(active_users)) if active_users else 0:.2f}"
@R('rep', '🕳 Users With 0 Projects')
def _r17():
    z = [u for u in active_users if not user_files.get(u)]
    return f"🕳 <b>Users with no projects:</b> {len(z)} of {len(active_users)}"
@R('rep', '🚧 Near Their Limit')
def _r18():
    rows = [f"• {_u(u)} — {len(v)}/{get_user_file_limit(u)}" for u, v in user_files.items() if u not in admin_ids and get_user_file_limit(u) and len(v) >= get_user_file_limit(u) - 1][:25]
    return _rows_text('🚧 Users At / Near Limit', rows)
@R('rep', '⏰ Expiring in 24h')
def _r19():
    now = _now(); rows = [f"• {_u(u)} · {s['plan_name']} · {s['expiry']:%d %b %H:%M}" for u, s in user_subscriptions.items() if s.get('expiry') and now < s['expiry'] < now + timedelta(days=1)]
    return _rows_text('⏰ Expiring within 24h', rows[:30])
@R('rep', '⌛ Recently Expired')
def _r20():
    now = _now(); rows = [f"• {_u(u)} · {s['plan_name']} · {s['expiry']:%d %b}" for u, s in user_subscriptions.items() if s.get('expiry') and now - timedelta(days=7) < s['expiry'] < now]
    return _rows_text('⌛ Expired in last 7 days', rows[:30])
@R('rep', '🗓 Expiry Calendar (7d)')
def _r21():
    now = _now(); days = {}
    for u, s in user_subscriptions.items():
        e = s.get('expiry')
        if e and now < e < now + timedelta(days=7): days[e.strftime('%a %d %b')] = days.get(e.strftime('%a %d %b'), 0) + 1
    return _rows_text('🗓 Plans ending (next 7 days)', [f"• {d}: <b>{n}</b>" for d, n in days.items()])
@R('rep', '📉 Churn (30d)')
def _r22():
    now = _now(); ch = sum(1 for s in user_subscriptions.values() if s.get('expiry') and now - timedelta(days=30) < s['expiry'] < now)
    act = sum(1 for u in user_subscriptions if has_active_sub(u))
    return f"📉 <b>Plans lapsed in 30 days:</b> {ch}\n⭐ <b>Active plans now:</b> {act}"
@R('rep', '🎯 Conversion Rate')
def _r23():
    buyers = _cnt("SELECT COUNT(DISTINCT user_id) FROM payments"); tot = len(active_users)
    return f"🎯 <b>Buyers:</b> {buyers}\n👥 <b>Users:</b> {tot}\n📈 <b>Conversion:</b> {(buyers * 100 / tot) if tot else 0:.2f}%"
@R('rep', '🛡 Admin List')
def _r24(): return _rows_text('🛡 Admins', [f"• {_u(a)}{' 👑' if a == OWNER_ID else ''}" for a in sorted(admin_ids)])
@R('rep', '🚫 Recent Bans')
def _r25(): return _top('🚫 Recent Bans', "SELECT user_id, reason, ban_date FROM banned_users ORDER BY ban_date DESC LIMIT 10", lambda i, r: f"{i}. {_u(r[0])} · {_hmx.escape(str(r[1])[:40])} · {str(r[2])[:10]}")
@R('rep', '📋 Pending Counts')
def _r26():
    return (f"📋 <b>Pending items</b>\n━━━━━━━━━━━━━━━━━━\n📄 Scripts: <b>{_cnt('SELECT COUNT(*) FROM pending_scripts')}</b>\n🗜 Zips: <b>{_cnt('SELECT COUNT(*) FROM pending_zips')}</b>\n"
            f"💳 Payments: <b>{_cnt('SELECT COUNT(*) FROM manual_payments WHERE status=?', ('pending',))}</b>")
@R('rep', '🗄 Database Stats')
def _r27():
    rows = []
    for t in ('active_users', 'user_files', 'subscriptions', 'payments', 'manual_payments', 'banned_users', 'referrals', 'points_log', 'redeem_codes', 'coupons', 'plans', 'ap_admin_log', 'ap_notes'):
        try: rows.append(f"• {t}: <b>{_cnt('SELECT COUNT(*) FROM ' + t)}</b>")
        except Exception: pass
    sz = os.path.getsize(DATABASE_PATH) if os.path.exists(DATABASE_PATH) else 0
    return _rows_text(f"🗄 Database · {_mb(sz)}", rows)
@R('rep', '⭐ Points Economy')
def _r28():
    return (f"⭐ <b>Points economy</b>\n━━━━━━━━━━━━━━━━━━\n💰 In circulation: <b>{_cnt('SELECT SUM(points) FROM user_points'):g}</b>\n"
            f"➕ Total issued: <b>{_cnt('SELECT SUM(delta) FROM points_log WHERE delta>0'):g}</b>\n➖ Total spent/removed: <b>{abs(_cnt('SELECT SUM(delta) FROM points_log WHERE delta<0')):g}</b>\n👤 Holders: <b>{_cnt('SELECT COUNT(*) FROM user_points WHERE points>0')}</b>")
@R('rep', '🎁 Claims & Redeems Today')
def _r29():
    return (f"🎁 <b>Today</b>\n━━━━━━━━━━━━━━━━━━\n📅 Daily bonus claims: <b>{_cnt('SELECT COUNT(*) FROM user_daily WHERE last_day=?', (_today(),))}</b>\n"
            f"🎟 Codes redeemed: <b>{_cnt('SELECT COUNT(*) FROM redeem_log WHERE created_at >= ?', (_today(),))}</b>")
@R('rep', '📦 Largest Projects')
def _r30():
    out = []
    for u, v in list(user_files.items()):
        for pn, _m, _t in v:
            try: out.append((_dir_size(get_user_folder(u, pn)), u, pn))
            except Exception: pass
    out.sort(reverse=True)
    return _rows_text('📦 Largest Projects', [f"{i}. {_hmx.escape(str(pn))} · {_u(u)} — <b>{_mb(s)}</b>" for i, (s, u, pn) in enumerate(out[:10], 1)])
@R('rep', '⏱ Longest-Running Bots')
def _r31():
    now = _now(); rows = []
    for k, i in list(bot_scripts.items()):
        if i.get('start_time') and _is_running(k): rows.append((now - i['start_time'], i))
    rows.sort(key=lambda x: x[0], reverse=True)
    return _rows_text('⏱ Longest-Running Bots', [f"{n}. {_hmx.escape(str(i.get('project_name')))} · {_u(i.get('script_owner_id'))} — {str(d).split('.')[0]}" for n, (d, i) in enumerate(rows[:10], 1)])
@R('rep', '🔗 Referral Stats')
def _r32():
    return (f"🔗 <b>Referrals</b>\n━━━━━━━━━━━━━━━━━━\n📨 Total: <b>{_cnt('SELECT COUNT(*) FROM referrals')}</b>\n✅ Rewarded: <b>{_cnt('SELECT COUNT(*) FROM referrals WHERE rewarded=1')}</b>\n"
            f"⏳ Pending: <b>{_cnt('SELECT COUNT(*) FROM referrals WHERE rewarded=0')}</b>\n👤 Referrers: <b>{_cnt('SELECT COUNT(DISTINCT inviter) FROM referrals')}</b>")
@R('rep', '🤖 Running Bots Now')
def _r33():
    rows = [f"• {_hmx.escape(str(i.get('project_name')))} · {_u(i.get('script_owner_id'))}" for k, i in list(bot_scripts.items()) if _is_running(k)]
    return _rows_text(f"🤖 Running now ({len(rows)})", rows[:40])
@R('rep', '🖥 Server Status')
def _r34():
    du = shutil.disk_usage(BASE_DIR); vm = psutil.virtual_memory()
    return (f"🖥 <b>Server</b>\n━━━━━━━━━━━━━━━━━━\n🧠 CPU: <b>{psutil.cpu_percent(interval=0.3)}%</b>\n💾 RAM: <b>{vm.percent}%</b> ({_mb(vm.used)} / {_mb(vm.total)})\n"
            f"💽 Disk: <b>{du.used * 100 // du.total}%</b> ({_mb(du.used)} / {_mb(du.total)})\n⏱ Bot uptime: <b>{_format_uptime(time.time() - BOT_START_TIME)}</b>")

# ---------------- 💰 REVENUE ----------------
def _rev(since):
    r = _db_q("SELECT COALESCE(SUM(amount_base),0), COUNT(*) FROM payments WHERE created_at >= ?", (since,), one=True)
    return r[0], r[1]
@R('rev', '💰 Revenue Today')
def _v1(): s, n = _rev(_today()); return f"💰 <b>Today:</b> {_money(s)} · {n} sale(s)"
@R('rev', '💰 Revenue 7d')
def _v2(): s, n = _rev(_since(7)); return f"💰 <b>Last 7 days:</b> {_money(s)} · {n} sale(s)"
@R('rev', '💰 Revenue 30d')
def _v3(): s, n = _rev(_since(30)); return f"💰 <b>Last 30 days:</b> {_money(s)} · {n} sale(s)"
@R('rev', '💰 Revenue All Time')
def _v4(): s, n = _rev(''); return f"💰 <b>All time:</b> {_money(s)} · {n} sale(s)"
@R('rev', '💳 By Method')
def _v5(): return _top('💳 Revenue by Method', "SELECT method, COUNT(*), SUM(amount_base) FROM payments GROUP BY method ORDER BY 3 DESC", lambda i, r: f"• {_hmx.escape(str(r[0]))}: <b>{_money(r[2])}</b> ({r[1]})")
@R('rev', '📦 By Plan')
def _v6(): return _top('📦 Revenue by Plan', "SELECT plan_name, COUNT(*), SUM(amount_base) FROM payments GROUP BY plan_name ORDER BY 3 DESC", lambda i, r: f"• {_hmx.escape(str(r[0]))}: <b>{_money(r[2])}</b> ({r[1]})")
@R('rev', '🧾 Last 10 Sales')
def _v7(): return _top('🧾 Last 10 Sales', "SELECT user_id, plan_name, method, amount_base, created_at FROM payments ORDER BY id DESC LIMIT 10", lambda i, r: f"{i}. {_u(r[0])} · {_hmx.escape(str(r[1]))} · {_hmx.escape(str(r[2]))} · <b>{_money(r[3])}</b> · {str(r[4])[:10]}")
@R('rev', '🧮 Avg Order Value')
def _v8():
    r = _db_q("SELECT AVG(amount_base) FROM payments WHERE amount_base>0", one=True)
    return f"🧮 <b>Average order:</b> {_money(r[0] or 0)}"
@R('rev', '🔁 Repeat Buyers')
def _v9():
    n = _cnt("SELECT COUNT(*) FROM (SELECT user_id FROM payments GROUP BY user_id HAVING COUNT(*)>1)")
    return f"🔁 <b>Repeat buyers:</b> {n} of {_cnt('SELECT COUNT(DISTINCT user_id) FROM payments')}"
@R('rev', '⏳ Pending Payments')
def _v10(): return _top('⏳ Pending Manual Payments', "SELECT rid, user_id, method_name, amount FROM manual_payments WHERE status='pending' ORDER BY rid DESC LIMIT 15", lambda i, r: f"#{r[0]} · {_u(r[1])} · {_hmx.escape(str(r[2]))} · {_hmx.escape(str(r[3]))}")
@R('rev', '❌ Rejected Count')
def _v11(): return f"❌ <b>Rejected payments:</b> {_cnt('SELECT COUNT(*) FROM manual_payments WHERE status NOT IN (?,?)', ('pending', 'approved'))}\n✅ <b>Approved:</b> {_cnt('SELECT COUNT(*) FROM manual_payments WHERE status=?', ('approved',))}"
@R('rev', '⭐ Stars Sales')
def _v12():
    r = _db_q("SELECT COUNT(*), COALESCE(SUM(amount_base),0) FROM payments WHERE lower(method) LIKE '%star%'", one=True)
    return f"⭐ <b>Telegram Stars sales:</b> {r[0]} · {_money(r[1])}"
@R('rev', '🪙 Points Purchases')
def _v13():
    return f"🪙 <b>Plans bought with points:</b> {_cnt('SELECT COUNT(*) FROM payments WHERE method=?', ('Points',))}"
@R('rev', '🏷 Coupons Overview')
def _v14(): return _top('🏷 Coupons', "SELECT code, percent, used, max_uses, active FROM coupons ORDER BY used DESC LIMIT 15", lambda i, r: f"• <code>{_hmx.escape(str(r[0]))}</code> {r[1]:g}% · used {r[2]}/{r[3] or '∞'} {'✅' if r[4] else '⛔'}")
@R('rev', '📅 Best Sales Day')
def _v15():
    r = _db_q("SELECT substr(created_at,1,10) d, SUM(amount_base) s FROM payments GROUP BY d ORDER BY s DESC LIMIT 1", one=True)
    return f"📅 <b>Best day:</b> {r[0]} — {_money(r[1])}" if r else "No sales yet."
@R('rev', '👤 Revenue per User')
def _v16():
    s, _n = _rev(''); u = len(active_users)
    return f"👤 <b>Revenue per user:</b> {_money(s / u) if u else 0}\n👥 Users: {u}"
@A('rev', '📤 Export Sales CSV')
def _v17(call):
    import csv
    p = os.path.join(tempfile.gettempdir(), f"sales_{int(time.time())}.csv")
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['id', 'user_id', 'plan_id', 'plan', 'method', 'amount_base', 'currency', 'ref', 'created_at'])
        w.writerows(_db_q("SELECT id,user_id,plan_id,plan_name,method,amount_base,currency,ref,created_at FROM payments ORDER BY id"))
    with open(p, 'rb') as f: bot.send_document(call.message.chat.id, f, caption="🧾 All sales")
    os.remove(p); return "✅ Sales CSV sent."

# ---------------- 📤 UPLOADS & SECURITY ----------------
TOG('upl', 'Uploads Enabled', 'UP_ENABLED')
TOG('upl', 'Allow .py', 'UP_ALLOW_PY')
TOG('upl', 'Allow .js', 'UP_ALLOW_JS')
TOG('upl', 'Allow .zip', 'UP_ALLOW_ZIP')
TOG('upl', 'Premium-only Uploads', 'UP_PREMIUM_ONLY')
TOG('upl', 'Require @username', 'UP_REQUIRE_USERNAME')
TOG('upl', 'Forward Files to Owner', 'UP_FWD_OWNER')
NUM('upl', 'Upload Cooldown', 'UP_COOLDOWN_SEC', 0, 3600, 's')
NUM('upl', 'Daily Upload Limit', 'UP_DAILY_LIMIT', 0, 1000)
NUM('upl', 'Max Name Length', 'UP_NAME_MAXLEN', 5, 60)
NUM('upl', 'Free Max File MB', 'UP_MAXMB_FREE', 0, 500, ' MB')
TOG('upl', 'Security Scan', 'SEC_SCAN_ON')
_ap('upl', 'txt', 'Blocked Words', key='SEC_BLOCK_WORDS', prompt="Send blocked words separated by commas (code containing any is flagged). Send - to clear.")
TOG('upl', 'Log Admin Actions', 'SEC_LOG_ADMIN')
@R('upl', '📥 Uploads Today')
def _s1(): return f"📥 <b>Uploads today:</b> {_cnt('SELECT COUNT(*) FROM ap_uploads WHERE ts >= ?', (_today(),))}\n👤 <b>Uploaders:</b> {_cnt('SELECT COUNT(DISTINCT user_id) FROM ap_uploads WHERE ts >= ?', (_today(),))}"
@R('upl', '🏅 Top Uploaders Today')
def _s2(): return _top('🏅 Top Uploaders Today', "SELECT user_id, COUNT(*) c FROM ap_uploads WHERE ts >= ? GROUP BY user_id ORDER BY c DESC LIMIT 10", lambda i, r: f"{i}. {_u(r[0])} — <b>{r[1]}</b>", (_today(),))
@R('upl', '📜 Admin Action Log')
def _s3(): return _top('📜 Last Admin Actions', "SELECT admin_id, action, ts FROM ap_admin_log ORDER BY id DESC LIMIT 20", lambda i, r: f"• {str(r[2])[5:16]} · <code>{r[0]}</code> · {_hmx.escape(str(r[1]))}")
@C('upl', '🧽 Clear Admin Log', 'This deletes the whole admin action log.')
def _s4(call): _db_exec("DELETE FROM ap_admin_log"); return "✅ Admin log cleared."

# ---------------- 🤖 HOSTING CONTROL ----------------
TOG('run', 'Block New Starts', 'RUN_BLOCK_START')
TOG('run', 'Auto-stop Expired', 'RUN_AUTO_STOP_EXPIRED')
TOG('run', 'Auto-restart Crashed', 'RUN_AUTO_RESTART')
TOG('run', 'Notify User on Crash', 'RUN_NOTIFY_CRASH')
NUM('run', 'Max Running / User', 'RUN_MAX_PER_USER', 0, 100)
NUM('run', 'Max Running Total', 'RUN_MAX_TOTAL', 0, 10000)
NUM('run', 'Max Restarts / Hour', 'RUN_RESTART_MAX', 1, 50)
NUM('run', 'Free Max Hours', 'RUN_MAX_HOURS_FREE', 0, 720, ' h')
NUM('run', 'RAM Limit / Bot', 'RUN_MEM_LIMIT_MB', 0, 16000, ' MB')
NUM('run', 'Log Size Cap', 'RUN_LOG_MAX_MB', 0, 500, ' MB')
def _stop_where(pred):
    n = 0
    for k, i in list(bot_scripts.items()):
        try:
            if pred(i.get('script_owner_id')) and _is_running(k): kill_process_tree(i); bot_scripts.pop(k, None); n += 1
        except Exception: pass
    return n
@C('run', '⏹ Stop ALL Bots', 'This stops every running user bot (admins excluded).')
def _h1(call): return f"⏹ Stopped <b>{_stop_where(lambda o: o not in admin_ids)}</b> bot(s)."
@C('run', '⏹ Stop Free Users\' Bots', 'This stops bots of every user without a premium plan.')
def _h2(call): return f"⏹ Stopped <b>{_stop_where(lambda o: o not in admin_ids and not has_active_sub(o))}</b> bot(s)."
@A('run', '⏹ Stop Expired Users\' Bots')
def _h3(call): return f"⏹ Stopped <b>{_stop_where(lambda o: o not in admin_ids and not has_active_sub(o) and o in user_subscriptions)}</b> bot(s)."
@Q('run', '⏹ Stop a User\'s Bots', "Send the user ID whose bots should be stopped.")
def _h4(m, t): uid, _ = _parse_uid(t); return f"⏹ Stopped <b>{_stop_where(lambda o: o == uid)}</b> bot(s) of {_u(uid)}."
@Q('run', '▶️ Start a User\'s Bots', "Send the user ID whose projects should be started.")
def _h5(m, t):
    uid, _ = _parse_uid(t); n = 0
    for pn, _m, _t in list(user_files.get(uid, [])):
        if not is_bot_running(uid, pn) and _ap_restart(uid, pn): n += 1
    return f"▶️ Started <b>{n}</b> project(s) of {_u(uid)}."
@A('run', '🔄 Restart All Running')
def _h6(call):
    n = 0
    for k, i in list(bot_scripts.items()):
        if _is_running(k):
            o, p = i.get('script_owner_id'), i.get('project_name'); kill_process_tree(i); bot_scripts.pop(k, None)
            if _ap_restart(o, p): n += 1
    return f"🔄 Restarted <b>{n}</b> bot(s)."
@R('run', '🧠 Top RAM Bots')
def _h7():
    out = []
    for k, i in list(bot_scripts.items()):
        try:
            p = psutil.Process(i['process'].pid); rss = p.memory_info().rss + sum(c.memory_info().rss for c in p.children(recursive=True)); out.append((rss, i))
        except Exception: pass
    out.sort(key=lambda x: x[0], reverse=True)
    return _rows_text('🧠 Top RAM Bots', [f"{n}. {_hmx.escape(str(i.get('project_name')))} · {_u(i.get('script_owner_id'))} — <b>{_mb(r)}</b>" for n, (r, i) in enumerate(out[:10], 1)])
@R('run', '🔥 Top CPU Bots')
def _h8():
    out = []
    for k, i in list(bot_scripts.items()):
        try: out.append((psutil.Process(i['process'].pid).cpu_percent(interval=0.1), i))
        except Exception: pass
    out.sort(key=lambda x: x[0], reverse=True)
    return _rows_text('🔥 Top CPU Bots', [f"{n}. {_hmx.escape(str(i.get('project_name')))} · {_u(i.get('script_owner_id'))} — <b>{c:.1f}%</b>" for n, (c, i) in enumerate(out[:10], 1)])

# ---------------- 👥 USERS & ACCESS ----------------
TOG('usr', 'Notify on Ban/Unban', 'USR_NOTIFY_BAN')
TOG('usr', 'Force-Join Check', 'FJ_ENABLED')
NUM('usr', 'Free Trial Days', 'USR_TRIAL_DAYS', 0, 365, ' d')
NUM('usr', 'Signup Bonus Points', 'USR_SIGNUP_POINTS', 0, 100000)
@Q('usr', '🔎 User Lookup Card', "Send the user ID.")
def _u1(m, t):
    uid, _ = _parse_uid(t); fn, un, jd, ls = get_profile(uid)
    sub = user_subscriptions.get(uid) or {}
    card = (f"🔎 <b>User card</b>\n━━━━━━━━━━━━━━━━━━\n🆔 <code>{uid}</code>\n👤 {_hmx.escape(fn or '-')} @{_hmx.escape(un or '-')}\n🏅 {rank_plain(uid)}\n"
            f"🚫 Banned: {'Yes' if uid in banned_users else 'No'}\n📁 Projects: {len(user_files.get(uid, []))}/{get_user_file_limit(uid)}\n"
            f"⭐ Points: {_cnt('SELECT points FROM user_points WHERE user_id=?', (uid,)):g}\n🔗 Referrals: {_cnt('SELECT COUNT(*) FROM referrals WHERE inviter=?', (uid,))}\n"
            f"💸 Spent: {_money(_cnt('SELECT SUM(amount_base) FROM payments WHERE user_id=?', (uid,)))}\n📅 Joined: {str(jd)[:10]} · Seen: {str(ls)[:16]}")
    if sub.get('expiry'): card += f"\n⏳ Plan ends: {sub['expiry']:%d %b %Y}"
    return card
@Q('usr', '🎁 Grant Plan Days', "Send: <user id> <days>   e.g. 123456 30")
def _u2(m, t):
    uid, rest = _parse_uid(t); d = int(rest)
    _g = _ar_guard(m.from_user.id, 'grant', d)
    if _g: return _g
    cur = user_subscriptions.get(uid); base = cur['expiry'] if cur and cur.get('expiry') and cur['expiry'] > _now() else _now()
    save_subscription(uid, base + timedelta(days=d), None if cur else 'Admin Grant', None)
    try: bot.send_message(uid, f"🎁 An admin gave you <b>{d} day(s)</b> of premium!", parse_mode='HTML')
    except Exception: pass
    return f"✅ {_u(uid)} now has premium until {user_subscriptions[uid]['expiry']:%d %b %Y}."
@Q('usr', '🚫 Revoke Premium', "Send the user ID to remove premium from.")
def _u3(m, t): uid, _ = _parse_uid(t); remove_subscription_db(uid); return f"✅ Premium removed from {_u(uid)}."
@Q('usr', '⏳ Temp Ban', "Send: <user id> <hours>   e.g. 123456 24")
def _u4(m, t):
    uid, rest = _parse_uid(t); h = int(rest)
    if uid in admin_ids: return "❌ Can't ban an admin."
    ban_user_db(uid, f"Temporary ban ({h}h)", m.from_user.id)
    _db_exec("INSERT OR REPLACE INTO ap_tempban (user_id, until) VALUES (?,?)", (uid, (_now() + timedelta(hours=h)).isoformat()))
    return f"⏳ {_u(uid)} banned for {h} hour(s)."
@Q('usr', '📝 Add Note', "Send: <user id> <note text>")
def _u5(m, t):
    uid, note = _parse_uid(t)
    if not note: return "❌ Add the note text after the ID."
    _db_exec("INSERT INTO ap_notes (user_id, note, by_admin, ts) VALUES (?,?,?,?)", (uid, note[:500], m.from_user.id, _now().isoformat()))
    return f"📝 Note saved for {_u(uid)}."
@Q('usr', '📖 View Notes', "Send the user ID.")
def _u6(m, t):
    uid, _ = _parse_uid(t)
    return _rows_text(f"📖 Notes · {uid}", [f"• {str(r[1])[:10]} — {_hmx.escape(r[0])}" for r in _db_q("SELECT note, ts FROM ap_notes WHERE user_id=? ORDER BY id DESC LIMIT 15", (uid,))])
@R('usr', '🗒 Latest Notes')
def _u7(): return _top('🗒 Latest Notes', "SELECT user_id, note FROM ap_notes ORDER BY id DESC LIMIT 10", lambda i, r: f"• {_u(r[0])}: {_hmx.escape(r[1][:60])}")
@Q('usr', '🗑 Delete All Projects', "Send: <user id> confirm   (this deletes ALL their projects and files)")
def _u8(m, t):
    uid, rest = _parse_uid(t)
    if rest.lower() != 'confirm': return "❌ Cancelled — type the ID followed by the word confirm."
    n = 0
    for pn, _m, _t in list(user_files.get(uid, [])):
        k = f"{uid}_{pn}"
        if k in bot_scripts: kill_process_tree(bot_scripts[k]); bot_scripts.pop(k, None)
        shutil.rmtree(get_user_folder(uid, pn), ignore_errors=True); remove_user_file_db(uid, pn); n += 1
    return f"🗑 Deleted <b>{n}</b> project(s) of {_u(uid)}."
@Q('usr', '📅 Reset Daily Claim', "Send the user ID.")
def _u9(m, t): uid, _ = _parse_uid(t); _db_exec("DELETE FROM user_daily WHERE user_id=?", (uid,)); return f"✅ Daily claim reset for {_u(uid)}."
@C('usr', '✅ Unban Everyone', 'This unbans every banned user.')
def _u10(call):
    ids = list(banned_users)
    for u in ids: unban_user_db(u)
    return f"✅ Unbanned <b>{len(ids)}</b> user(s)."
@Q('usr', '🔧 Set Custom Limit', "Send: <user id> <project limit>")
def _u11(m, t): uid, rest = _parse_uid(t); set_user_limit_db(uid, int(rest), m.from_user.id); return f"✅ {_u(uid)} limit = <b>{int(rest)}</b>."
@Q('usr', '♻️ Remove Custom Limit', "Send the user ID.")
def _u12(m, t): uid, _ = _parse_uid(t); remove_user_limit_db(uid); return f"✅ Custom limit removed for {_u(uid)}."
@R('usr', '🔧 Custom Limits List')
def _u13(): return _top('🔧 Users With Custom Limits', "SELECT user_id, file_limit FROM user_limits ORDER BY file_limit DESC LIMIT 30", lambda i, r: f"• {_u(r[0])} — <b>{r[1]}</b>")
@C('usr', '🧹 Clear All Custom Limits', 'This removes every custom project limit.')
def _u14(call):
    for u in list(user_limits): remove_user_limit_db(u)
    return "✅ All custom limits cleared."
@Q('usr', '🔍 Find User by Name', "Send part of the name or @username.")
def _u15(m, t):
    q = '%' + t.strip().lstrip('@') + '%'
    return _top('🔍 Matches', "SELECT user_id, first_name, username FROM active_users WHERE first_name LIKE ? OR username LIKE ? LIMIT 15", lambda i, r: f"• <code>{r[0]}</code> {_hmx.escape(r[1] or '')} @{_hmx.escape(r[2] or '-')}", (q, q))
@Q('usr', '➕ Give Points', "Send: <user id> <points>")
def _u16(m, t): uid, rest = _parse_uid(t); _lb_add_points(uid, float(rest), 'admin_toolbox'); return f"✅ Gave <b>{float(rest):g}</b> points to {_u(uid)}."
@Q('usr', '➖ Take Points', "Send: <user id> <points>")
def _u17(m, t): uid, rest = _parse_uid(t); _lb_add_points(uid, -float(rest), 'admin_toolbox'); return f"✅ Took <b>{float(rest):g}</b> points from {_u(uid)}."
@Q('usr', '⏩ Extend ALL Premium', "Send the number of days to add to every active premium plan.")
def _u18(m, t):
    d = int(t.strip()); n = 0
    for u, s in list(user_subscriptions.items()):
        if has_active_sub(u): save_subscription(u, s['expiry'] + timedelta(days=d)); n += 1
    return f"⏩ Extended <b>{n}</b> plan(s) by {d} day(s)."
@Q('usr', '📜 User Points History', "Send the user ID.")
def _u19(m, t):
    uid, _ = _parse_uid(t)
    return _rows_text(f"📜 Points · {uid}", [f"• {str(r[2])[5:16]} · <b>{r[0]:+g}</b> · {_hmx.escape(str(r[1]))}" for r in _db_q("SELECT delta, reason, created_at FROM points_log WHERE user_id=? ORDER BY id DESC LIMIT 15", (uid,))])
@Q('usr', '📁 User Projects', "Send the user ID.")
def _u20(m, t):
    uid, _ = _parse_uid(t)
    return _rows_text(f"📁 Projects · {uid}", [f"• {_hmx.escape(str(pn))} ({ft}) {'🟢' if is_bot_running(uid, pn) else '⚪'}" for pn, _m, ft in user_files.get(uid, [])])

# ---------------- 🔔 NOTIFICATIONS ----------------
TOG('ntf', 'Plan-expired → Admin', 'NTF_EXPIRY_ADMIN')
TOG('ntf', 'Daily Report → Owner', 'NTF_DAILY_REPORT')
NUM('ntf', 'Report Hour (0-23)', 'NTF_DAILY_HOUR', 0, 23, ':00')
TOG('ntf', 'Startup DM', 'NTF_STARTUP_DM')
TOG('ntf', 'Error DM', 'NTF_ERROR_DM')
TOG('ntf', 'Crash → Admins', 'NTF_CRASH_ADMIN')
@A('ntf', '📰 Send Daily Report Now')
def _n1(call): bot.send_message(call.from_user.id, _ap_daily_report(), parse_mode='HTML'); return "✅ Report sent."
@A('ntf', '🔔 Test DM to Me')
def _n2(call): bot.send_message(call.from_user.id, "🔔 Test notification from the Admin Toolbox."); return "✅ Test sent."
def _blast(m, uids, text, label):
    uids = [u for u in uids if u not in banned_users]; chat = m.chat.id
    def work():
        ok = 0
        for u in uids:
            try: bot.send_message(u, text, parse_mode='HTML'); ok += 1
            except Exception: pass
            time.sleep(0.06)
        try: bot.send_message(chat, f"📬 {label}: delivered to <b>{ok}/{len(uids)}</b>.", parse_mode='HTML')
        except Exception: pass
    threading.Thread(target=work, daemon=True).start()
    return f"📬 Sending to <b>{len(uids)}</b> user(s) in the background…"
@Q('ntf', '📣 Message All Admins', "Send the message for all admins.")
def _n3(m, t): return _blast(m, list(admin_ids), t, 'Admins')
@Q('ntf', '💬 Message One User', "Send: <user id> <message>")
def _n4(m, t):
    uid, txt = _parse_uid(t)
    bot.send_message(uid, txt, parse_mode='HTML'); return f"✅ Sent to {_u(uid)}."
@Q('ntf', '💎 Message Premium Users', "Send the message for all premium users.")
def _n5(m, t): return _blast(m, [u for u in active_users if has_active_sub(u)], t, 'Premium')
@Q('ntf', '🆓 Message Free Users', "Send the message for all free users.")
def _n6(m, t): return _blast(m, [u for u in active_users if not has_active_sub(u)], t, 'Free users')
@Q('ntf', '🕳 Nudge No-Project Users', "Send the message for users who haven't uploaded any project.")
def _n7(m, t): return _blast(m, [u for u in active_users if not user_files.get(u) and u not in admin_ids], t, 'No-project users')
@Q('ntf', '😴 Win-back (30d inactive)', "Send the message for users not seen in 30+ days.")
def _n8(m, t):
    ids = [r[0] for r in _db_q("SELECT user_id FROM active_users WHERE last_seen < ?", (_since(30),))]
    return _blast(m, ids, t, 'Win-back')
@Q('ntf', '⏰ Message Expiring (3d)', "Send the message for users whose plan ends within 3 days.")
def _n9(m, t):
    now = _now(); ids = [u for u, s in user_subscriptions.items() if s.get('expiry') and now < s['expiry'] < now + timedelta(days=3)]
    return _blast(m, ids, t, 'Expiring')
@Q('ntf', '🆕 Message New Users (7d)', "Send the message for users who joined in the last 7 days.")
def _n10(m, t): return _blast(m, [r[0] for r in _db_q("SELECT user_id FROM active_users WHERE join_date >= ?", (_since(7),))], t, 'New users')

# ---------------- 🧹 MAINTENANCE ----------------
@A('mnt', '🗜 Vacuum Database')
def _m1(call):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH); conn.execute('VACUUM'); conn.close()
    return f"✅ Database optimized ({_mb(os.path.getsize(DATABASE_PATH))})."
@A('mnt', '💾 Send DB Backup')
def _m2(call):
    p = os.path.join(tempfile.gettempdir(), f"backup_{int(time.time())}.db")
    with DB_LOCK:
        src = sqlite3.connect(DATABASE_PATH); dst = sqlite3.connect(p); src.backup(dst); dst.close(); src.close()
    with open(p, 'rb') as f: bot.send_document(call.message.chat.id, f, caption=f"💾 Backup {_now():%d %b %Y %H:%M}")
    os.remove(p); return "✅ Backup sent."
@C('mnt', '🧺 Clean Orphan Folders', 'Deletes project folders (older than 1 day) that have no database record.')
def _m3(call):
    n = 0
    if os.path.isdir(UPLOAD_BOTS_DIR):
        for u in os.listdir(UPLOAD_BOTS_DIR):
            ud = os.path.join(UPLOAD_BOTS_DIR, u)
            if not (os.path.isdir(ud) and u.isdigit()): continue
            known = {pn for pn, _m, _t in user_files.get(int(u), [])}
            for d in os.listdir(ud):
                dp = os.path.join(ud, d)
                if os.path.isdir(dp) and d not in known and time.time() - os.path.getmtime(dp) > 86400:
                    shutil.rmtree(dp, ignore_errors=True); n += 1
    return f"🧺 Removed <b>{n}</b> orphan folder(s)."
@A('mnt', '📄 Delete Logs > 7d')
def _m4(call):
    n = 0
    for u, v in list(user_files.items()):
        for pn, _m, _t in v:
            if is_bot_running(u, pn): continue
            lp = os.path.join(get_user_folder(u, pn), f"{pn}.log")
            if os.path.exists(lp) and time.time() - os.path.getmtime(lp) > 7 * 86400:
                try: os.remove(lp); n += 1
                except Exception: pass
    return f"📄 Deleted <b>{n}</b> old log(s)."
@A('mnt', '🐍 Clean __pycache__')
def _m5(call):
    n = 0
    for r, ds, _f in os.walk(UPLOAD_BOTS_DIR):
        for d in list(ds):
            if d == '__pycache__': shutil.rmtree(os.path.join(r, d), ignore_errors=True); ds.remove(d); n += 1
    return f"🐍 Removed <b>{n}</b> __pycache__ folder(s)."
@A('mnt', '🧟 Clear Dead Processes')
def _m6(call):
    n = 0
    for k in list(bot_scripts):
        if not _is_running(k): bot_scripts.pop(k, None); n += 1
    return f"🧟 Cleared <b>{n}</b> dead entr{'y' if n == 1 else 'ies'}."
@A('mnt', '🔃 Reload Data from DB')
def _m7(call):
    for d in (user_files, user_subscriptions, user_limits): d.clear()
    banned_users.clear(); active_users.clear(); load_data()
    return f"🔃 Reloaded: {len(active_users)} users, {sum(len(v) for v in user_files.values())} projects."
@A('mnt', '🗑 Remove Expired Subs')
def _m8(call):
    now = _now(); ids = [u for u, s in list(user_subscriptions.items()) if s.get('expiry') and s['expiry'] < now]
    for u in ids: remove_subscription_db(u)
    return f"🗑 Removed <b>{len(ids)}</b> expired subscription(s)."
@R('mnt', '🧠 Memory Report')
def _m9():
    import gc; gc.collect(); p = psutil.Process()
    return f"🧠 <b>Bot process</b>\n━━━━━━━━━━━━━━━━━━\nRAM: <b>{_mb(p.memory_info().rss)}</b>\nThreads: <b>{threading.active_count()}</b>\nOpen files: <b>{len(p.open_files())}</b>\nChildren: <b>{len(p.children())}</b>"
@A('mnt', '⚙️ Export Settings JSON')
def _m10(call):
    rows = _db_q("SELECT key, value FROM settings")
    p = os.path.join(tempfile.gettempdir(), f"settings_{int(time.time())}.json")
    with open(p, 'w', encoding='utf-8') as f: json.dump(dict(rows), f, indent=1, ensure_ascii=False)
    with open(p, 'rb') as f: bot.send_document(call.message.chat.id, f, caption="⚙️ All settings")
    os.remove(p); return "✅ Settings exported."
@C('mnt', '🧮 Purge Points Log > 90d', 'Deletes points history older than 90 days (balances are kept).')
def _m11(call): rc, _ = _db_exec("DELETE FROM points_log WHERE created_at < ?", (_since(90),)); return f"🧮 Removed <b>{rc}</b> log row(s)."
@A('mnt', '🎟 Purge Dead Redeem Codes')
def _m12(call):
    rc, _ = _db_exec("DELETE FROM redeem_codes WHERE (max_uses>0 AND used>=max_uses) OR (expires_at IS NOT NULL AND expires_at<>'' AND expires_at < ?)", (_now().isoformat(),))
    return f"🎟 Removed <b>{rc}</b> expired/used-up code(s)."
@A('mnt', '🧾 Purge Orphan Meta')
def _m13(call):
    rc, _ = _db_exec("DELETE FROM project_meta WHERE NOT EXISTS (SELECT 1 FROM user_files f WHERE f.user_id=project_meta.user_id AND f.project_name=project_meta.project_name)")
    return f"🧾 Removed <b>{rc}</b> orphan row(s)."
@R('mnt', '💽 Disk Usage')
def _m14():
    du = shutil.disk_usage(BASE_DIR)
    return f"💽 <b>Disk</b>\n━━━━━━━━━━━━━━━━━━\nUploads folder: <b>{_mb(_dir_size(UPLOAD_BOTS_DIR))}</b>\nDatabase: <b>{_mb(os.path.getsize(DATABASE_PATH))}</b>\nFree: <b>{_mb(du.free)}</b> of {_mb(du.total)}"
@A('mnt', '🧹 Purge Upload Counters')
def _m15(call): rc, _ = _db_exec("DELETE FROM ap_uploads WHERE ts < ?", (_since(7),)); return f"🧹 Removed <b>{rc}</b> old counter row(s)."
@C('mnt', '📅 Reset ALL Daily Claims', 'Everyone can claim the daily bonus again.')
def _m16(call): rc, _ = _db_exec("DELETE FROM user_daily"); return f"📅 Reset <b>{rc}</b> claim(s)."
@A('mnt', '🔒 Lock / Unlock Bot')
def _m17(call):
    global bot_locked
    bot_locked = not bot_locked
    return "🔒 Bot is now <b>LOCKED</b> (users can't use it)." if bot_locked else "🔓 Bot is now <b>UNLOCKED</b>."
@R('mnt', '🛠 System Info')
def _m18():
    import platform
    return f"🛠 <b>System</b>\n━━━━━━━━━━━━━━━━━━\nPython: <b>{sys.version.split()[0]}</b>\nOS: <b>{platform.system()} {platform.release()}</b>\nCPU cores: <b>{psutil.cpu_count()}</b>\nUptime: <b>{_format_uptime(time.time() - BOT_START_TIME)}</b>"
@R('mnt', '🔢 Settings Count')
def _m19(): return f"🔢 <b>Saved settings:</b> {_cnt('SELECT COUNT(*) FROM settings')}\n🎛 <b>Toolbox options:</b> {len(AP_OPTS)}"

# ============================================================
# --- Admin Toolbox: interface ---
# ============================================================
_AP_PAGE = 10
def _ap_cat_idx(cat): return [i for i, o in enumerate(AP_OPTS) if o['cat'] == cat]
def _ap_label(i):
    o = AP_OPTS[i]; k = o['kind']
    if k == 'tog': return ('✅ ' if _lbf(o['key']) else '❌ ') + o['label']
    if k == 'num': return f"{o['label']}: {int(_lbn(o['key']))}{o['unit']}"
    if k == 'txt': return f"{o['label']}: {'set' if _lbs(o['key']) else 'none'}"
    return o['label']
def _ap_home_markup():
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
    for c, name in AP_CATS: m.add(B(f"{name} ({len(_ap_cat_idx(c))})", callback_data=f"ap_c_{c}_0"))
    m.add(B('🔙 Back to Admin Panel', callback_data='admin_panel'))
    return m
def _ap_home_text(): return f"🧩 <b>Admin Toolbox</b> · <b>{len(AP_OPTS)}</b> options\n━━━━━━━━━━━━━━━━━━\nPick a category. Toggles and numbers apply instantly."
def _ap_cat_view(cat, page):
    B = types.InlineKeyboardButton; ids = _ap_cat_idx(cat); pages = max(1, (len(ids) + _AP_PAGE - 1) // _AP_PAGE); page = max(0, min(page, pages - 1))
    m = types.InlineKeyboardMarkup(row_width=2)
    chunk = ids[page * _AP_PAGE:(page + 1) * _AP_PAGE]
    for a in range(0, len(chunk), 2):
        m.row(*[B(_ap_label(i), callback_data=f"ap_o_{i}") for i in chunk[a:a + 2]])
    nav = []
    if page > 0: nav.append(B('⬅️', callback_data=f"ap_c_{cat}_{page - 1}"))
    nav.append(B(f"{page + 1}/{pages}", callback_data=f"ap_c_{cat}_{page}"))
    if page < pages - 1: nav.append(B('➡️', callback_data=f"ap_c_{cat}_{page + 1}"))
    m.row(*nav); m.row(B('🔙 Toolbox', callback_data='ap_h'))
    name = dict(AP_CATS)[cat]
    return f"<b>{name}</b> · page {page + 1}/{pages}\n━━━━━━━━━━━━━━━━━━\nTap an option.", m
def _ap_back_markup(i):
    B = types.InlineKeyboardButton; cat = AP_OPTS[i]['cat']; pg = _ap_cat_idx(cat).index(i) // _AP_PAGE
    m = types.InlineKeyboardMarkup(); m.row(B('🔙 Back', callback_data=f"ap_c_{cat}_{pg}"), B('🖥 Monitor' if cat == 'sys' else '🧩 Toolbox', callback_data='sm_home' if cat == 'sys' else 'ap_h')); return m
def _ap_out(chat_id, text, i, call=None):
    mk = _ap_back_markup(i)
    if call is not None and len(text) <= 3800:
        try: bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode='HTML', reply_markup=mk); return
        except Exception as e:
            if 'not modified' in str(e): return
    _say(chat_id, text, mk)
def _ap_run(i, call, fn, *a):
    try: res = fn(*a)
    except ValueError: res = "❌ Invalid input. Check the format shown in the prompt and try again."
    except Exception as e: logger.warning(f"toolbox option failed: {e}"); res = f"❌ Failed: {_hmx.escape(str(e)[:200])}"
    return res
def _ap_ask(call, i, prompt, handler):
    msg = bot.send_message(call.message.chat.id, f"{prompt}\n\n<i>Send /cancel to abort.</i>", parse_mode='HTML')
    bot.register_next_step_handler(msg, handler)

def toolbox_callback(call):
    d = call.data
    try: bot.answer_callback_query(call.id)
    except Exception: pass
    chat = call.message.chat.id
    if d == 'ap_h': return _rp_edit(call, _ap_home_text(), _ap_home_markup())
    if d.startswith('ap_c_'):
        _, _, cat, pg = d.split('_'); t, m = _ap_cat_view(cat, int(pg)); return _rp_edit(call, t, m)
    if d.startswith('ap_y_'):
        i = int(d[5:]); o = AP_OPTS[i]; res = _ap_run(i, call, o['fn'], call); return _ap_out(chat, res, i, call)
    if not d.startswith('ap_o_'): return
    i = int(d[5:]); o = AP_OPTS[i]; k = o['kind']
    if k == 'tog':
        set_setting(o['key'], '0' if _lbf(o['key']) else '1')
        t, m = _ap_cat_view(o['cat'], _ap_cat_idx(o['cat']).index(i) // _AP_PAGE); return _rp_edit(call, t, m)
    if k == 'rep': return _ap_out(chat, _ap_run(i, call, o['fn']), i, call)
    if k == 'act': return _ap_out(chat, _ap_run(i, call, o['fn'], call), i, call)
    if k == 'cfm':
        B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup()
        m.row(B('✅ Yes, do it', callback_data=f"ap_y_{i}"), B('❌ Cancel', callback_data=f"ap_c_{o['cat']}_{_ap_cat_idx(o['cat']).index(i) // _AP_PAGE}"))
        return _rp_edit(call, f"⚠️ <b>{_hmx.escape(o['label'])}</b>\n{_hmx.escape(o['warn'])}\n\nAre you sure?", m)
    if k in ('num', 'txt'):
        cur = _lbs(o['key']); hint = f"{o['lo']} – {o['hi']}" if k == 'num' else ''
        def h(m):
            if not m.text or m.text.strip().lower() == '/cancel' or m.from_user.id not in admin_ids: return bot.send_message(m.chat.id, "Cancelled.")
            try:
                if k == 'num':
                    v = int(float(m.text.strip()))
                    if not (o['lo'] <= v <= o['hi']): raise ValueError
                    set_setting(o['key'], str(v)); shown = str(v)
                else:
                    v = '' if m.text.strip() == '-' else m.text.strip()[:500]; set_setting(o['key'], v); shown = v or 'cleared'
            except ValueError: return bot.send_message(m.chat.id, f"❌ Send a whole number between {o['lo']} and {o['hi']}." if k == 'num' else "❌ Invalid text.")
            bot.send_message(m.chat.id, f"✅ <b>{_hmx.escape(o['label'])}</b> → <code>{_hmx.escape(shown)}</code>", parse_mode='HTML', reply_markup=_ap_back_markup(i))
        return _ap_ask(call, i, f"✏️ <b>{_hmx.escape(o['label'])}</b>\nCurrent: <code>{_hmx.escape(cur)}</code>\n" + (f"Allowed: {hint} (0 = off/unlimited where it makes sense)" if k == 'num' else o['prompt']), h)
    if k == 'ask':
        def h(m):
            if not m.text or m.text.strip().lower() == '/cancel' or m.from_user.id not in admin_ids: return bot.send_message(m.chat.id, "Cancelled.")
            res = _ap_run(i, call, o['fn'], m, m.text)
            _say(m.chat.id, res, _ap_back_markup(i))
        return _ap_ask(call, i, f"<b>{_hmx.escape(o['label'])}</b>\n{o['prompt']}", h)


# ============================================================
# --- Backup & Restore: export / import the entire bot ---
# ============================================================
LB_DEF.update({'BKP_AUTO': '0', 'BKP_AUTO_HOURS': '24', 'BKP_AUTO_FULL': '0'})
_BKP_PENDING = {}      # admin id -> {'zip': path, 'info': str}
_BKP_CHUNK = 18 * 1048576
_BKP_SKIP_DIRS = {'node_modules', '__pycache__', '.git', 'venv', '.venv'}
_BKP_BUSY = {'on': False}

def _bkp_make(full):
    """Build the backup zip, return its path."""
    ts = datetime.now().strftime('%Y%m%d_%H%M')
    tmpdir = tempfile.mkdtemp(prefix='fenixbkp_')
    snap = os.path.join(tmpdir, 'bot_data.db')
    with DB_LOCK:
        src = sqlite3.connect(DATABASE_PATH); dst = sqlite3.connect(snap); src.backup(dst); dst.close(); src.close()
    out = os.path.join(tempfile.gettempdir(), f"fenix_backup_{'full' if full else 'data'}_{ts}.zip")
    files = 0
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(snap, 'bot_data.db')
        if full and os.path.isdir(UPLOAD_BOTS_DIR):
            for r, ds, fs in os.walk(UPLOAD_BOTS_DIR):
                ds[:] = [d for d in ds if d not in _BKP_SKIP_DIRS]
                for f in fs:
                    if f.endswith('.log'): continue
                    fp = os.path.join(r, f)
                    try: z.write(fp, os.path.join('upload_bots', os.path.relpath(fp, UPLOAD_BOTS_DIR))); files += 1
                    except Exception: pass
        manifest = {'app': 'fenix-hosting-bot', 'version': 1, 'created': datetime.now().isoformat(), 'full': bool(full),
                    'files': files, 'users': len(active_users), 'projects': sum(len(v) for v in user_files.values())}
        z.writestr('manifest.json', json.dumps(manifest, indent=1))
    shutil.rmtree(tmpdir, ignore_errors=True)
    return out, manifest

def _bkp_send(chat_id, full, caption_prefix='💾'):
    if _BKP_BUSY['on']: bot.send_message(chat_id, "⏳ Another backup/restore is already running."); return
    _BKP_BUSY['on'] = True
    try:
        path, mf = _bkp_make(full); size = os.path.getsize(path)
        cap = f"{caption_prefix} <b>{'Full' if full else 'Data-only'} backup</b>\n👥 {mf['users']} users · 📁 {mf['projects']} projects · {_mb(size)}"
        if size <= _BKP_CHUNK:
            with open(path, 'rb') as f: bot.send_document(chat_id, f, caption=cap, parse_mode='HTML')
        else:
            n = 0; base = os.path.basename(path)
            with open(path, 'rb') as f:
                while True:
                    chunk = f.read(_BKP_CHUNK)
                    if not chunk: break
                    n += 1; pp = os.path.join(tempfile.gettempdir(), f"{base}.{n:03d}")
                    with open(pp, 'wb') as o: o.write(chunk)
                    with open(pp, 'rb') as o: bot.send_document(chat_id, o, caption=(cap + f"\n📦 Part {n}") if n == 1 else f"📦 Part {n}", parse_mode='HTML')
                    os.remove(pp)
            bot.send_message(chat_id, f"✅ Sent in <b>{n}</b> parts. To restore, send ALL parts (in order) to Import, then /done.", parse_mode='HTML')
        os.remove(path)
    except Exception as e:
        logger.warning(f"backup failed: {e}")
        try: bot.send_message(chat_id, f"❌ Backup failed: {_hmx.escape(str(e)[:300])}")
        except Exception: pass
    finally: _BKP_BUSY['on'] = False

def _bkp_safe_extract(z, prefix, dest):
    n = 0; dest_abs = os.path.abspath(dest)
    for info in z.infolist():
        if not info.filename.startswith(prefix) or info.is_dir(): continue
        rel = info.filename[len(prefix):]
        target = os.path.abspath(os.path.join(dest, rel))
        if not target.startswith(dest_abs + os.sep): continue          # zip-slip guard
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with z.open(info) as s, open(target, 'wb') as o: shutil.copyfileobj(s, o)
        n += 1
    return n

def _bkp_validate(path):
    if not zipfile.is_zipfile(path): raise ValueError("not a valid zip file (if it was sent in parts, send every part)")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if 'manifest.json' not in names or 'bot_data.db' not in names: raise ValueError("this is not a FENIX backup (manifest/database missing)")
        mf = json.loads(z.read('manifest.json'))
        if mf.get('app') != 'fenix-hosting-bot': raise ValueError("this backup belongs to a different app")
        probe = os.path.join(tempfile.gettempdir(), f"probe_{int(time.time())}.db")
        with z.open('bot_data.db') as s, open(probe, 'wb') as o: shutil.copyfileobj(s, o)
        try:
            c = sqlite3.connect(probe); c.execute("SELECT COUNT(*) FROM active_users").fetchone(); c.close()
        finally: os.remove(probe)
    return mf

def _bkp_apply(path, with_files, chat_id):
    _BKP_BUSY['on'] = True
    try:
        # 1) safety copy of the current database
        safety = os.path.join(IROTECH_DIR, f"pre_import_{datetime.now():%Y%m%d_%H%M%S}.db")
        with DB_LOCK:
            s = sqlite3.connect(DATABASE_PATH); d = sqlite3.connect(safety); s.backup(d); d.close(); s.close()
        # 2) stop every running bot
        for k, i in list(bot_scripts.items()):
            try: kill_process_tree(i)
            except Exception: pass
            bot_scripts.pop(k, None)
        # 3) replace the database content
        tmpdb = os.path.join(tempfile.gettempdir(), f"restore_{int(time.time())}.db")
        with zipfile.ZipFile(path) as z:
            with z.open('bot_data.db') as s, open(tmpdb, 'wb') as o: shutil.copyfileobj(s, o)
            with DB_LOCK:
                src = sqlite3.connect(tmpdb); dst = sqlite3.connect(DATABASE_PATH); src.backup(dst); dst.close(); src.close()
            os.remove(tmpdb)
            # 4) project files
            n = 0
            if with_files and any(x.startswith('upload_bots/') for x in z.namelist()):
                if os.path.isdir(UPLOAD_BOTS_DIR): shutil.rmtree(UPLOAD_BOTS_DIR, ignore_errors=True)
                os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
                n = _bkp_safe_extract(z, 'upload_bots/', UPLOAD_BOTS_DIR)
        # 5) make sure all tables/columns exist, then reload memory
        init_db(); _lb_init(); _rc_init(); _ap_init()
        for dct in (user_files, user_subscriptions, user_limits): dct.clear()
        banned_users.clear(); active_users.clear(); load_data()
        try: _bk_clear()
        except Exception: pass
        bot.send_message(chat_id, f"✅ <b>Import complete</b>\n👥 {len(active_users)} users · 📁 {sum(len(v) for v in user_files.values())} projects · 🗂 {n} files restored\n"
                                  f"🛟 Your previous database was saved as <code>{os.path.basename(safety)}</code> on the server.\n▶️ Bots were stopped — use <b>Run All Scripts</b> to start them.", parse_mode='HTML')
    except Exception as e:
        logger.error(f"import failed: {e}", exc_info=True)
        try: bot.send_message(chat_id, f"❌ Import failed: {_hmx.escape(str(e)[:300])}\nYour previous data is safe in the pre_import backup on the server.")
        except Exception: pass
    finally:
        _BKP_BUSY['on'] = False
        try: os.remove(path)
        except Exception: pass

def _bkp_home():
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
    m.add(B('📤 Export — Data Only (users, plans, settings…)', callback_data='bkp_exp_data'),
          B('📦 Export — FULL (data + all project files)', callback_data='bkp_exp_full'),
          B('📥 Import a Backup', callback_data='bkp_imp'),
          B(('✅' if _lbf('BKP_AUTO') else '❌') + ' Auto-Backup to Owner', callback_data='bkp_auto'),
          B(f"⏱ Auto-Backup Every: {_lbi('BKP_AUTO_HOURS')}h", callback_data='bkp_hrs'),
          B(('📦 Auto type: FULL' if _lbf('BKP_AUTO_FULL') else '📤 Auto type: Data only'), callback_data='bkp_autotype'),
          B('🔙 Back to Admin Panel', callback_data='admin_panel'))
    txt = ("💾 <b>Backup & Restore</b>\n━━━━━━━━━━━━━━━━━━\n"
           "📤 <b>Data only</b> — database: users, plans, payments, points, settings, messages, colors.\n"
           "📦 <b>Full</b> — data + every user's project files (node_modules / logs are skipped).\n"
           "📥 <b>Import</b> — send the backup .zip (or all its parts) to restore everything on this or a new server.\n\n"
           "<i>Large backups are split into 18 MB parts because Telegram bots can only download 20 MB files.</i>")
    return txt, m

def backup_callback(call):
    d = call.data; chat = call.message.chat.id; uid = call.from_user.id
    try: bot.answer_callback_query(call.id)
    except Exception: pass
    if d == 'bkp_home': t, m = _bkp_home(); return _rp_edit(call, t, m)
    if d in ('bkp_exp_data', 'bkp_exp_full'):
        bot.send_message(chat, "⏳ Building backup… this can take a minute.")
        threading.Thread(target=_bkp_send, args=(chat, d == 'bkp_exp_full'), daemon=True).start(); return
    if d == 'bkp_auto': set_setting('BKP_AUTO', '0' if _lbf('BKP_AUTO') else '1'); t, m = _bkp_home(); return _rp_edit(call, t, m)
    if d == 'bkp_autotype': set_setting('BKP_AUTO_FULL', '0' if _lbf('BKP_AUTO_FULL') else '1'); t, m = _bkp_home(); return _rp_edit(call, t, m)
    if d == 'bkp_hrs':
        msg = bot.send_message(chat, "⏱ Send how many hours between automatic backups (1–168). /cancel to abort.")
        def h(mm):
            if not mm.text or mm.from_user.id not in admin_ids: return
            try: v = int(mm.text.strip()); assert 1 <= v <= 168
            except Exception: return bot.send_message(mm.chat.id, "❌ Send a number from 1 to 168.")
            set_setting('BKP_AUTO_HOURS', str(v)); bot.send_message(mm.chat.id, f"✅ Auto-backup every {v}h.")
        return bot.register_next_step_handler(msg, h)
    if d == 'bkp_imp':
        state = {'parts': []}
        msg = bot.send_message(chat, "📥 <b>Import</b>\nSend the backup file now (.zip, or every <code>.zip.001 / .002 …</code> part).\nWhen all parts are sent, send /done. Send /cancel to abort.", parse_mode='HTML')
        def h(mm):
            if mm.from_user.id not in admin_ids: return
            if mm.text and mm.text.strip().lower() == '/cancel':
                for p in state['parts']: os.path.exists(p) and os.remove(p)
                return bot.send_message(mm.chat.id, "Cancelled.")
            if mm.text and mm.text.strip().lower() == '/done':
                return _bkp_finish(mm, state)
            if mm.document:
                try:
                    fi = bot.get_file(mm.document.file_id); data = bot.download_file(fi.file_path)
                    p = os.path.join(tempfile.gettempdir(), f"imp_{uid}_{mm.document.file_name}")
                    with open(p, 'wb') as o: o.write(data)
                    state['parts'].append(p)
                    bot.send_message(mm.chat.id, f"✅ Received <b>{_hmx.escape(mm.document.file_name or 'file')}</b> ({len(state['parts'])} so far). Send the next part, or /done.", parse_mode='HTML')
                except Exception as e: bot.send_message(mm.chat.id, f"❌ Could not download: {_hmx.escape(str(e)[:200])}")
            else: bot.send_message(mm.chat.id, "Send the backup file, /done or /cancel.")
            bot.register_next_step_handler(mm, h)
        return bot.register_next_step_handler(msg, h)
    if d in ('bkp_go_all', 'bkp_go_db'):
        p = _BKP_PENDING.pop(uid, None)
        if not p or not os.path.exists(p['zip']): return bot.send_message(chat, "❌ Nothing pending — start Import again.")
        if _BKP_BUSY['on']: return bot.send_message(chat, "⏳ Another backup/restore is running.")
        bot.send_message(chat, "⏳ Restoring… please wait.")
        threading.Thread(target=_bkp_apply, args=(p['zip'], d == 'bkp_go_all', chat), daemon=True).start(); return
    if d == 'bkp_no':
        p = _BKP_PENDING.pop(uid, None)
        if p:
            try: os.remove(p['zip'])
            except Exception: pass
        return bot.send_message(chat, "Cancelled — nothing was changed.")

def _bkp_finish(mm, state):
    parts = sorted(state['parts'])
    if not parts: return bot.send_message(mm.chat.id, "❌ No file received.")
    try:
        if len(parts) == 1: joined = parts[0]
        else:
            joined = os.path.join(tempfile.gettempdir(), f"joined_{int(time.time())}.zip")
            with open(joined, 'wb') as o:
                for p in parts:
                    with open(p, 'rb') as f: shutil.copyfileobj(f, o)
            for p in parts: os.remove(p)
        mf = _bkp_validate(joined)
    except Exception as e:
        for p in parts + [locals().get('joined')]:
            try: p and os.path.exists(p) and os.remove(p)
            except Exception: pass
        return bot.send_message(mm.chat.id, f"❌ Invalid backup: {_hmx.escape(str(e)[:250])}")
    _BKP_PENDING[mm.from_user.id] = {'zip': joined}
    B = types.InlineKeyboardButton; k = types.InlineKeyboardMarkup(row_width=1)
    if mf.get('full'): k.add(B('♻️ Restore EVERYTHING (data + project files)', callback_data='bkp_go_all'))
    k.add(B('🗄 Restore DATA ONLY (keep current project files)', callback_data='bkp_go_db'), B('❌ Cancel', callback_data='bkp_no'))
    bot.send_message(mm.chat.id, f"✅ <b>Valid backup</b>\n📅 {str(mf.get('created'))[:16]}\n👥 {mf.get('users')} users · 📁 {mf.get('projects')} projects · {'📦 Full' if mf.get('full') else '📤 Data only'}\n\n"
                     "⚠️ This <b>replaces all current data</b> and stops all running bots. Your current database is saved first.", parse_mode='HTML', reply_markup=k)

def _bkp_auto_loop():
    while True:
        time.sleep(300)
        try:
            if not _lbf('BKP_AUTO') or _BKP_BUSY['on']: continue
            last = float(get_setting('BKP_LAST', '0') or 0)
            if time.time() - last >= _lbi('BKP_AUTO_HOURS') * 3600:
                set_setting('BKP_LAST', str(time.time()))
                _bkp_send(OWNER_ID, _lbf('BKP_AUTO_FULL'), '🕒 Auto')
        except Exception as e: logger.warning(f"auto backup: {e}")


# ============================================================
# --- System Monitor: RAM / storage / CPU / network + 50 options ---
# ============================================================
LB_DEF.update({'SM_ALERT_ON': '0', 'SM_ALERT_RAM': '90', 'SM_ALERT_DISK': '90', 'SM_ALERT_CPU': '95', 'SM_ALERT_COOLDOWN': '30',
               'SM_SHOW_HEADER': '1', 'SM_SAMPLE_MIN': '5', 'SM_HIST_DAYS': '3', 'SM_USER_QUOTA_MB': '0', 'SM_MIN_FREE_MB': '0',
               'SM_AUTO_CLEAN': '0', 'SM_LOG_KEEP_DAYS': '7'})
AP_CATS.append(('sys', '🖥 System Monitor'))

def _sm_init():
    _db_exec("CREATE TABLE IF NOT EXISTS sm_history (ts TEXT, ram REAL, disk REAL, cpu REAL, bots INTEGER, ram_used REAL, disk_used REAL)")

def _sm_cg(path):
    try: return open(path).read().strip()
    except Exception: return None
def _sm_mem():
    """(total, used, available) — respects container (cgroup) limits when they are lower than the host's."""
    vm = psutil.virtual_memory(); total, used, avail = vm.total, vm.total - vm.available, vm.available
    lim = _sm_cg('/sys/fs/cgroup/memory.max') or _sm_cg('/sys/fs/cgroup/memory/memory.limit_in_bytes')
    cur = _sm_cg('/sys/fs/cgroup/memory.current') or _sm_cg('/sys/fs/cgroup/memory/memory.usage_in_bytes')
    try:
        if lim and lim != 'max' and cur and 0 < int(lim) < vm.total:
            total = int(lim); used = int(cur)
            st = _sm_cg('/sys/fs/cgroup/memory.stat') or ''
            for line in st.splitlines():                       # don't count reclaimable page cache as used
                if line.startswith('inactive_file '): used = max(0, used - int(line.split()[1]))
            avail = max(0, total - used)
    except Exception: pass
    return total, used, avail
def _sm_disk():
    du = shutil.disk_usage(BASE_DIR); return du.total, du.used, du.free
def _sm_pct(u, t): return (u * 100.0 / t) if t else 0.0
def _gb(b): return f"{b / 1073741824:.2f} GB" if b >= 1073741824 else f"{b / 1048576:.0f} MB"
def _sm_bar(p, n=10):
    f = int(round(max(0, min(100, p)) / 100 * n)); return '▰' * f + '▱' * (n - f)
def _sm_ico(p): return '🟢' if p < 70 else ('🟡' if p < 90 else '🔴')
def _sm_bots_ram():
    tot = 0; n = 0
    for k, i in list(bot_scripts.items()):
        try:
            if not _is_running(k): continue
            p = psutil.Process(i['process'].pid); tot += p.memory_info().rss + sum(c.memory_info().rss for c in p.children(recursive=True)); n += 1
        except Exception: pass
    return n, tot
def _sm_line():
    mt, mu, _ = _sm_mem(); dt, du, _ = _sm_disk()
    return f"🧠 RAM {_gb(mu)}/{_gb(mt)} ({_sm_pct(mu, mt):.0f}%) · 💽 Disk {_gb(du)}/{_gb(dt)} ({_sm_pct(du, dt):.0f}%)"
def _admin_panel_text():
    t = ("✦ <b>𝗔𝗗𝗠𝗜𝗡  𝗖𝗢𝗡𝗦𝗢𝗟𝗘</b> ✦\n<i>Full control of your hosting platform</i>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬")
    try:
        if _lbf('SM_SHOW_HEADER'):
            mt, mu, _a = _sm_mem(); dt, du, _f = _sm_disk(); mp, dp = _sm_pct(mu, mt), _sm_pct(du, dt)
            run = sum(1 for k in list(bot_scripts) if _is_running(k))
            t += (f"\n<blockquote>🧠 RAM  {_sm_bar(mp, 8)} <b>{mp:.0f}%</b>\n      {_gb(mu)} / {_gb(mt)}\n"
                  f"💽 Disk  {_sm_bar(dp, 8)} <b>{dp:.0f}%</b>\n      {_gb(du)} / {_gb(dt)}\n"
                  f"👥 Users <b>{len(active_users)}</b>  ·  🤖 Running <b>{run}</b></blockquote>")
    except Exception: pass
    return _MStr(t)

def _sm_dash():
    mt, mu, ma = _sm_mem(); dt, du, df = _sm_disk(); sw = psutil.swap_memory()
    cpu = psutil.cpu_percent(interval=0.3); n, br = _sm_bots_ram()
    try: la = os.getloadavg()
    except Exception: la = (0, 0, 0)
    up_b = _dir_size(UPLOAD_BOTS_DIR); db = os.path.getsize(DATABASE_PATH) if os.path.exists(DATABASE_PATH) else 0
    mp, dp = _sm_pct(mu, mt), _sm_pct(du, dt)
    t = (f"🖥 <b>SYSTEM MONITOR</b>\n━━━━━━━━━━━━━━━━━━\n"
         f"{_sm_ico(mp)} <b>RAM</b>  {_sm_bar(mp)} <b>{mp:.0f}%</b>\n   Used <b>{_gb(mu)}</b> of <b>{_gb(mt)}</b> · Free <b>{_gb(ma)}</b>\n\n"
         f"{_sm_ico(dp)} <b>STORAGE</b>  {_sm_bar(dp)} <b>{dp:.0f}%</b>\n   Used <b>{_gb(du)}</b> of <b>{_gb(dt)}</b> · Free <b>{_gb(df)}</b>\n\n"
         f"{_sm_ico(cpu)} <b>CPU</b>  {_sm_bar(cpu)} <b>{cpu:.0f}%</b>\n   {psutil.cpu_count()} core(s) · load {la[0]:.2f} / {la[1]:.2f} / {la[2]:.2f}\n")
    if sw.total: t += f"\n🔁 <b>SWAP</b>  {_sm_bar(sw.percent)} <b>{sw.percent:.0f}%</b> ({_gb(sw.used)}/{_gb(sw.total)})\n"
    t += (f"\n🤖 Running bots: <b>{n}</b> · using <b>{_gb(br)}</b> RAM\n📂 User projects: <b>{_gb(up_b)}</b> · 🗄 DB: <b>{_gb(db)}</b>\n"
          f"⏱ Server up: <b>{_format_uptime(time.time() - psutil.boot_time())}</b> · Bot up: <b>{_format_uptime(time.time() - BOT_START_TIME)}</b>\n"
          f"🕒 <i>{_now():%H:%M:%S}</i>")
    return t
def _sm_idx(label):
    for i, o in enumerate(AP_OPTS):
        if o['cat'] == 'sys' and o['label'] == label: return i
    return 0
def _sm_markup():
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=2)
    m.row(B('🔄 Refresh', callback_data='sm_home'), B('📡 Live 60s', callback_data='sm_live'))
    for a, b in (('🧠 Memory Details', '💽 Storage Details'), ('⚙️ CPU Per-Core', '🌐 Network Totals'), ('🤖 Bots Resource Usage', '🧮 Top Processes (RAM)'),
                 ('📂 Top Storage Users', '📈 RAM History 24h'), ('🧹 Quick Cleanup', '🔔 Alerts On/Off')):
        m.row(B(a, callback_data=f"ap_o_{_sm_idx(a)}"), B(b, callback_data=f"ap_o_{_sm_idx(b)}"))
    m.row(B(f"🧩 All {len(_ap_cat_idx('sys'))} System Options", callback_data='ap_c_sys_0'))
    m.row(B('🔙 Back to Admin Panel', callback_data='admin_panel')); return m

def monitor_callback(call):
    try: bot.answer_callback_query(call.id)
    except Exception: pass
    if call.data == 'sm_live':
        chat, mid = call.message.chat.id, call.message.message_id
        def live():
            for _ in range(12):
                try: bot.edit_message_text(_sm_dash(), chat, mid, parse_mode='HTML', reply_markup=_sm_markup())
                except Exception as e:
                    if 'not modified' not in str(e): break
                time.sleep(5)
        threading.Thread(target=live, daemon=True).start(); return
    _rp_edit(call, _sm_dash(), _sm_markup())

# ---------------- background sampler / alerts / auto-clean ----------------
_SM = {'last': 0, 'alert': {}, 'clean_day': ''}
def _sm_sample():
    mt, mu, _ = _sm_mem(); dt, du, _ = _sm_disk(); cpu = psutil.cpu_percent(interval=1)
    _db_exec("INSERT INTO sm_history VALUES (?,?,?,?,?,?,?)", (_now().isoformat(), _sm_pct(mu, mt), _sm_pct(du, dt), cpu, _sm_bots_ram()[0], mu, du))
    _db_exec("DELETE FROM sm_history WHERE ts < ?", (_since(max(1, _lbi('SM_HIST_DAYS'))),))
    return _sm_pct(mu, mt), _sm_pct(du, dt), cpu
def _sm_cleanup(days):
    freed = 0; n = 0
    for r, ds, fs in os.walk(UPLOAD_BOTS_DIR):
        for d in list(ds):
            if d == '__pycache__':
                freed += _dir_size(os.path.join(r, d)); shutil.rmtree(os.path.join(r, d), ignore_errors=True); ds.remove(d); n += 1
        for f in fs:
            fp = os.path.join(r, f)
            if f.endswith('.log') and time.time() - os.path.getmtime(fp) > days * 86400:
                try: sz = os.path.getsize(fp); os.remove(fp); freed += sz; n += 1
                except Exception: pass
    return n, freed
def _sm_loop():
    while True:
        time.sleep(30)
        try:
            if time.time() - _SM['last'] < max(1, _lbi('SM_SAMPLE_MIN')) * 60: continue
            _SM['last'] = time.time(); ram, disk, cpu = _sm_sample()
            if _lbf('SM_ALERT_ON'):
                for name, val, key in (('RAM', ram, 'SM_ALERT_RAM'), ('Storage', disk, 'SM_ALERT_DISK'), ('CPU', cpu, 'SM_ALERT_CPU')):
                    if val >= _lbi(key) and time.time() - _SM['alert'].get(name, 0) > _lbi('SM_ALERT_COOLDOWN') * 60:
                        _SM['alert'][name] = time.time()
                        try: bot.send_message(OWNER_ID, f"🚨 <b>{name} is at {val:.0f}%</b> (limit {_lbi(key)}%)\n{_sm_line()}", parse_mode='HTML')
                        except Exception: pass
            if _lbf('SM_AUTO_CLEAN') and _SM['clean_day'] != _today() and _now().hour == 4:
                _SM['clean_day'] = _today(); n, fr = _sm_cleanup(max(1, _lbi('SM_LOG_KEEP_DAYS')))
                logger.info(f"auto clean: {n} items, {_mb(fr)}")
        except Exception as e: logger.warning(f"sm_loop: {e}")

# ---------------- upload guards (quota / low disk) ----------------
_sm_orig_gate = _ap_upload_gate
def _ap_upload_gate(message, ext=None, size=None):
    if not _sm_orig_gate(message, ext, size): return False
    uid = message.from_user.id
    if uid in admin_ids or not ext: return True
    try:
        mf = _lbi('SM_MIN_FREE_MB')
        if mf > 0 and _sm_disk()[2] < mf * 1048576:
            bot.reply_to(message, "⚠️ The server is low on storage right now. Please try again later."); return False
        q = _lbi('SM_USER_QUOTA_MB')
        if q > 0 and _dir_size(get_user_folder(uid)) + (size or 0) > q * 1048576:
            bot.reply_to(message, f"💽 Your storage quota ({q} MB) is full. Delete a project first."); return False
    except Exception as e: logger.debug(f"quota check: {e}")
    return True

# ---------------- 🖥 System options (shown in Toolbox → System Monitor) ----------------
_OS = 'sys'
@R(_OS, '🧠 Memory Details')
def _y1():
    vm = psutil.virtual_memory(); t, u, a = _sm_mem(); pr = psutil.Process(); n, br = _sm_bots_ram()
    return (f"🧠 <b>Memory</b>\n━━━━━━━━━━━━━━━━━━\nTotal: <b>{_gb(t)}</b>\nUsed: <b>{_gb(u)}</b> ({_sm_pct(u, t):.1f}%)\nAvailable: <b>{_gb(a)}</b>\n"
            f"Host RAM: {_gb(vm.total)} (cached {_gb(getattr(vm, 'cached', 0))})\nThis bot process: <b>{_gb(pr.memory_info().rss)}</b>\nUser bots ({n}): <b>{_gb(br)}</b>")
@R(_OS, '🔁 Swap Details')
def _y2():
    s = psutil.swap_memory()
    return f"🔁 <b>Swap</b>\nTotal: {_gb(s.total)}\nUsed: {_gb(s.used)} ({s.percent}%)\nFree: {_gb(s.free)}" if s.total else "🔁 No swap configured."
@R(_OS, '💽 Storage Details')
def _y3():
    t, u, f = _sm_disk(); rows = [f"Server disk: <b>{_gb(u)}</b> / {_gb(t)} ({_sm_pct(u, t):.0f}%) · free <b>{_gb(f)}</b>"]
    for p in psutil.disk_partitions(all=False)[:6]:
        try: d = psutil.disk_usage(p.mountpoint); rows.append(f"• <code>{_hmx.escape(p.mountpoint)}</code> {_gb(d.used)}/{_gb(d.total)} ({d.percent}%)")
        except Exception: pass
    return _rows_text('💽 Storage', rows)
@R(_OS, '📦 Storage Breakdown')
def _y4():
    tmp = tempfile.gettempdir(); pre = sum(os.path.getsize(os.path.join(IROTECH_DIR, f)) for f in os.listdir(IROTECH_DIR) if f.startswith('pre_import_')) if os.path.isdir(IROTECH_DIR) else 0
    logs = pyc = 0
    for r, ds, fs in os.walk(UPLOAD_BOTS_DIR):
        if os.path.basename(r) == '__pycache__': pyc += sum(os.path.getsize(os.path.join(r, f)) for f in fs)
        logs += sum(os.path.getsize(os.path.join(r, f)) for f in fs if f.endswith('.log'))
    rows = [f"📂 User projects: <b>{_gb(_dir_size(UPLOAD_BOTS_DIR))}</b>", f"🗄 Database: <b>{_gb(os.path.getsize(DATABASE_PATH))}</b>", f"📜 Project logs: <b>{_gb(logs)}</b>",
            f"🐍 __pycache__: <b>{_gb(pyc)}</b>", f"🛟 pre-import backups: <b>{_gb(pre)}</b>", f"🗂 Whole data folder: <b>{_gb(_dir_size(IROTECH_DIR))}</b>"]
    return _rows_text('📦 Storage breakdown', rows)
@R(_OS, '📂 Top Storage Users')
def _y5():
    out = []
    for u in os.listdir(UPLOAD_BOTS_DIR) if os.path.isdir(UPLOAD_BOTS_DIR) else []:
        if u.isdigit(): out.append((_dir_size(os.path.join(UPLOAD_BOTS_DIR, u)), int(u)))
    out.sort(reverse=True)
    return _rows_text('📂 Top storage users', [f"{i}. {_u(u)} — <b>{_gb(s)}</b>" for i, (s, u) in enumerate(out[:15], 1)])
@R(_OS, '📄 Biggest Files')
def _y6():
    out = []
    for r, _d, fs in os.walk(UPLOAD_BOTS_DIR):
        for f in fs:
            try: out.append((os.path.getsize(os.path.join(r, f)), os.path.relpath(os.path.join(r, f), UPLOAD_BOTS_DIR)))
            except Exception: pass
    out.sort(reverse=True)
    return _rows_text('📄 Biggest files', [f"{i}. <code>{_hmx.escape(p[:55])}</code> — <b>{_gb(s)}</b>" for i, (s, p) in enumerate(out[:10], 1)])
@R(_OS, '🗃 Storage by File Type')
def _y7():
    agg = {}
    for r, _d, fs in os.walk(UPLOAD_BOTS_DIR):
        for f in fs:
            e = os.path.splitext(f)[1].lower() or 'none'
            try: agg[e] = agg.get(e, 0) + os.path.getsize(os.path.join(r, f))
            except Exception: pass
    return _rows_text('🗃 By file type', [f"• {e}: <b>{_gb(s)}</b>" for e, s in sorted(agg.items(), key=lambda x: -x[1])[:12]])
@R(_OS, '📜 Largest Logs')
def _y8():
    out = []
    for r, _d, fs in os.walk(UPLOAD_BOTS_DIR):
        for f in fs:
            if f.endswith('.log'):
                try: out.append((os.path.getsize(os.path.join(r, f)), os.path.relpath(os.path.join(r, f), UPLOAD_BOTS_DIR)))
                except Exception: pass
    out.sort(reverse=True)
    return _rows_text('📜 Largest logs', [f"{i}. <code>{_hmx.escape(p[:55])}</code> — <b>{_gb(s)}</b>" for i, (s, p) in enumerate(out[:10], 1)])
@R(_OS, '🕸 Stale Projects (30d)')
def _y9():
    rows = []
    for u, v in list(user_files.items()):
        for pn, _m, _t in v:
            try:
                fp = get_user_folder(u, pn); mt = max([os.path.getmtime(os.path.join(r, f)) for r, _d, fs in os.walk(fp) for f in fs] or [0])
                if mt and time.time() - mt > 30 * 86400 and not is_bot_running(u, pn): rows.append(f"• {_hmx.escape(str(pn))} · {_u(u)} · {_gb(_dir_size(fp))}")
            except Exception: pass
    return _rows_text('🕸 Not touched in 30 days', rows[:25])
@R(_OS, '🔢 Inode Usage')
def _y10():
    s = os.statvfs(BASE_DIR); tot, free = s.f_files, s.f_ffree
    return f"🔢 <b>Inodes</b>\nTotal: {tot}\nUsed: {tot - free} ({_sm_pct(tot - free, tot):.1f}%)\nFree: {free}" if tot else "🔢 Not reported by this filesystem."
@R(_OS, '⚙️ CPU Per-Core')
def _y11():
    pc = psutil.cpu_percent(interval=0.5, percpu=True)
    return _rows_text(f"⚙️ CPU · total {sum(pc) / len(pc):.0f}%", [f"Core {i}: {_sm_bar(p, 8)} <b>{p:.0f}%</b>" for i, p in enumerate(pc)])
@R(_OS, '📊 CPU Freq & Load')
def _y12():
    f = psutil.cpu_freq(); la = os.getloadavg() if hasattr(os, 'getloadavg') else (0, 0, 0)
    return f"📊 <b>CPU</b>\nCores: {psutil.cpu_count()} ({psutil.cpu_count(logical=False) or '?'} physical)\nFrequency: {f'{f.current:.0f} MHz' if f else 'n/a'}\nLoad avg: {la[0]:.2f} / {la[1]:.2f} / {la[2]:.2f}"
@R(_OS, '🌐 Network Totals')
def _y13():
    n = psutil.net_io_counters(); return f"🌐 <b>Network (since boot)</b>\n⬆️ Sent: <b>{_gb(n.bytes_sent)}</b> ({n.packets_sent} pkts)\n⬇️ Received: <b>{_gb(n.bytes_recv)}</b> ({n.packets_recv} pkts)\nErrors in/out: {n.errin}/{n.errout}"
@R(_OS, '⚡ Network Speed')
def _y14():
    a = psutil.net_io_counters(); time.sleep(1); b = psutil.net_io_counters()
    return f"⚡ <b>Live speed</b>\n⬆️ {(b.bytes_sent - a.bytes_sent) / 1024:.1f} KB/s\n⬇️ {(b.bytes_recv - a.bytes_recv) / 1024:.1f} KB/s"
@R(_OS, '🔌 Connections')
def _y15():
    try: c = psutil.net_connections(kind='inet')
    except Exception as e: return f"🔌 Not permitted on this host ({_hmx.escape(str(e)[:80])})."
    st = {}
    for x in c: st[x.status] = st.get(x.status, 0) + 1
    return _rows_text(f"🔌 Connections ({len(c)})", [f"• {k}: <b>{v}</b>" for k, v in sorted(st.items(), key=lambda x: -x[1])])
@R(_OS, '🤖 Bots Resource Usage')
def _y16():
    out = []
    for k, i in list(bot_scripts.items()):
        try:
            p = psutil.Process(i['process'].pid); rss = p.memory_info().rss + sum(c.memory_info().rss for c in p.children(recursive=True)); out.append((rss, p.cpu_percent(interval=0.05), i))
        except Exception: pass
    out.sort(key=lambda x: -x[0])
    return _rows_text(f"🤖 Running bots ({len(out)})", [f"{n}. {_hmx.escape(str(i.get('project_name')))} · {_u(i.get('script_owner_id'))} — {_gb(r)} · {c:.0f}% CPU" for n, (r, c, i) in enumerate(out[:20], 1)])
@R(_OS, '🧮 Top Processes (RAM)')
def _y17():
    ps = []
    for p in psutil.process_iter(['pid', 'name', 'memory_info']):
        try: ps.append((p.info['memory_info'].rss, p.info['pid'], p.info['name']))
        except Exception: pass
    ps.sort(reverse=True)
    return _rows_text('🧮 Top processes by RAM', [f"{i}. <code>{pid}</code> {_hmx.escape(str(nm))} — <b>{_gb(r)}</b>" for i, (r, pid, nm) in enumerate(ps[:10], 1)])
@R(_OS, '🔥 Top Processes (CPU)')
def _y18():
    ps = list(psutil.process_iter(['pid', 'name']))
    for p in ps:
        try: p.cpu_percent(None)
        except Exception: pass
    time.sleep(0.5); out = []
    for p in ps:
        try: out.append((p.cpu_percent(None), p.info['pid'], p.info['name']))
        except Exception: pass
    out.sort(reverse=True)
    return _rows_text('🔥 Top processes by CPU', [f"{i}. <code>{pid}</code> {_hmx.escape(str(nm))} — <b>{c:.0f}%</b>" for i, (c, pid, nm) in enumerate(out[:10], 1)])
@R(_OS, '🧵 Process Counts')
def _y19():
    st = {}
    for p in psutil.process_iter(['status']):
        try: st[p.info['status']] = st.get(p.info['status'], 0) + 1
        except Exception: pass
    return _rows_text(f"🧵 Processes ({sum(st.values())})", [f"• {k}: <b>{v}</b>" for k, v in st.items()])
@R(_OS, '🌡 Temps & Battery')
def _y20():
    rows = []
    try:
        for n, es in (psutil.sensors_temperatures() or {}).items():
            for e in es[:2]: rows.append(f"• {n}: <b>{e.current:.0f}°C</b>")
    except Exception: pass
    try:
        b = psutil.sensors_battery()
        if b: rows.append(f"🔋 Battery {b.percent:.0f}% {'(charging)' if b.power_plugged else ''}")
    except Exception: pass
    return _rows_text('🌡 Sensors', rows, "<i>No sensors available on this host.</i>")
@R(_OS, '⏱ Uptime & Boot')
def _y21():
    b = psutil.boot_time(); return f"⏱ <b>Uptime</b>\nServer booted: {datetime.fromtimestamp(b):%d %b %Y %H:%M}\nServer up: <b>{_format_uptime(time.time() - b)}</b>\nBot up: <b>{_format_uptime(time.time() - BOT_START_TIME)}</b>"
@R(_OS, '🐍 Bot Process Info')
def _y22():
    p = psutil.Process(); return (f"🐍 <b>Bot process</b>\nPID: {p.pid}\nRAM: <b>{_gb(p.memory_info().rss)}</b>\nCPU: {p.cpu_percent(interval=0.2):.0f}%\nThreads: {p.num_threads()}\n"
                                 f"Open files: {len(p.open_files())}\nChildren: {len(p.children())}\nStarted: {datetime.fromtimestamp(p.create_time()):%d %b %H:%M}")
@R(_OS, '📁 File Descriptors')
def _y23():
    try:
        import resource; soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE); n = psutil.Process().num_fds()
        return f"📁 <b>File descriptors</b>\nOpen: {n}\nSoft limit: {soft}\nHard limit: {hard}"
    except Exception as e: return f"📁 Not available: {_hmx.escape(str(e)[:80])}"
@R(_OS, '💿 Disk I/O')
def _y24():
    d = psutil.disk_io_counters()
    return f"💿 <b>Disk I/O (since boot)</b>\n📖 Read: <b>{_gb(d.read_bytes)}</b> ({d.read_count} ops)\n✍️ Written: <b>{_gb(d.write_bytes)}</b> ({d.write_count} ops)" if d else "💿 Not reported by this host."
@R(_OS, '🖥 Server Info')
def _y25():
    import platform, socket
    return (f"🖥 <b>Server</b>\nHost: <code>{_hmx.escape(socket.gethostname())}</code>\nOS: {platform.system()} {platform.release()}\nArch: {platform.machine()}\n"
            f"Python: {platform.python_version()}\nCPU: {psutil.cpu_count()} cores\nRAM: {_gb(psutil.virtual_memory().total)} host")
@R(_OS, '📦 Container Limits')
def _y26():
    lim = _sm_cg('/sys/fs/cgroup/memory.max') or _sm_cg('/sys/fs/cgroup/memory/memory.limit_in_bytes'); cpu = _sm_cg('/sys/fs/cgroup/cpu.max')
    try: ml = _gb(int(lim)) if lim and lim != 'max' and int(lim) < 1 << 50 else 'none (host RAM)'
    except Exception: ml = 'unknown'
    return f"📦 <b>Container limits</b>\nMemory limit: <b>{ml}</b>\nCPU quota: <b>{cpu or 'none'}</b>"
def _sm_hist(col, title, hrs=24):
    rows = _db_q(f"SELECT ts, {col} FROM sm_history WHERE ts >= ? ORDER BY ts", (_iso_ago(hours=hrs),))
    if not rows: return "📈 No samples yet — the monitor records one every few minutes."
    vals = [r[1] for r in rows]; n = 24; step = max(1, len(vals) // n); pts = [max(vals[i:i + step]) for i in range(0, len(vals), step)][-n:]
    spark = ''.join('▁▂▃▄▅▆▇█'[min(7, int(v / 100 * 8))] for v in pts)
    return f"📈 <b>{title} · last {hrs}h</b>\n<code>{spark}</code>\nNow: <b>{vals[-1]:.0f}%</b> · Avg: <b>{sum(vals) / len(vals):.0f}%</b> · Peak: <b>{max(vals):.0f}%</b> · Low: <b>{min(vals):.0f}%</b>\nSamples: {len(vals)}"
@R(_OS, '📈 RAM History 24h')
def _y27(): return _sm_hist('ram', 'RAM')
@R(_OS, '📈 Storage History 24h')
def _y28(): return _sm_hist('disk', 'Storage')
@R(_OS, '📈 CPU History 24h')
def _y29(): return _sm_hist('cpu', 'CPU')
@R(_OS, '🏔 Peak Usage 24h')
def _y30():
    r = _db_q("SELECT MAX(ram), MAX(cpu), MAX(disk), MAX(bots), COUNT(*) FROM sm_history WHERE ts >= ?", (_iso_ago(hours=24),), one=True)
    return f"🏔 <b>Peaks (24h)</b>\n🧠 RAM {r[0] or 0:.0f}%\n⚙️ CPU {r[1] or 0:.0f}%\n💽 Storage {r[2] or 0:.0f}%\n🤖 Most bots running: {r[3] or 0}\n<i>{r[4]} samples</i>"
@R(_OS, '🔮 Disk-Full Forecast')
def _y31():
    r = _db_q("SELECT ts, disk_used FROM sm_history ORDER BY ts", ())
    if len(r) < 3: return "🔮 Not enough history yet (needs a few samples)."
    d0, d1 = datetime.fromisoformat(r[0][0]), datetime.fromisoformat(r[-1][0]); days = max((d1 - d0).total_seconds() / 86400, 1e-6); grow = (r[-1][1] - r[0][1]) / days
    free = _sm_disk()[2]
    return (f"🔮 Storage grows ≈ <b>{_gb(max(grow, 0))}/day</b>\n" + (f"⏳ Full in ≈ <b>{free / grow:.0f} days</b>" if grow > 0 else "✅ Not growing."))
@A(_OS, '📸 Take Sample Now')
def _y32(call): p = _sm_sample(); return f"📸 Recorded: RAM {p[0]:.0f}% · Disk {p[1]:.0f}% · CPU {p[2]:.0f}%"
@C(_OS, '🗑 Clear Monitor History', 'Deletes all recorded RAM/disk/CPU samples.')
def _y33(call): rc, _ = _db_exec("DELETE FROM sm_history"); return f"🗑 Removed <b>{rc}</b> sample(s)."
@A(_OS, '🧹 Quick Cleanup')
def _y34(call):
    n, fr = _sm_cleanup(max(1, _lbi('SM_LOG_KEEP_DAYS'))); tmpn = 0
    for f in os.listdir(tempfile.gettempdir()):
        if f.startswith(('fenix_backup_', 'fenixbkp_', 'imp_', 'sales_', 'backup_', 'settings_', 'joined_', 'probe_', 'restore_')):
            fp = os.path.join(tempfile.gettempdir(), f)
            try:
                if time.time() - os.path.getmtime(fp) > 3600: fr += _dir_size(fp) if os.path.isdir(fp) else os.path.getsize(fp); shutil.rmtree(fp) if os.path.isdir(fp) else os.remove(fp); tmpn += 1
            except Exception: pass
    return f"🧹 Cleaned <b>{n + tmpn}</b> item(s) · freed <b>{_gb(fr)}</b>\n{_sm_line()}"
@C(_OS, '🛟 Delete pre-import Backups', 'Deletes the pre_import_*.db safety copies on the server.')
def _y35(call):
    n = fr = 0
    for f in os.listdir(IROTECH_DIR):
        if f.startswith('pre_import_'):
            fp = os.path.join(IROTECH_DIR, f); fr += os.path.getsize(fp); os.remove(fp); n += 1
    return f"🛟 Deleted <b>{n}</b> file(s) · freed <b>{_gb(fr)}</b>."
@C(_OS, '📜 Delete ALL Logs', 'Deletes every project .log file (running bots keep logging to new files).')
def _y36(call):
    n = fr = 0
    for r, _d, fs in os.walk(UPLOAD_BOTS_DIR):
        for f in fs:
            if f.endswith('.log'):
                fp = os.path.join(r, f)
                try: fr += os.path.getsize(fp); os.remove(fp); n += 1
                except Exception: pass
    return f"📜 Deleted <b>{n}</b> log(s) · freed <b>{_gb(fr)}</b>."
@A(_OS, '♻️ Free Memory (GC)')
def _y37(call):
    import gc; b = psutil.Process().memory_info().rss; c = gc.collect(); a = psutil.Process().memory_info().rss
    return f"♻️ Collected <b>{c}</b> objects · bot RAM {_gb(b)} → {_gb(a)}"
@C(_OS, '💥 Stop Biggest RAM Bot', 'Stops the single running user bot that uses the most memory.')
def _y38(call):
    best = None
    for k, i in list(bot_scripts.items()):
        try:
            if i.get('script_owner_id') in admin_ids: continue
            p = psutil.Process(i['process'].pid); r = p.memory_info().rss + sum(c.memory_info().rss for c in p.children(recursive=True))
            if best is None or r > best[0]: best = (r, k, i)
        except Exception: pass
    if not best: return "No user bots are running."
    kill_process_tree(best[2]); bot_scripts.pop(best[1], None)
    try: bot.send_message(best[2]['script_owner_id'], f"⏹️ Your project <b>{_hmx.escape(str(best[2].get('project_name')))}</b> was stopped by an admin (high memory use).", parse_mode='HTML')
    except Exception: pass
    return f"💥 Stopped {_hmx.escape(str(best[2].get('project_name')))} ({_gb(best[0])})."
@Q(_OS, '🛑 Stop Bots Over N MB', "Send a number in MB. Every user bot using more RAM than this is stopped.")
def _y39(m, t):
    lim = int(t.strip()) * 1048576; n = 0
    for k, i in list(bot_scripts.items()):
        try:
            if i.get('script_owner_id') in admin_ids: continue
            p = psutil.Process(i['process'].pid)
            if p.memory_info().rss + sum(c.memory_info().rss for c in p.children(recursive=True)) > lim: kill_process_tree(i); bot_scripts.pop(k, None); n += 1
        except Exception: pass
    return f"🛑 Stopped <b>{n}</b> bot(s) over {t.strip()} MB."
@C(_OS, '🔁 Restart Bot Process', 'Restarts the whole hosting bot process (all running user bots stop). On Render it comes back automatically.')
def _y40(call):
    def go():
        time.sleep(2)
        try: os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception: os._exit(0)
    threading.Thread(target=go, daemon=True).start(); return "🔁 Restarting in 2 seconds…"
@A(_OS, '📤 Send Report File')
def _y41(call):
    txt = re.sub(r'<[^>]+>', '', "\n\n".join(f() for f in (_y1, _y3, _y4, _y11, _y13, _y16, _y21, _y25)))
    p = os.path.join(tempfile.gettempdir(), f"system_report_{int(time.time())}.txt")
    open(p, 'w', encoding='utf-8').write(_hmx.unescape(txt))
    with open(p, 'rb') as f: bot.send_document(call.message.chat.id, f, caption="🖥 System report")
    os.remove(p); return "✅ Report sent."
TOG(_OS, 'Show RAM/Disk in Admin Panel', 'SM_SHOW_HEADER')
TOG(_OS, '🔔 Alerts On/Off', 'SM_ALERT_ON')
NUM(_OS, 'Alert: RAM %', 'SM_ALERT_RAM', 1, 100, '%')
NUM(_OS, 'Alert: Storage %', 'SM_ALERT_DISK', 1, 100, '%')
NUM(_OS, 'Alert: CPU %', 'SM_ALERT_CPU', 1, 100, '%')
NUM(_OS, 'Alert Cooldown', 'SM_ALERT_COOLDOWN', 1, 1440, ' min')
NUM(_OS, 'Sample Every', 'SM_SAMPLE_MIN', 1, 60, ' min')
NUM(_OS, 'Keep History', 'SM_HIST_DAYS', 1, 30, ' d')
NUM(_OS, 'User Storage Quota', 'SM_USER_QUOTA_MB', 0, 100000, ' MB')
NUM(_OS, 'Block Uploads if Free <', 'SM_MIN_FREE_MB', 0, 100000, ' MB')
TOG(_OS, 'Daily Auto-Clean (4 AM)', 'SM_AUTO_CLEAN')
NUM(_OS, 'Keep Logs For', 'SM_LOG_KEEP_DAYS', 1, 365, ' d')


# ============================================================
# --- Admin Roles & Permissions: owner chooses what each admin can access ---
# ============================================================
AR_PERMS = [('users', '👥 Users & Bans'), ('subs', '💳 Subscriptions'), ('plans', '📦 Plans'), ('payments', '💰 Payments & Stars'),
            ('pending', '📋 Pending & Approval'), ('broadcast', '📢 Broadcast'), ('lock', '🔒 Lock / Run All'), ('channels', '📡 Force-Join'),
            ('tools', '🧰 Admin Tools'), ('toolbox', '🧩 Admin Toolbox'), ('monitor', '🖥 System Monitor'), ('customize', '🎛 Customize Buttons'),
            ('messages', '✏️ Edit Messages'), ('colors', '🎨 Button Colors'), ('leaderboard', '🏆 Leaderboard'), ('points', '🔗 Refer & Points'),
            ('redeem', '🎟 Redeem Codes')]
AR_KEYS = [k for k, _ in AR_PERMS]
AR_PRESETS = {'Support': ['users', 'pending'],
              'Manager': ['users', 'pending', 'subs', 'plans', 'payments', 'broadcast', 'lock', 'channels', 'redeem', 'points', 'leaderboard'],
              'Full': list(AR_KEYS)}
LB_DEF.update({'AR_DEFAULT': 'users,pending', 'AR_DEF_TITLE': 'Admin'})

def _ar_init():
    _db_exec("CREATE TABLE IF NOT EXISTS admin_perms (user_id INTEGER PRIMARY KEY, perms TEXT, title TEXT)")

def _ar_title_clean(t): return (re.sub(r'[^A-Za-z0-9 _\-]', '', str(t or '')).strip()[:16]) or 'Admin'
def _ar_default():
    perms = [p for p in str(get_setting('AR_DEFAULT', LB_DEF['AR_DEFAULT']) or '').split(',') if p in AR_KEYS]
    return perms, _ar_title_clean(get_setting('AR_DEF_TITLE', 'Admin'))
def _ar_get(uid):
    """(set of permission keys, title) for an admin. Owner = everything. Admins with no saved row (added before this feature) keep full access."""
    if uid == OWNER_ID: return set(AR_KEYS), 'Owner'
    r = _db_q("SELECT perms, title FROM admin_perms WHERE user_id=?", (uid,), one=True)
    if not r: return set(AR_KEYS), 'Admin'
    return {p for p in (r[0] or '').split(',') if p in AR_KEYS}, _ar_title_clean(r[1])
def _ar_set(uid, perms=None, title=None):
    cur_p, cur_t = _ar_get(uid)
    perms = cur_p if perms is None else set(perms); title = cur_t if title is None else _ar_title_clean(title)
    _db_exec("INSERT OR REPLACE INTO admin_perms (user_id, perms, title) VALUES (?,?,?)", (uid, ','.join(k for k in AR_KEYS if k in perms), title))
def _can(uid, perm):
    if uid == OWNER_ID: return True
    if uid not in admin_ids: return False
    return perm in _ar_get(uid)[0]
def _adm_rank(uid):
    if uid == OWNER_ID: return "👑 Owner"
    return "🛡️ " + _ar_get(uid)[1]

_AR_EXACT = {'subscription': 'subs', 'add_subscription': 'subs', 'remove_subscription': 'subs', 'check_subscription': 'subs',
             'broadcast': 'broadcast', 'cancel_broadcast': 'broadcast',
             'user_management': 'users', 'ban_user': 'users', 'unban_user': 'users', 'user_info': 'users', 'all_users': 'users', 'set_user_limit': 'users',
             'remove_user_limit': 'users', 'view_user_files': 'users',
             'pending_files': 'pending', 'lock_bot': 'lock', 'unlock_bot': 'lock', 'run_all_scripts': 'lock',
             'channel_add': 'channels', 'set_force_join': 'channels', 'add_plan_init': 'plans', 'manage_plans': 'plans',
             'admin_pay_methods': 'payments', 'add_pay_method': 'payments', 'admin_pay_settings': 'payments', 'cd_stars': 'payments',
             'add_admin': '__owner__', 'remove_admin': '__owner__', 'ar_home': '__owner__'}
_AR_PREFIX = [('confirm_broadcast_', 'broadcast'), ('users_page_', 'users'), ('chat_user_', 'users'), ('admin_user_files_', 'users'), ('ud_', 'users'),
              ('pending_user_', 'pending'), ('approve_file_', 'pending'), ('reject_file_', 'pending'), ('approve_zip_', 'pending'), ('reject_zip_', 'pending'), ('ua_', 'pending'),
              ('remove_force_join_', 'channels'), ('del_plan_', 'plans'), ('del_pay_', 'payments'), ('pps_', 'payments'), ('ppt_', 'payments'),
              ('approve_pay_', 'payments'), ('reject_pay_', 'payments'), ('adm_', 'tools'), ('adt_', 'tools'), ('ap_', 'toolbox'), ('sm_', 'monitor'),
              ('bc_', 'customize'), ('mx_', 'messages'), ('bk_', 'colors'), ('lb_a_', 'leaderboard'), ('rp_a_', 'points'), ('cd_', 'redeem'),
              ('bkp_', '__owner__'), ('ar_', '__owner__')]
def _perm_of(data):
    data = str(data or '')
    if data == 'ar_me': return None
    if data in _AR_EXACT: return _AR_EXACT[data]
    for pre, perm in _AR_PREFIX:
        if data.startswith(pre): return perm
    return None
def _ar_allowed(uid, data):
    perm = _perm_of(data)
    if perm is None or uid == OWNER_ID: return True
    if perm == '__owner__': return False
    return perm in _ar_get(uid)[0]

def _adm_gate(call):
    """False (after telling the admin) when a restricted admin taps something they were not given."""
    try:
        uid = call.from_user.id
        if uid in admin_ids and uid != OWNER_ID and not _ar_allowed(uid, call.data):
            bot.answer_callback_query(call.id, "🔒 You don't have permission for this option. Ask the owner to grant access.", show_alert=True)
            return False
    except Exception as e: logger.warning(f"adm gate: {e}")
    return True

def _adm_filter_markup(markup, uid):
    """Hide admin-panel buttons the admin may not use."""
    try:
        rows = []
        for row in markup.keyboard:
            keep = [b for b in row if getattr(b, 'callback_data', None) is None or _ar_allowed(uid, b.callback_data)]
            if keep: rows.append(keep)
        new = types.InlineKeyboardMarkup(row_width=getattr(markup, 'row_width', 2))
        for r in rows: new.row(*r)
        return new
    except Exception: return markup

# ---- hooks: new admin gets default permissions; removal clears them ----
_ar_orig_add = add_admin_db
def add_admin_db(admin_id):
    new = admin_id not in admin_ids and admin_id != OWNER_ID
    r = _ar_orig_add(admin_id)
    if new:
        perms, title = _ar_default(); _ar_set(admin_id, perms, title)
        try:
            B = types.InlineKeyboardButton; mk = types.InlineKeyboardMarkup(); mk.add(B('🛡 Choose what this admin can access', callback_data=f'ar_u_{admin_id}'))
            bot.send_message(OWNER_ID, f"🛡 <b>New admin added</b>\n<code>{admin_id}</code> is now <b>{_hmx.escape(title)}</b> with <b>{len(perms)}</b> of {len(AR_KEYS)} permissions.\nTap below to change their access.", parse_mode='HTML', reply_markup=mk)
        except Exception: pass
    return r
_ar_orig_rm = remove_admin_db
def remove_admin_db(admin_id):
    r = _ar_orig_rm(admin_id)
    if r:
        try: _db_exec("DELETE FROM admin_perms WHERE user_id=?", (admin_id,))
        except Exception: pass
    return r

# ---- UI ----
def _ar_name(uid):
    fn, un, _, _ = get_profile(uid, fetch=False)
    return _hmx.escape((fn or (('@' + un) if un else f"User{str(uid)[-4:]}"))[:18])
def _ar_home():
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
    others = sorted(a for a in admin_ids if a != OWNER_ID)
    for a in others:
        p, t = _ar_get(a); m.add(B(f"🛡 {_ar_name(a)} · {t} · {len(p)}/{len(AR_KEYS)}", callback_data=f"ar_u_{a}"))
    m.add(B('⚙️ Default access for NEW admins', callback_data='ar_u_0'), B('➕ Add Admin', callback_data='add_admin'))
    m.add(B('🔙 Back to Admin Panel', callback_data='admin_panel'))
    txt = (f"🛡 <b>Admin Roles</b>\n━━━━━━━━━━━━━━━━━━\nAdmins: <b>{len(others)}</b>\n"
           "Pick an admin to choose exactly which parts of the Admin Panel they can use.\n"
           "<i>Admins you added before this feature keep full access until you change it.</i>" if others else
           "🛡 <b>Admin Roles</b>\n━━━━━━━━━━━━━━━━━━\nNo admins yet besides you.\nUse ➕ Add Admin — new admins get the default access you set below.")
    return txt, m
def _ar_user(uid):
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=2)
    if uid == 0: perms, title = set(_ar_default()[0]), _ar_default()[1]; who = "Default for <b>new admins</b>"
    else: perms, title = _ar_get(uid); who = f"{_ar_name(uid)} · <code>{uid}</code>"
    btns = [B(('✅ ' if k in perms else '❌ ') + lab, callback_data=f"ar_t_{uid}_{k}") for k, lab in AR_PERMS]
    for i in range(0, len(btns), 2): m.row(*btns[i:i + 2])
    m.row(*[B(f"📋 {n}", callback_data=f"ar_p_{uid}_{n}") for n in AR_PRESETS])
    m.row(B('✅ Allow all', callback_data=f"ar_all_{uid}"), B('❌ Remove all', callback_data=f"ar_none_{uid}"))
    m.row(B(f"🏷 Rank title: {title}", callback_data=f"ar_ti_{uid}"))
    if uid: m.row(B('🗑 Remove this admin', callback_data=f"ar_rm_{uid}"))
    m.row(B('🔙 Back', callback_data='ar_home'))
    txt = (f"🛡 <b>Admin Access</b>\n━━━━━━━━━━━━━━━━━━\n{who}\nShown as: <b>🛡️ {_hmx.escape(title)}</b>\nAccess: <b>{len(perms)}</b> of {len(AR_KEYS)}\n\n"
           "Tap an item to turn it ✅ on or ❌ off. Hidden items disappear from that admin's panel.\n"
           "<i>Adding/removing admins, backups and these roles are always owner-only.</i>")
    return txt, m

def roles_callback(call):
    d = call.data
    try: bot.answer_callback_query(call.id)
    except Exception: pass
    if d == 'ar_home': t, m = _ar_home(); return _rp_edit(call, t, m)
    parts = d.split('_', 3); act = parts[1]; uid = int(parts[2]) if len(parts) > 2 and parts[2].lstrip('-').isdigit() else 0
    def cur(): return set(_ar_default()[0]) if uid == 0 else _ar_get(uid)[0]
    def save(perms=None, title=None):
        if uid == 0:
            if perms is not None: set_setting('AR_DEFAULT', ','.join(k for k in AR_KEYS if k in perms))
            if title is not None: set_setting('AR_DEF_TITLE', _ar_title_clean(title))
        else: _ar_set(uid, perms, title)
    if uid and uid not in admin_ids and act not in ('home',): t, m = _ar_home(); return _rp_edit(call, t, m)
    if act == 't':
        k = parts[3]; p = cur()
        if k in AR_KEYS: p.symmetric_difference_update({k}); save(p)
    elif act == 'p': save(set(AR_PRESETS.get(parts[3], [])))
    elif act == 'all': save(set(AR_KEYS))
    elif act == 'none': save(set())
    elif act == 'ti':
        msg = bot.send_message(call.message.chat.id, "🏷 Send the rank title to show for this admin (e.g. <code>Moderator</code>, <code>Support</code>). Letters/numbers only, max 16.\n/cancel to abort.", parse_mode='HTML')
        def h(mm):
            if mm.from_user.id != OWNER_ID or not mm.text or mm.text.strip().lower() == '/cancel': return bot.send_message(mm.chat.id, "Cancelled.")
            save(None, mm.text); t, m = _ar_user(uid); bot.send_message(mm.chat.id, t, parse_mode='HTML', reply_markup=m)
        return bot.register_next_step_handler(msg, h)
    elif act == 'rm':
        B = types.InlineKeyboardButton; mk = types.InlineKeyboardMarkup(); mk.row(B('✅ Yes, remove', callback_data=f"ar_rmy_{uid}"), B('❌ Cancel', callback_data=f"ar_u_{uid}"))
        return _rp_edit(call, f"⚠️ Remove <code>{uid}</code> ({_ar_name(uid)}) from admins?", mk)
    elif act == 'rmy':
        remove_admin_db(uid)
        try: bot.send_message(uid, "ℹ️ You are no longer an admin of this bot.")
        except Exception: pass
        t, m = _ar_home(); return _rp_edit(call, "✅ Admin removed.\n\n" + t, m)
    elif act == 'u': pass
    t, m = _ar_user(uid); _rp_edit(call, t, m)

def roles_me_callback(call):
    uid = call.from_user.id; perms, title = _ar_get(uid)
    rows = [('✅ ' if k in perms else '🔒 ') + lab for k, lab in AR_PERMS]
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(); m.add(B('🔙 Back to Admin Panel', callback_data='admin_panel'))
    try: bot.answer_callback_query(call.id)
    except Exception: pass
    _rp_edit(call, f"🛡 <b>My Access</b>\n━━━━━━━━━━━━━━━━━━\nRank: <b>{'👑 Owner' if uid == OWNER_ID else '🛡️ ' + _hmx.escape(title)}</b>\n\n" + "\n".join(rows) +
             ("\n\n<i>🔒 = not available for your role. Ask the owner for access.</i>" if len(perms) < len(AR_KEYS) else ''), m)

# make the stored handler enforce permissions
def _ar_install_gate():
    try: hs = list(getattr(bot, 'callback_query_handlers', []) or [])
    except Exception: hs = []
    for h in hs:
        try:
            f = h['function']
            if getattr(f, '__name__', '') == 'handle_callbacks' and not getattr(f, '_ar_wrapped', False):
                def mk(f):
                    def w(call):
                        if not _adm_gate(call): return
                        return f(call)
                    w._ar_wrapped = True; w.__name__ = 'handle_callbacks'; return w
                h['function'] = mk(f)
        except Exception as e: logger.warning(f"ar gate install: {e}")
_ar_install_gate()

# ============================================================
# --- Admin limits & options: how many bots an admin can host, and much more ---
# ============================================================
# key: (label, kind, default, min, max, unit)
AR_OPTS = {
    'maxbots':   ('📁 Max hosted bots', 'num', 0, 0, 100000, ''),
    'maxrun':    ('🟢 Max running at once', 'num', 0, 0, 100000, ''),
    'maxmb':     ('📦 Max upload size', 'num', 0, 0, 2000, ' MB'),
    'storage':   ('💽 Storage quota', 'num', 0, 0, 1000000, ' MB'),
    'mem':       ('🧠 RAM limit per bot', 'num', 0, 0, 64000, ' MB'),
    'dailyup':   ('📤 Uploads per day', 'num', 0, 0, 10000, ''),
    'py':        ('🐍 Allow .py files', 'tog', 1, 0, 1, ''),
    'js':        ('🟨 Allow .js files', 'tog', 1, 0, 1, ''),
    'zip':       ('🗜 Allow .zip files', 'tog', 1, 0, 1, ''),
    'selfapp':   ('✅ Auto-approve own uploads', 'tog', 0, 0, 1, ''),
    'maxgrant':  ('🎁 Max plan days per grant', 'num', 0, 0, 3650, ' d'),
    'maxsetlim': ('🔧 Max project limit they can set', 'num', 0, 0, 100000, ''),
    'dailyact':  ('⚡ Sensitive actions per day', 'num', 0, 0, 10000, ''),
    'expdays':   ('⏳ Admin role expires after', 'num', 0, 0, 3650, ' d'),
    'notify':    ('🔔 Notify me of their actions', 'tog', 0, 0, 1, ''),
}
_AR_OPT_HELP = "0 = no limit / use the bot default"

def _ar_init():
    _db_exec("CREATE TABLE IF NOT EXISTS admin_perms (user_id INTEGER PRIMARY KEY, perms TEXT, title TEXT)")
    for sql in ("ALTER TABLE admin_perms ADD COLUMN opts TEXT", "ALTER TABLE admin_perms ADD COLUMN expires TEXT"):
        try: _db_exec(sql)
        except Exception: pass
    _db_exec("CREATE TABLE IF NOT EXISTS ar_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, kind TEXT, detail TEXT, ts TEXT)")

def _ar_set(uid, perms=None, title=None):
    cur_p, cur_t = _ar_get(uid)
    perms = cur_p if perms is None else set(perms); title = cur_t if title is None else _ar_title_clean(title)
    _db_exec("INSERT INTO admin_perms (user_id, perms, title) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET perms=excluded.perms, title=excluded.title",
             (uid, ','.join(k for k in AR_KEYS if k in perms), title))

def _is_ra(uid): return uid in admin_ids and uid != OWNER_ID
def _ar_opts_row(uid):
    try:
        r = _db_q("SELECT opts FROM admin_perms WHERE user_id=?", (uid,), one=True)
        return json.loads(r[0]) if r and r[0] else {}
    except Exception: return {}
def _ar_opts(uid):
    base = {k: v[2] for k, v in AR_OPTS.items()}
    if uid == 0:
        try: base.update(json.loads(get_setting('AR_OPTS_DEF', '') or '{}'))
        except Exception: pass
    else: base.update(_ar_opts_row(uid))
    return base
def _ao(uid, key):
    try: return int(_ar_opts(uid).get(key, AR_OPTS[key][2]))
    except Exception: return AR_OPTS[key][2]
def _ar_opt_set(uid, key, val):
    o = _ar_opts_row(uid) if uid else {}
    if uid == 0:
        try: o = json.loads(get_setting('AR_OPTS_DEF', '') or '{}')
        except Exception: o = {}
    o[key] = int(val)
    if uid == 0: set_setting('AR_OPTS_DEF', json.dumps(o))
    else:
        if not _db_q("SELECT 1 FROM admin_perms WHERE user_id=?", (uid,), one=True): _ar_set(uid)      # legacy admin -> create row (keeps full access)
        _db_exec("UPDATE admin_perms SET opts=? WHERE user_id=?", (json.dumps(o), uid))
    if key == 'expdays' and uid:
        _db_exec("UPDATE admin_perms SET expires=? WHERE user_id=?", ((_now() + timedelta(days=int(val))).isoformat() if int(val) > 0 else None, uid))

# ---- enforcement ----
_ar_orig_limit = get_user_file_limit
def get_user_file_limit(user_id):
    if _is_ra(user_id):
        v = _ao(user_id, 'maxbots')
        if v > 0: return v
    return _ar_orig_limit(user_id)

_ar_orig_upl = _ap_upload_gate
def _ap_upload_gate(message, ext=None, size=None):
    uid = message.from_user.id
    if _is_ra(uid):
        def no(t): bot.reply_to(message, t); return False
        if ext:
            if not _ao(uid, ext.lstrip('.')): return no(f"🚫 Your admin role is not allowed to upload {ext} files.")
            mb = _ao(uid, 'maxmb')
            if mb > 0 and size and size > mb * 1048576: return no(f"⚠️ Your upload limit is {mb} MB.")
            st = _ao(uid, 'storage')
            if st > 0 and _dir_size(get_user_folder(uid)) + (size or 0) > st * 1048576: return no(f"💽 Your storage quota ({st} MB) is full.")
            da = _ao(uid, 'dailyup')
            if da > 0 and _cnt("SELECT COUNT(*) FROM ar_actions WHERE admin_id=? AND kind='upload' AND ts>=?", (uid, _today())) >= da: return no(f"📅 Daily upload limit reached ({da}).")
            _db_exec("INSERT INTO ar_actions (admin_id, kind, detail, ts) VALUES (?,?,?,?)", (uid, 'upload', ext, _now().isoformat()))
    return _ar_orig_upl(message, ext, size)

_ar_orig_run = _ap_run_gate
def _ap_run_gate(owner_id, msg_obj, project):
    if _is_ra(owner_id):
        mr = _ao(owner_id, 'maxrun')
        if mr > 0:
            n = sum(1 for pn, _m, _t in user_files.get(owner_id, []) if pn != project and is_bot_running(owner_id, pn))
            if n >= mr:
                try: bot.send_message(msg_obj.chat.id, f"⚠️ Your admin role can run {mr} bot(s) at the same time. Stop one first.")
                except Exception: pass
                return False
    return _ar_orig_run(owner_id, msg_obj, project)

def _should_auto_approve(is_safe, uid=None):
    if uid is not None and _is_ra(uid) and _ao(uid, 'selfapp') and is_safe: return True
    return _upload_mode() == 'auto' and (is_safe or not _auto_safe_only())

def _ar_guard(uid, kind, val=0):
    """None when the admin may do it (and the action is logged), else the refusal text."""
    if not _is_ra(uid): return None
    if kind == 'grant' and _ao(uid, 'maxgrant') > 0 and val > _ao(uid, 'maxgrant'): return f"⚠️ Your role can grant at most {_ao(uid, 'maxgrant')} days at a time."
    if kind == 'setlimit' and _ao(uid, 'maxsetlim') > 0 and val > _ao(uid, 'maxsetlim'): return f"⚠️ Your role can set a project limit of at most {_ao(uid, 'maxsetlim')}."
    da = _ao(uid, 'dailyact')
    if da > 0 and _cnt("SELECT COUNT(*) FROM ar_actions WHERE admin_id=? AND kind<>'upload' AND ts>=?", (uid, _today())) >= da:
        return f"⚠️ Daily action limit reached ({da}). Try again tomorrow."
    _db_exec("INSERT INTO ar_actions (admin_id, kind, detail, ts) VALUES (?,?,?,?)", (uid, kind, str(val), _now().isoformat()))
    if _ao(uid, 'notify'):
        try: bot.send_message(OWNER_ID, f"🔔 <b>{_adm_rank(uid)}</b> {_ar_name(uid)} (<code>{uid}</code>): <b>{kind}</b> {_hmx.escape(str(val))}", parse_mode='HTML')
        except Exception: pass
    return None

_ar_orig_ban = ban_user_db
def ban_user_db(user_id, reason, banned_by):
    g = _ar_guard(banned_by, 'ban', user_id)
    if g:
        try: bot.send_message(banned_by, g)
        except Exception: pass
        return False
    return _ar_orig_ban(user_id, reason, banned_by)

# ---- watcher: RAM limit per admin bot + admin role expiry ----
def _ar_watch():
    while True:
        time.sleep(30)
        try:
            for k, i in list(bot_scripts.items()):
                o = i.get('script_owner_id')
                if not _is_ra(o): continue
                lim = _ao(o, 'mem')
                if lim <= 0 or not _is_running(k): continue
                try:
                    p = psutil.Process(i['process'].pid); rss = p.memory_info().rss + sum(c.memory_info().rss for c in p.children(recursive=True))
                except Exception: continue
                if rss > lim * 1048576:
                    kill_process_tree(i); bot_scripts.pop(k, None)
                    try: bot.send_message(o, f"⏹️ <b>{_hmx.escape(str(i.get('project_name')))}</b> was stopped: it used more than your {lim} MB RAM limit.", parse_mode='HTML')
                    except Exception: pass
            now = _now().isoformat()
            for uid, exp in _db_q("SELECT user_id, expires FROM admin_perms WHERE expires IS NOT NULL AND expires<>''"):
                if exp < now and uid in admin_ids and uid != OWNER_ID:
                    remove_admin_db(uid)
                    for t, txt in ((uid, "ℹ️ Your admin role has expired."), (OWNER_ID, f"⌛ Admin <code>{uid}</code> ({_ar_name(uid)}) expired and was removed.")):
                        try: bot.send_message(t, txt, parse_mode='HTML')
                        except Exception: pass
        except Exception as e: logger.warning(f"ar_watch: {e}")

# ---- new admin gets the default limits ----
_ar2_prev_add = add_admin_db
def add_admin_db(admin_id):
    new = admin_id not in admin_ids and admin_id != OWNER_ID
    r = _ar2_prev_add(admin_id)
    if new:
        try:
            d = _ar_opts(0)
            for k in AR_OPTS:
                if d.get(k) != AR_OPTS[k][2]: _ar_opt_set(admin_id, k, d[k])
        except Exception as e: logger.warning(f"apply default admin limits: {e}")
    return r

# ---- UI ----
def _ar_val(uid, key):
    lab, kind, _d, _lo, _hi, unit = AR_OPTS[key]; v = _ao(uid, key)
    if kind == 'tog': return ('✅ ' if v else '❌ ') + lab
    return f"{lab}: {('∞' if v == 0 else str(v) + unit)}"
def _ar_opts_view(uid):
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(row_width=1)
    for k in AR_OPTS: m.add(B(_ar_val(uid, k), callback_data=f"ar_x_{uid}_{k}"))
    m.add(B('🔙 Back', callback_data=f"ar_u_{uid}"))
    who = "Default for <b>new admins</b>" if uid == 0 else f"{_ar_name(uid)} · <code>{uid}</code>"
    extra = ''
    if uid:
        r = _db_q("SELECT expires FROM admin_perms WHERE user_id=?", (uid,), one=True)
        if r and r[0]: extra = f"\n⏳ Role ends: <b>{r[0][:10]}</b>"
        used = len(user_files.get(uid, [])); extra += f"\n📁 Hosting now: <b>{used}</b> / {get_user_file_limit(uid)}"
    return (f"⚙️ <b>Admin Limits</b>\n━━━━━━━━━━━━━━━━━━\n{who}{extra}\n\nTap an item to change it. <i>{_AR_OPT_HELP}.</i>"), m

_ar_user_orig = _ar_user
def _ar_user(uid):
    t, m = _ar_user_orig(uid)
    try: m.keyboard.insert(max(0, len(m.keyboard) - 1), [types.InlineKeyboardButton('⚙️ Limits & Options (bots, storage, RAM…)', callback_data=f"ar_o_{uid}")])
    except Exception: pass
    return t, m

_ar_roles_prev = roles_callback
def roles_callback(call):
    d = call.data
    if d.startswith('ar_o_') or d.startswith('ar_x_'):
        try: bot.answer_callback_query(call.id)
        except Exception: pass
        parts = d.split('_', 3); uid = int(parts[2])
        if uid and uid not in admin_ids: t, m = _ar_home(); return _rp_edit(call, t, m)
        if d.startswith('ar_x_'):
            key = parts[3]
            if key in AR_OPTS:
                lab, kind, _df, lo, hi, unit = AR_OPTS[key]
                if kind == 'tog': _ar_opt_set(uid, key, 0 if _ao(uid, key) else 1)
                else:
                    msg = bot.send_message(call.message.chat.id, f"✏️ <b>{_hmx.escape(lab)}</b>\nCurrent: <b>{_ao(uid, key)}</b>\nSend a number from {lo} to {hi} ({_AR_OPT_HELP}). /cancel to abort.", parse_mode='HTML')
                    def h(mm):
                        if mm.from_user.id != OWNER_ID or not mm.text or mm.text.strip().lower() == '/cancel': return bot.send_message(mm.chat.id, "Cancelled.")
                        try: v = int(float(mm.text.strip())); assert lo <= v <= hi
                        except Exception: return bot.send_message(mm.chat.id, f"❌ Send a whole number from {lo} to {hi}.")
                        _ar_opt_set(uid, key, v); t, mk = _ar_opts_view(uid); bot.send_message(mm.chat.id, "✅ Saved.\n\n" + t, parse_mode='HTML', reply_markup=mk)
                    return bot.register_next_step_handler(msg, h)
        t, m = _ar_opts_view(uid); return _rp_edit(call, t, m)
    return _ar_roles_prev(call)

def roles_me_callback(call):
    uid = call.from_user.id; perms, title = _ar_get(uid)
    rows = [('✅ ' if k in perms else '🔒 ') + lab for k, lab in AR_PERMS]
    B = types.InlineKeyboardButton; m = types.InlineKeyboardMarkup(); m.add(B('🔙 Back to Admin Panel', callback_data='admin_panel'))
    try: bot.answer_callback_query(call.id)
    except Exception: pass
    lim = ''
    if _is_ra(uid):
        o = _ar_opts(uid); r = _db_q("SELECT expires FROM admin_perms WHERE user_id=?", (uid,), one=True)
        L = [f"📁 Hosted bots ▸ <b>{len(user_files.get(uid, []))} / {get_user_file_limit(uid)}</b>"]
        if o['maxrun']: L.append(f"🟢 Running at once ▸ <b>{o['maxrun']}</b>")
        if o['maxmb']: L.append(f"📦 Max upload ▸ <b>{o['maxmb']} MB</b>")
        if o['storage']: L.append(f"💽 Storage ▸ <b>{o['storage']} MB</b>")
        if o['mem']: L.append(f"🧠 RAM per bot ▸ <b>{o['mem']} MB</b>")
        if o['dailyup']: L.append(f"📤 Uploads/day ▸ <b>{o['dailyup']}</b>")
        if o['dailyact']: L.append(f"⚡ Actions/day ▸ <b>{o['dailyact']}</b>")
        if o['maxgrant']: L.append(f"🎁 Max grant ▸ <b>{o['maxgrant']} d</b>")
        if r and r[0]: L.append(f"⏳ Role ends ▸ <b>{r[0][:10]}</b>")
        lim = "\n\n<b>◈ LIMITS</b>\n<blockquote>" + "\n".join(L) + "</blockquote>"
    _rp_edit(call, f"🛡 <b>My Access</b>\n━━━━━━━━━━━━━━━━━━\nRank: <b>{'👑 Owner' if uid == OWNER_ID else '🛡️ ' + _hmx.escape(title)}</b>\n\n" + "\n".join(rows) +
             ("\n\n<i>🔒 = not available for your role. Ask the owner for access.</i>" if len(perms) < len(AR_KEYS) else '') + lim, m)

# ============================================================
# --- Admin approval permissions + more per-admin options ---
# ============================================================
for _k, _l in (('approve', '✅ Approve Bots'), ('reject', '❌ Reject Bots'), ('approveall', '⚡ Approve All Pending'),
               ('viewfiles', '📂 View Users\' Files')):
    if _k not in AR_KEYS: AR_PERMS.append((_k, _l)); AR_KEYS.append(_k)
AR_PRESETS['Support'] = ['users', 'pending', 'approve', 'reject']
AR_PRESETS['Manager'] = AR_PRESETS['Manager'] + ['approve', 'reject', 'approveall', 'viewfiles']
AR_PRESETS['Full'] = list(AR_KEYS)
LB_DEF['AR_DEFAULT'] = 'users,pending,approve,reject'
_AR_EXACT.update({'ua_all': 'approveall', 'ua_all_yes': 'approveall'})
_AR_PREFIX[:0] = [('approve_file_', 'approve'), ('approve_zip_', 'approve'), ('reject_file_', 'reject'), ('reject_zip_', 'reject'),
                  ('admin_user_files_', 'viewfiles')]
AR_OPTS.update({
    'apprday':  ('✅ Approvals per day', 'num', 0, 0, 10000, ''),
    'apprsafe': ('🛡 Approve only scan-safe files', 'tog', 0, 0, 1, ''),
    'noself':   ('🚫 Cannot approve own uploads', 'tog', 1, 0, 1, ''),
    'rejday':   ('❌ Rejections per day', 'num', 0, 0, 10000, ''),
    'apprnote': ('🔔 Notify me on approve/reject', 'tog', 0, 0, 1, ''),
})

def _ar3_migrate():
    try:
        if get_setting('AR3_MIG', '') == '1': return
        for uid, p in _db_q("SELECT user_id, perms FROM admin_perms"):
            ps = [x for x in str(p or '').split(',') if x]
            for src, ks in (('pending', ('approve', 'reject', 'approveall')), ('users', ('viewfiles',))):
                if src in ps:
                    for k in ks:
                        if k not in ps: ps.append(k)
                _db_exec("UPDATE admin_perms SET perms=? WHERE user_id=?", (','.join(ps), uid))
        d = [x for x in str(get_setting('AR_DEFAULT', '') or '').split(',') if x]
        if 'pending' in d:
            for k in ('approve', 'reject'):
                if k not in d: d.append(k)
            set_setting('AR_DEFAULT', ','.join(d))
        set_setting('AR3_MIG', '1')
    except Exception as e: logger.warning(f"ar3 migrate: {e}")

def _ar3_wrap(orig, kind, zip_):
    def w(call):
        uid = call.from_user.id
        if _is_ra(uid):
            try:
                parts = call.data.split('_', 3); tu = int(parts[2]); pn = parts[3]
                def no(t): bot.answer_callback_query(call.id, t, show_alert=True); return None
                if kind == 'approve' and _ao(uid, 'noself') and tu == uid: return no("🚫 You can't approve your own upload. Ask the owner.")
                cap = _ao(uid, 'apprday' if kind == 'approve' else 'rejday')
                if cap > 0 and _cnt("SELECT COUNT(*) FROM ar_actions WHERE admin_id=? AND kind=? AND ts>=?", (uid, kind, _today())) >= cap:
                    return no(f"📅 Daily {kind} limit reached ({cap}).")
                if kind == 'approve' and _ao(uid, 'apprsafe'):
                    e = (pending_zip_files if zip_ else pending_script_files).get(tu, {}).get(pn) or {}
                    safe = (not e.get('patterns')) if zip_ else e.get('is_safe', False)
                    if not safe: return no("🛡 Your role may only approve files that passed the security scan.")
                _db_exec("INSERT INTO ar_actions (admin_id, kind, detail, ts) VALUES (?,?,?,?)", (uid, kind, f"{tu}/{pn}", _now().isoformat()))
                if _ao(uid, 'apprnote'):
                    try: bot.send_message(OWNER_ID, f"🔔 {_adm_rank(uid)} {_ar_name(uid)} (<code>{uid}</code>) <b>{kind}d</b> <code>{_hmx.escape(pn)}</code> of <code>{tu}</code>", parse_mode='HTML')
                    except Exception: pass
            except Exception as e: logger.warning(f"ar3 approve guard: {e}")
        return orig(call)
    return w
process_approve_file = _ar3_wrap(process_approve_file, 'approve', False)
process_approve_zip = _ar3_wrap(process_approve_zip, 'approve', True)
process_reject_file = _ar3_wrap(process_reject_file, 'reject', False)
process_reject_zip = _ar3_wrap(process_reject_zip, 'reject', True)

_ar3_prev_init = _ar_init
def _ar_init():
    _ar3_prev_init(); _ar3_migrate()

if __name__ == '__main__':
    def startup():
        """Initialize DB and load persisted data. Called once at startup."""
        init_db()
        _lb_init()
        _rc_init()
        _ap_init()
        _sm_init()
        _ar_init()
        load_data()

    logger.info("="*50 + "\n🤖 FENIX HOSTING BOT Starting...\n" +
                f"🐍 Python: {sys.version.split()[0]}\n"
                f"🔧 Base Dir: {BASE_DIR}\n📁 Upload Dir: {UPLOAD_BOTS_DIR}\n"
                f"📊 Data Dir: {IROTECH_DIR}\n🔑 Owner ID: {OWNER_ID}\n"
                f"🛡️ Admins: {len(admin_ids)} | 🚫 Banned: {len(banned_users)}\n" + "="*50)
    class _OwnerErrorHandler:
        """Logs every handler/polling error and DMs the owner (max 1 per minute)."""
        last = 0
        def handle(self, exception):
            logger.error(f"Bot error: {exception}", exc_info=exception)
            if time.time() - self.last > 60 and _lbf('NTF_ERROR_DM'):
                self.last = time.time()
                try: bot.send_message(OWNER_ID, f"⚠️ Bot error:\n{str(exception)[:900]}")
                except Exception: pass
            return True
    bot.exception_handler = _OwnerErrorHandler()
    startup()
    keep_alive()
    try:
        me = bot.get_me()
        logger.info(f"✅ Connected as @{me.username} (id {me.id})")
        try:
            if _lbf('NTF_STARTUP_DM'): bot.send_message(OWNER_ID, f"✅ <b>Bot started</b> as @{me.username}\n🕒 {datetime.now():%d-%m-%Y %H:%M:%S}\nIf you see this, the bot can reach Telegram. Send /start to test replies.", parse_mode='HTML')
        except Exception as _e: logger.warning(f"Could not DM owner on startup: {_e}")
    except Exception as e:
        logger.critical(f"❌ Token check failed (wrong/revoked BOT_TOKEN?): {e}")
    try:
        bot.remove_webhook()   # a leftover webhook makes polling receive nothing
    except Exception as e:
        logger.warning(f"remove_webhook failed: {e}")
    threading.Thread(target=payments_housekeeping, daemon=True).start()
    threading.Thread(target=_ap_watcher, daemon=True).start()
    threading.Thread(target=_bkp_auto_loop, daemon=True).start()
    threading.Thread(target=_sm_loop, daemon=True).start()
    threading.Thread(target=_ar_watch, daemon=True).start()
    threading.Thread(target=admin_housekeeping, daemon=True).start()
    setup_command_menu()
    logger.info("🚀 Starting polling...")
    while True:
        try:
            bot.infinity_polling(logger_level=logging.INFO, timeout=60, long_polling_timeout=30)
        except requests.exceptions.ReadTimeout:
            logger.warning("Polling ReadTimeout. Restarting in 5s...")
            time.sleep(5)
        except requests.exceptions.ConnectionError as ce:
            logger.error(f"Polling ConnectionError: {ce}. Retrying in 15s...")
            time.sleep(15)
        except Exception as e:
            if '409' in str(e) or 'Conflict' in str(e):
                logger.critical("⚠️ 409 Conflict: another process is polling with the SAME bot token. "
                                "Use a separate token for this bot (set BOT_TOKEN) or stop the other instance.")
            logger.critical(f"💥 Unrecoverable polling error: {e}", exc_info=True)
            logger.info("Restarting polling in 30s...")
            time.sleep(30)
        finally:
            logger.warning("Polling attempt finished. Will restart if in loop.")
            time.sleep(1)
