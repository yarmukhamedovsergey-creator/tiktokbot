"""
TikTok Auto Commenter v4.0
Fixed UI + Russian
"""

import os
import json
import time
import random
import hashlib
import re
import threading
from urllib.parse import quote
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

from kivy.app import App
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.properties import StringProperty, NumericProperty
from kivy.utils import platform
from kivy.animation import Animation
from kivy.metrics import dp, sp

if platform != 'android':
    from kivy.core.window import Window
    Window.size = (400, 750)

if platform == 'android':
    try:
        from android.permissions import request_permissions, Permission
        request_permissions([Permission.INTERNET, Permission.WRITE_EXTERNAL_STORAGE])
    except Exception:
        pass


HISTORY_FILE = 'comment_history.json'
if platform == 'android':
    try:
        HISTORY_FILE = os.path.join(
            os.environ.get('EXTERNAL_STORAGE', '/sdcard'),
            'tiktokbot_history.json'
        )
    except Exception:
        pass


def load_history():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return []

def save_history(h):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(h, f, ensure_ascii=False, indent=1)
    except Exception:
        pass

def add_to_history(vid, txt, ok, err=''):
    try:
        h = load_history()
        h.append({
            'time': datetime.now().strftime('%d.%m %H:%M'),
            'video': vid, 'text': txt, 'ok': ok, 'error': err,
        })
        if len(h) > 500:
            h = h[-500:]
        save_history(h)
    except Exception:
        pass

def format_history():
    h = load_history()
    if not h:
        return '[color=888899]История пуста[/color]'
    lines = []
    for item in reversed(h):
        t = item.get('time', '?')
        vid = item.get('video', '?')
        txt = item.get('text', '?')
        ok = item.get('ok', False)
        err = item.get('error', '')
        sv = vid[:8] + '..' + vid[-4:] if len(vid) > 14 else vid
        if ok:
            s = '[color=66dd88]OK[/color]'
        else:
            s = '[color=ff6666]' + (err[:30] if err else 'FAIL') + '[/color]'
        lines.append(
            '[color=889999]' + t + '[/color]  ' + s + '\n'
            '[color=99aacc]' + sv + '[/color]\n'
            '[color=ddddee]' + txt + '[/color]\n'
        )
    return '\n'.join(lines)

def get_stats():
    h = load_history()
    t = len(h)
    o = sum(1 for x in h if x.get('ok'))
    return t, o, t - o


EMOJIS = [
    '\U0001f525','\U0001f4af','\U0001f44d','\u2728','\U0001f4aa',
    '\U0001f64c','\u2764\ufe0f','\U0001f60a','\U0001f440','\U0001f3af',
    '\u2b50','\U0001f31f','\U0001f4ab','\U0001f389','\U0001f919',
    '\U0001f44f','\U0001f4a5','\U0001f680','\U0001f48e','\U0001f3c6',
    '\U0001f60e','\U0001f91e','\u2705','\U0001f51d',
    '\U0001f91d','\u26a1','\U0001f38a',
]
INVISIBLE = ['\u200b','\u200c','\u200d','\ufeff','\u00ad','\u2060']
ENDINGS_LIST = ['!','!!','...','.',')',')))','!!!','~','!~','..!']
SEPS = [' ','_','.','\u00b7',' ','-']


class CommentGen:
    def __init__(self, templates):
        self.t = [x for x in templates if x.strip()]
        self.used = set()
        self.i = 0
    def next(self):
        base = self.t[self.i % len(self.t)]
        self.i += 1
        for _ in range(300):
            r = self._m(base)
            if r not in self.used:
                self.used.add(r)
                return r
        f = base + ' ' + str(self.i)
        self.used.add(f)
        return f
    def _m(self, t):
        mods = [self._inv, self._sp, self._em, self._cs, self._end, self._dbl]
        for fn in random.sample(mods, random.randint(2, 3)):
            t = fn(t)
        return t
    def _inv(self, t):
        p = random.randint(1, max(1, len(t)-1))
        return t[:p] + random.choice(INVISIBLE) + t[p:]
    def _sp(self, t):
        pp = [i for i, c in enumerate(t) if c == ' ']
        if not pp: return t
        p = random.choice(pp)
        return t[:p] + random.choice(SEPS) + t[p+1:]
    def _em(self, t):
        e = random.choice(EMOJIS)
        return (t + ' ' + e) if random.random() > 0.35 else (e + ' ' + t)
    def _cs(self, t):
        c = list(t)
        i = random.randint(0, len(c) - 1)
        c[i] = c[i].swapcase()
        return ''.join(c)
    def _end(self, t):
        return t.rstrip('!.~) ') + random.choice(ENDINGS_LIST)
    def _dbl(self, t):
        if len(t) < 3: return t
        i = random.randint(1, len(t) - 2)
        return t[:i] + t[i] + t[i:] if t[i].isalpha() else t


class TikTok:
    UA = (
        'Mozilla/5.0 (Linux; Android 14; SM-S928B) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/125.0.6422.165 Mobile Safari/537.36'
    )
    def __init__(self):
        self.s = requests.Session()
        self.sid = ''
        self.csrf = ''
        self.ms = ''
        self.username = ''
    def login_cookie(self, sid):
        self.sid = sid.strip()
        self.s.cookies.set('sessionid', self.sid, domain='.tiktok.com', path='/')
        self.s.headers.update({'User-Agent': self.UA, 'Accept': 'text/html', 'Accept-Language': 'en-US,en;q=0.9'})
        try:
            r = self.s.get('https://www.tiktok.com/', timeout=30)
            self._tok(r)
            m = re.search(r'"uniqueId":"([^"]+)"', r.text)
            if m:
                self.username = m.group(1)
                return True, self.username
            if len(r.text) > 50000:
                self.username = 'ok'
                return True, self.username
            return False, 'Cookie невалидный'
        except requests.exceptions.ConnectionError:
            return False, 'Нет интернета'
        except requests.exceptions.Timeout:
            return False, 'Таймаут'
        except Exception as e:
            return False, str(e)
    def login_password(self, email, pwd):
        ph = hashlib.md5(pwd.encode()).hexdigest()
        did = str(random.randint(7000000000000000000, 7999999999999999999))
        iid = str(random.randint(7000000000000000000, 7999999999999999999))
        p = {'aid':'1233','device_id':did,'iid':iid,'os_api':'28','device_type':'SM-S928B','device_brand':'samsung','os_version':'14','app_name':'musical_ly','version_code':'2023501030','channel':'googleplay','language':'en'}
        d = {'mix_mode':'1','email':email,'password':ph,'username':'','mobile':''}
        self.s.headers.update({'User-Agent':'com.zhiliaoapp.musically/2023501030 TTNet/3.1.0','Content-Type':'application/x-www-form-urlencoded'})
        try:
            r = self.s.post('https://api22-normal-c-useast2a.tiktokv.com/passport/user/login/', params=p, data=d, timeout=30)
            j = r.json()
            if j.get('error_code', -1) == 0 or j.get('message') == 'success':
                dd = j.get('data', {})
                self.sid = dd.get('session_key', '')
                for c in r.cookies:
                    if c.name == 'sessionid': self.sid = c.value
                self.username = dd.get('username', '')
                self.s.cookies.set('sessionid', self.sid, domain='.tiktok.com', path='/')
                self.s.headers['User-Agent'] = self.UA
                return True, self.username
            msg = j.get('data', {}).get('description', j.get('message', '?'))
            return False, str(msg)
        except requests.exceptions.ConnectionError:
            return False, 'Нет интернета'
        except Exception as e:
            return False, str(e)
    def _tok(self, r):
        try:
            for c in self.s.cookies:
                if c.name == 'tt_csrf_token': self.csrf = c.value
                elif c.name == 'msToken': self.ms = c.value
        except Exception: pass
    def search(self, kw, count=30):
        ids = []
        try:
            self.s.headers['Accept'] = 'text/html'
            self.s.headers['Referer'] = 'https://www.tiktok.com/'
            r = self.s.get('https://www.tiktok.com/search/video?q=' + quote(kw), timeout=30)
            self._tok(r)
            for m in re.finditer(r'(?:video/|"id":"|"aweme_id":")\s*(\d{15,25})', r.text):
                ids.append(m.group(1))
        except Exception: pass
        seen = set()
        u = []
        for v in ids:
            if v not in seen:
                seen.add(v)
                u.append(v)
        return u[:count]
    def comment(self, vid, text):
        try:
            self.s.headers['Accept'] = 'text/html'
            self.s.headers['Referer'] = 'https://www.tiktok.com/'
            r = self.s.get('https://www.tiktok.com/video/' + vid, timeout=20)
            self._tok(r)
            time.sleep(random.uniform(0.5, 1.5))
            self.s.headers.update({'Accept':'application/json','Content-Type':'application/x-www-form-urlencoded','Referer':'https://www.tiktok.com/video/'+vid,'Origin':'https://www.tiktok.com'})
            if self.csrf: self.s.headers['X-CSRFToken'] = self.csrf
            p = {'aid':'1988'}
            if self.ms: p['msToken'] = self.ms
            r = self.s.post('https://www.tiktok.com/api/comment/publish/', params=p, data={'aweme_id':vid,'text':text,'text_extra':'[]','is_self_see':'0'}, timeout=20)
            if r.status_code == 200:
                j = r.json()
                if j.get('status_code') == 0: return True, 'OK'
                return False, j.get('status_msg', '?')
            return False, 'HTTP ' + str(r.status_code)
        except Exception as e:
            return False, str(e)
    def reply(self, vid, text):
        try:
            self.s.headers['Accept'] = 'application/json'
            self.s.headers['Referer'] = 'https://www.tiktok.com/video/' + vid
            r = self.s.get('https://www.tiktok.com/api/comment/list/', params={'aid':'1988','aweme_id':vid,'count':'5','cursor':'0'}, timeout=20)
            cid = ''
            if r.status_code == 200:
                cc = r.json().get('comments', [])
                if cc: cid = str(cc[0].get('cid', ''))
            if not cid: return self.comment(vid, text)
            time.sleep(random.uniform(0.5, 1.5))
            self.s.headers.update({'Content-Type':'application/x-www-form-urlencoded','Origin':'https://www.tiktok.com'})
            if self.csrf: self.s.headers['X-CSRFToken'] = self.csrf
            r = self.s.post('https://www.tiktok.com/api/comment/publish/', params={'aid':'1988'}, data={'aweme_id':vid,'text':text,'reply_id':cid,'text_extra':'[]','is_self_see':'0'}, timeout=20)
            if r.status_code == 200:
                j = r.json()
                if j.get('status_code') == 0: return True, 'OK'
                return False, j.get('status_msg', '?')
            return False, 'HTTP ' + str(r.status_code)
        except Exception as e:
            return False, str(e)


KV = '''
#:import dp kivy.metrics.dp
#:import sp kivy.metrics.sp

ScreenManager:
    id: sm

    # ========== MAIN SCREEN ==========
    Screen:
        name: 'login'
        canvas.before:
            Color:
                rgba: 0.07, 0.07, 0.10, 1
            Rectangle:
                pos: self.pos
                size: self.size

        ScrollView:
            do_scroll_x: False
            bar_width: dp(0)

            BoxLayout:
                orientation: 'vertical'
                padding: dp(18)
                spacing: dp(10)
                size_hint_y: None
                height: self.minimum_height

                Widget:
                    size_hint_y: None
                    height: dp(15)

                Label:
                    text: 'TikTok Bot'
                    font_size: sp(28)
                    bold: True
                    color: 1, 1, 1, 1
                    size_hint_y: None
                    height: dp(45)

                Label:
                    text: app.status
                    font_size: sp(12)
                    color: 0.55, 0.7, 0.95, 1
                    size_hint_y: None
                    height: dp(22)

                # --- History button ---
                Button:
                    text: 'История комментариев'
                    font_size: sp(13)
                    size_hint_y: None
                    height: dp(44)
                    background_normal: ''
                    background_color: 0.13, 0.16, 0.25, 1
                    color: 0.6, 0.75, 1, 1
                    on_release: app.show_history()

                Widget:
                    size_hint_y: None
                    height: dp(6)

                # --- Login section ---
                Label:
                    text: 'СПОСОБ ВХОДА'
                    font_size: sp(11)
                    bold: True
                    color: 0.45, 0.65, 1, 1
                    size_hint_y: None
                    height: dp(26)
                    halign: 'left'
                    text_size: self.size

                BoxLayout:
                    size_hint_y: None
                    height: dp(42)
                    spacing: dp(8)

                    ToggleButton:
                        id: btn_cookie
                        text: 'Cookie'
                        group: 'login'
                        state: 'down'
                        font_size: sp(13)
                        background_normal: ''
                        background_down: ''
                        background_color: (0.22, 0.42, 0.82, 1) if self.state == 'down' else (0.16, 0.16, 0.24, 1)
                        color: 1, 1, 1, 1
                        on_state: app.switch_login('cookie')

                    ToggleButton:
                        id: btn_pass
                        text: 'Email + Пароль'
                        group: 'login'
                        font_size: sp(13)
                        background_normal: ''
                        background_down: ''
                        background_color: (0.22, 0.42, 0.82, 1) if self.state == 'down' else (0.16, 0.16, 0.24, 1)
                        color: 1, 1, 1, 1
                        on_state: app.switch_login('password')

                # Cookie box
                BoxLayout:
                    id: cookie_box
                    orientation: 'vertical'
                    size_hint_y: None
                    height: dp(100)
                    opacity: 1
                    spacing: dp(6)

                    Label:
                        text: 'Chrome > tiktok.com > войди > в строке:\\njavascript:prompt("c",document.cookie)\\nнайди sessionid=XXX скопируй XXX'
                        font_size: sp(9)
                        color: 0.45, 0.45, 0.55, 1
                        size_hint_y: None
                        height: dp(42)
                        halign: 'left'
                        text_size: self.size

                    TextInput:
                        id: inp_cookie
                        hint_text: 'Вставь sessionid сюда'
                        multiline: False
                        size_hint_y: None
                        height: dp(48)
                        font_size: sp(14)
                        background_normal: ''
                        background_color: 0.15, 0.15, 0.22, 1
                        foreground_color: 1, 1, 1, 1
                        hint_text_color: 0.45, 0.45, 0.55, 1
                        cursor_color: 0.5, 0.7, 1, 1
                        padding: dp(14), dp(12)

                # Password box
                BoxLayout:
                    id: pass_box
                    orientation: 'vertical'
                    size_hint_y: None
                    height: dp(0)
                    opacity: 0
                    spacing: dp(6)

                    TextInput:
                        id: inp_email
                        hint_text: 'Email'
                        multiline: False
                        size_hint_y: None
                        height: dp(48)
                        font_size: sp(14)
                        background_normal: ''
                        background_color: 0.15, 0.15, 0.22, 1
                        foreground_color: 1, 1, 1, 1
                        hint_text_color: 0.45, 0.45, 0.55, 1
                        cursor_color: 0.5, 0.7, 1, 1
                        padding: dp(14), dp(12)

                    TextInput:
                        id: inp_pass
                        hint_text: 'Пароль'
                        multiline: False
                        password: True
                        size_hint_y: None
                        height: dp(48)
                        font_size: sp(14)
                        background_normal: ''
                        background_color: 0.15, 0.15, 0.22, 1
                        foreground_color: 1, 1, 1, 1
                        hint_text_color: 0.45, 0.45, 0.55, 1
                        cursor_color: 0.5, 0.7, 1, 1
                        padding: dp(14), dp(12)

                # --- Search ---
                Label:
                    text: 'ПОИСКОВЫЙ ЗАПРОС'
                    font_size: sp(11)
                    bold: True
                    color: 0.45, 0.65, 1, 1
                    size_hint_y: None
                    height: dp(26)
                    halign: 'left'
                    text_size: self.size

                TextInput:
                    id: inp_keyword
                    hint_text: 'Например: тг юзы'
                    multiline: False
                    size_hint_y: None
                    height: dp(48)
                    font_size: sp(14)
                    background_normal: ''
                    background_color: 0.15, 0.15, 0.22, 1
                    foreground_color: 1, 1, 1, 1
                    hint_text_color: 0.45, 0.45, 0.55, 1
                    cursor_color: 0.5, 0.7, 1, 1
                    padding: dp(14), dp(12)

                # --- Comments ---
                Label:
                    text: 'КОММЕНТАРИИ'
                    font_size: sp(11)
                    bold: True
                    color: 0.45, 0.65, 1, 1
                    size_hint_y: None
                    height: dp(26)
                    halign: 'left'
                    text_size: self.size

                Label:
                    text: 'Бот чередует и делает каждый уникальным'
                    font_size: sp(10)
                    color: 0.4, 0.4, 0.5, 1
                    size_hint_y: None
                    height: dp(18)
                    halign: 'left'
                    text_size: self.size

                TextInput:
                    id: inp_c1
                    hint_text: 'Вариант 1 (обязательно)'
                    multiline: False
                    size_hint_y: None
                    height: dp(46)
                    font_size: sp(14)
                    background_normal: ''
                    background_color: 0.15, 0.15, 0.22, 1
                    foreground_color: 1, 1, 1, 1
                    hint_text_color: 0.45, 0.45, 0.55, 1
                    cursor_color: 0.5, 0.7, 1, 1
                    padding: dp(14), dp(12)

                TextInput:
                    id: inp_c2
                    hint_text: 'Вариант 2'
                    multiline: False
                    size_hint_y: None
                    height: dp(46)
                    font_size: sp(14)
                    background_normal: ''
                    background_color: 0.15, 0.15, 0.22, 1
                    foreground_color: 1, 1, 1, 1
                    hint_text_color: 0.45, 0.45, 0.55, 1
                    cursor_color: 0.5, 0.7, 1, 1
                    padding: dp(14), dp(12)

                TextInput:
                    id: inp_c3
                    hint_text: 'Вариант 3'
                    multiline: False
                    size_hint_y: None
                    height: dp(46)
                    font_size: sp(14)
                    background_normal: ''
                    background_color: 0.15, 0.15, 0.22, 1
                    foreground_color: 1, 1, 1, 1
                    hint_text_color: 0.45, 0.45, 0.55, 1
                    cursor_color: 0.5, 0.7, 1, 1
                    padding: dp(14), dp(12)

                TextInput:
                    id: inp_c4
                    hint_text: 'Вариант 4'
                    multiline: False
                    size_hint_y: None
                    height: dp(46)
                    font_size: sp(14)
                    background_normal: ''
                    background_color: 0.15, 0.15, 0.22, 1
                    foreground_color: 1, 1, 1, 1
                    hint_text_color: 0.45, 0.45, 0.55, 1
                    cursor_color: 0.5, 0.7, 1, 1
                    padding: dp(14), dp(12)

                # --- Settings ---
                Label:
                    text: 'НАСТРОЙКИ'
                    font_size: sp(11)
                    bold: True
                    color: 0.45, 0.65, 1, 1
                    size_hint_y: None
                    height: dp(26)
                    halign: 'left'
                    text_size: self.size

                BoxLayout:
                    size_hint_y: None
                    height: dp(44)
                    spacing: dp(10)
                    Label:
                        text: 'Кол-во видео:'
                        color: 0.7, 0.7, 0.8, 1
                        font_size: sp(13)
                        halign: 'left'
                        text_size: self.size
                        valign: 'center'
                    TextInput:
                        id: inp_count
                        text: '30'
                        multiline: False
                        input_filter: 'int'
                        size_hint_x: 0.25
                        size_hint_y: None
                        height: dp(42)
                        font_size: sp(15)
                        halign: 'center'
                        background_normal: ''
                        background_color: 0.15, 0.15, 0.22, 1
                        foreground_color: 1, 1, 1, 1
                        padding: dp(8), dp(10)

                BoxLayout:
                    size_hint_y: None
                    height: dp(44)
                    spacing: dp(8)
                    Label:
                        text: 'Пауза (сек):'
                        color: 0.7, 0.7, 0.8, 1
                        font_size: sp(13)
                        halign: 'left'
                        text_size: self.size
                        valign: 'center'
                    TextInput:
                        id: inp_dmin
                        text: '10'
                        multiline: False
                        input_filter: 'int'
                        size_hint_x: 0.13
                        size_hint_y: None
                        height: dp(42)
                        font_size: sp(15)
                        halign: 'center'
                        background_normal: ''
                        background_color: 0.15, 0.15, 0.22, 1
                        foreground_color: 1, 1, 1, 1
                        padding: dp(8), dp(10)
                    Label:
                        text: '—'
                        color: 0.5, 0.5, 0.6, 1
                        size_hint_x: 0.05
                    TextInput:
                        id: inp_dmax
                        text: '25'
                        multiline: False
                        input_filter: 'int'
                        size_hint_x: 0.13
                        size_hint_y: None
                        height: dp(42)
                        font_size: sp(15)
                        halign: 'center'
                        background_normal: ''
                        background_color: 0.15, 0.15, 0.22, 1
                        foreground_color: 1, 1, 1, 1
                        padding: dp(8), dp(10)

                BoxLayout:
                    size_hint_y: None
                    height: dp(44)
                    Label:
                        text: 'Ответы на комменты:'
                        color: 0.7, 0.7, 0.8, 1
                        font_size: sp(13)
                        halign: 'left'
                        text_size: self.size
                        valign: 'center'
                    Switch:
                        id: sw_reply
                        active: False
                        size_hint_x: 0.3

                Widget:
                    size_hint_y: None
                    height: dp(6)

                # --- Start ---
                Button:
                    text: 'ЗАПУСТИТЬ'
                    font_size: sp(17)
                    bold: True
                    size_hint_y: None
                    height: dp(54)
                    background_normal: ''
                    background_color: 0.22, 0.47, 0.95, 1
                    color: 1, 1, 1, 1
                    on_release: app.start()

                Widget:
                    size_hint_y: None
                    height: dp(25)

    # ========== RUN SCREEN ==========
    Screen:
        name: 'run'
        canvas.before:
            Color:
                rgba: 0.07, 0.07, 0.10, 1
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            orientation: 'vertical'

            # Header
            BoxLayout:
                size_hint_y: None
                height: dp(54)
                padding: dp(4)
                canvas.before:
                    Color:
                        rgba: 0.09, 0.09, 0.13, 1
                    Rectangle:
                        pos: self.pos
                        size: self.size
                Button:
                    text: '<'
                    size_hint_x: None
                    width: dp(48)
                    font_size: sp(22)
                    background_normal: ''
                    background_color: 0, 0, 0, 0
                    color: 0.7, 0.8, 1, 1
                    on_release: app.go_back()
                Label:
                    text: app.run_title
                    font_size: sp(16)
                    bold: True
                    color: 1, 1, 1, 1
                    halign: 'left'
                    text_size: self.size
                    valign: 'center'

            # Stats
            BoxLayout:
                size_hint_y: None
                height: dp(75)
                padding: dp(10), dp(6)
                spacing: dp(8)

                BoxLayout:
                    orientation: 'vertical'
                    canvas.before:
                        Color:
                            rgba: 0.1, 0.12, 0.2, 1
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(12)]
                    Label:
                        text: str(app.sv)
                        font_size: sp(26)
                        bold: True
                        color: 0.45, 0.65, 1, 1
                    Label:
                        text: 'видео'
                        font_size: sp(10)
                        color: 0.4, 0.5, 0.6, 1

                BoxLayout:
                    orientation: 'vertical'
                    canvas.before:
                        Color:
                            rgba: 0.08, 0.16, 0.12, 1
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(12)]
                    Label:
                        text: str(app.sc)
                        font_size: sp(26)
                        bold: True
                        color: 0.4, 0.88, 0.55, 1
                    Label:
                        text: 'отправлено'
                        font_size: sp(10)
                        color: 0.35, 0.5, 0.4, 1

                BoxLayout:
                    orientation: 'vertical'
                    canvas.before:
                        Color:
                            rgba: 0.18, 0.1, 0.1, 1
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(12)]
                    Label:
                        text: str(app.se)
                        font_size: sp(26)
                        bold: True
                        color: 1, 0.45, 0.4, 1
                    Label:
                        text: 'ошибки'
                        font_size: sp(10)
                        color: 0.55, 0.35, 0.35, 1

            # Log
            ScrollView:
                id: lscr
                do_scroll_x: False
                bar_width: dp(2)
                bar_color: 0.3, 0.5, 0.9, 0.3

                Label:
                    text: app.log
                    font_size: sp(11)
                    color: 0.7, 0.72, 0.78, 1
                    size_hint_y: None
                    height: max(self.texture_size[1] + dp(20), lscr.height)
                    text_size: self.width - dp(24), None
                    halign: 'left'
                    valign: 'top'
                    padding: dp(12), dp(8)
                    markup: True

            # Buttons
            BoxLayout:
                size_hint_y: None
                height: dp(58)
                padding: dp(12), dp(6)
                spacing: dp(10)
                canvas.before:
                    Color:
                        rgba: 0.09, 0.09, 0.13, 1
                    Rectangle:
                        pos: self.pos
                        size: self.size

                Button:
                    id: bp
                    text: 'ПАУЗА'
                    font_size: sp(14)
                    bold: True
                    background_normal: ''
                    background_color: 0.7, 0.52, 0.12, 1
                    color: 1, 1, 1, 1
                    on_release: app.pause()

                Button:
                    text: 'СТОП'
                    font_size: sp(14)
                    bold: True
                    background_normal: ''
                    background_color: 0.8, 0.22, 0.22, 1
                    color: 1, 1, 1, 1
                    on_release: app.stop()

    # ========== HISTORY SCREEN ==========
    Screen:
        name: 'history'
        canvas.before:
            Color:
                rgba: 0.07, 0.07, 0.10, 1
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            orientation: 'vertical'

            BoxLayout:
                size_hint_y: None
                height: dp(54)
                padding: dp(4)
                canvas.before:
                    Color:
                        rgba: 0.09, 0.09, 0.13, 1
                    Rectangle:
                        pos: self.pos
                        size: self.size
                Button:
                    text: '<'
                    size_hint_x: None
                    width: dp(48)
                    font_size: sp(22)
                    background_normal: ''
                    background_color: 0, 0, 0, 0
                    color: 0.7, 0.8, 1, 1
                    on_release: app.close_history()
                Label:
                    text: 'История'
                    font_size: sp(17)
                    bold: True
                    color: 1, 1, 1, 1
                    halign: 'left'
                    text_size: self.size
                    valign: 'center'

            BoxLayout:
                size_hint_y: None
                height: dp(72)
                padding: dp(10), dp(6)
                spacing: dp(8)

                BoxLayout:
                    orientation: 'vertical'
                    canvas.before:
                        Color:
                            rgba: 0.1, 0.12, 0.2, 1
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(12)]
                    Label:
                        text: str(app.hist_total)
                        font_size: sp(22)
                        bold: True
                        color: 0.45, 0.65, 1, 1
                    Label:
                        text: 'всего'
                        font_size: sp(10)
                        color: 0.4, 0.5, 0.6, 1

                BoxLayout:
                    orientation: 'vertical'
                    canvas.before:
                        Color:
                            rgba: 0.08, 0.16, 0.12, 1
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(12)]
                    Label:
                        text: str(app.hist_ok)
                        font_size: sp(22)
                        bold: True
                        color: 0.4, 0.88, 0.55, 1
                    Label:
                        text: 'успешно'
                        font_size: sp(10)
                        color: 0.35, 0.5, 0.4, 1

                BoxLayout:
                    orientation: 'vertical'
                    canvas.before:
                        Color:
                            rgba: 0.18, 0.1, 0.1, 1
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(12)]
                    Label:
                        text: str(app.hist_fail)
                        font_size: sp(22)
                        bold: True
                        color: 1, 0.45, 0.4, 1
                    Label:
                        text: 'ошибок'
                        font_size: sp(10)
                        color: 0.55, 0.35, 0.35, 1

            ScrollView:
                id: hist_scroll
                do_scroll_x: False
                bar_width: dp(2)
                bar_color: 0.3, 0.5, 0.9, 0.3

                Label:
                    text: app.history_text
                    font_size: sp(11)
                    color: 0.7, 0.72, 0.78, 1
                    size_hint_y: None
                    height: max(self.texture_size[1] + dp(20), hist_scroll.height)
                    text_size: self.width - dp(24), None
                    halign: 'left'
                    valign: 'top'
                    padding: dp(12), dp(8)
                    markup: True

            BoxLayout:
                size_hint_y: None
                height: dp(58)
                padding: dp(12), dp(6)
                spacing: dp(10)
                canvas.before:
                    Color:
                        rgba: 0.09, 0.09, 0.13, 1
                    Rectangle:
                        pos: self.pos
                        size: self.size

                Button:
                    text: 'Обновить'
                    font_size: sp(14)
                    bold: True
                    background_normal: ''
                    background_color: 0.2, 0.35, 0.7, 1
                    color: 1, 1, 1, 1
                    on_release: app.refresh_history()

                Button:
                    text: 'Очистить'
                    font_size: sp(14)
                    bold: True
                    background_normal: ''
                    background_color: 0.6, 0.18, 0.18, 1
                    color: 1, 1, 1, 1
                    on_release: app.clear_history()
'''


class BotApp(App):
    status = StringProperty('Введи данные и нажми Запустить')
    log = StringProperty('')
    run_title = StringProperty('')
    sv = NumericProperty(0)
    sc = NumericProperty(0)
    se = NumericProperty(0)
    history_text = StringProperty('')
    hist_total = NumericProperty(0)
    hist_ok = NumericProperty(0)
    hist_fail = NumericProperty(0)

    def build(self):
        self.title = 'TikTok Bot'
        self.running = False
        self.is_paused = False
        self.login_mode = 'cookie'
        try:
            return Builder.load_string(KV)
        except Exception as e:
            print('UI Error: ' + str(e))
            return Builder.load_string('BoxLayout:\n Label:\n  text: "Error"')

    def switch_login(self, mode):
        try:
            self.login_mode = mode
            ids = self.root.ids
            if mode == 'cookie':
                Animation(height=dp(100), opacity=1, d=0.25).start(ids.cookie_box)
                Animation(height=0, opacity=0, d=0.25).start(ids.pass_box)
            else:
                Animation(height=0, opacity=0, d=0.25).start(ids.cookie_box)
                Animation(height=dp(110), opacity=1, d=0.25).start(ids.pass_box)
        except Exception: pass

    def show_history(self):
        try:
            self.refresh_history()
            self.root.ids.sm.current = 'history'
        except Exception: pass

    def close_history(self):
        try:
            self.root.ids.sm.current = 'login'
        except Exception: pass

    def refresh_history(self):
        try:
            self.history_text = format_history()
            t, o, f = get_stats()
            self.hist_total = t
            self.hist_ok = o
            self.hist_fail = f
        except Exception:
            self.history_text = 'Ошибка загрузки'

    def clear_history(self):
        try:
            save_history([])
            self.refresh_history()
        except Exception: pass

    def start(self):
        try:
            if requests is None:
                self.status = 'Нет библиотеки requests'
                return
            ids = self.root.ids
            kw = ids.inp_keyword.text.strip()
            c1 = ids.inp_c1.text.strip()
            if not kw:
                self.status = 'Введи поисковый запрос!'
                return
            if not c1:
                self.status = 'Введи хотя бы 1 комментарий!'
                return
            templates = [c1]
            for f in [ids.inp_c2, ids.inp_c3, ids.inp_c4]:
                t = f.text.strip()
                if t: templates.append(t)
            try: count = int(ids.inp_count.text)
            except: count = 30
            try: dmin = int(ids.inp_dmin.text)
            except: dmin = 10
            try: dmax = int(ids.inp_dmax.text)
            except: dmax = 25
            dmax = max(dmax, dmin + 2)
            cfg = {
                'mode': self.login_mode,
                'cookie': ids.inp_cookie.text.strip(),
                'email': ids.inp_email.text.strip(),
                'password': ids.inp_pass.text.strip(),
                'keyword': kw, 'templates': templates,
                'count': count, 'dmin': dmin, 'dmax': dmax,
                'reply': ids.sw_reply.active,
            }
            self.sv = 0; self.sc = 0; self.se = 0
            self.log = ''; self.running = True; self.is_paused = False
            self.run_title = kw
            Clock.schedule_once(lambda dt: self._go('run'), 0.1)
            threading.Thread(target=self._safe_run, args=(cfg,), daemon=True).start()
        except Exception as e:
            self.status = str(e)

    def _go(self, s):
        try: self.root.ids.sm.current = s
        except: pass

    def _safe_run(self, cfg):
        try: self._run(cfg)
        except Exception as e:
            self._log('[color=ff6666]Краш: ' + str(e) + '[/color]')
            self.running = False

    def _run(self, cfg):
        self._log('[color=7799ff]Проверяю интернет...[/color]')
        try:
            requests.get('https://www.google.com', timeout=10)
        except:
            self._log('[color=ff6666]Нет интернета![/color]')
            return

        bot = TikTok()
        self._log('[color=7799ff]Вхожу в аккаунт...[/color]')

        if cfg['mode'] == 'password':
            if not cfg['email'] or not cfg['password']:
                self._log('[color=ff6666]Введи email и пароль![/color]')
                return
            ok, msg = bot.login_password(cfg['email'], cfg['password'])
        else:
            if not cfg['cookie']:
                self._log('[color=ff6666]Вставь cookie![/color]')
                return
            ok, msg = bot.login_cookie(cfg['cookie'])

        if not ok:
            self._log('[color=ff6666]Ошибка: ' + str(msg) + '[/color]')
            return
        self._log('[color=66dd88]Вошёл: @' + str(msg) + '[/color]\n')

        self._log('[color=8899bb]Ищу видео...[/color]')
        videos = bot.search(cfg['keyword'], cfg['count'])
        if not videos:
            self._log('[color=ff6666]Видео не найдены[/color]')
            return
        self._log('[color=66dd88]Найдено: ' + str(len(videos)) + '[/color]\n')

        gen = CommentGen(cfg['templates'])
        for i, vid in enumerate(videos):
            if not self.running: break
            while self.is_paused and self.running: time.sleep(0.5)
            if not self.running: break

            text = gen.next()
            self._log('[color=7799ff][' + str(i+1) + '/' + str(len(videos)) + '][/color] ' + text)
            try:
                if cfg['reply']: ok, msg = bot.reply(vid, text)
                else: ok, msg = bot.comment(vid, text)
            except Exception as e:
                ok = False; msg = str(e)

            add_to_history(vid, text, ok, '' if ok else msg)
            if ok:
                self._upd('sc')
                self._log('[color=66dd88]  Отправлено[/color]')
            else:
                self._upd('se')
                self._log('[color=ff6666]  ' + str(msg) + '[/color]')
                if 'login' in str(msg).lower() or 'session' in str(msg).lower():
                    self._log('[color=ffbb44]Сессия истекла![/color]')
                    break
            self._upd('sv')
            if i < len(videos) - 1 and self.running:
                w = random.uniform(cfg['dmin'], cfg['dmax'])
                self._log('[color=8899bb]  Пауза ' + str(int(w)) + ' сек...[/color]\n')
                time.sleep(w)

        self._log('\n[color=7799ff]Готово![/color]')
        self.running = False

    def _log(self, msg):
        Clock.schedule_once(lambda dt: self._add(msg))
    def _add(self, msg):
        try:
            self.log += msg + '\n'
            Clock.schedule_once(lambda dt: setattr(self.root.ids.lscr, 'scroll_y', 0), 0.1)
        except: pass
    def _upd(self, a):
        Clock.schedule_once(lambda dt: setattr(self, a, getattr(self, a) + 1))

    def stop(self):
        self.running = False
        self._log('[color=ff6666]Остановлено[/color]')
    def pause(self):
        self.is_paused = not self.is_paused
        try: self.root.ids.bp.text = 'ДАЛЬШЕ' if self.is_paused else 'ПАУЗА'
        except: pass
        self._log('[color=ffbb44]Пауза[/color]' if self.is_paused else '[color=66dd88]Продолжаю[/color]')
    def go_back(self):
        self.running = False
        Clock.schedule_once(lambda dt: self._go('login'), 0.1)


if __name__ == '__main__':
    try: BotApp().run()
    except Exception as e: print('FATAL: ' + str(e))
