"""
TikTok Auto Commenter v3.2
+ History checker
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


# ═══════════════════════════════════════
#  HISTORY SAVER
# ═══════════════════════════════════════

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


def save_history(history):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def add_to_history(video_id, comment_text, status, error_msg=''):
    try:
        h = load_history()
        h.append({
            'time': datetime.now().strftime('%d.%m %H:%M:%S'),
            'video': video_id,
            'text': comment_text,
            'ok': status,
            'error': error_msg,
        })
        # max 500 records
        if len(h) > 500:
            h = h[-500:]
        save_history(h)
    except Exception:
        pass


def format_history():
    h = load_history()
    if not h:
        return '[color=8899bb]Istoriya pusta[/color]'

    lines = []
    for item in reversed(h):
        t = item.get('time', '?')
        vid = item.get('video', '?')
        txt = item.get('text', '?')
        ok = item.get('ok', False)
        err = item.get('error', '')

        if ok:
            status = '[color=66dd88]OK[/color]'
        else:
            status = '[color=ff6666]' + (err if err else 'FAIL') + '[/color]'

        short_vid = vid[:8] + '...' + vid[-4:] if len(vid) > 14 else vid

        lines.append(
            '[color=8899bb]' + t + '[/color]  ' + status + '\n'
            '[color=aabbdd]video: ' + short_vid + '[/color]\n'
            '[color=ffffff]' + txt + '[/color]\n'
        )

    return '\n'.join(lines)


def get_stats():
    h = load_history()
    total = len(h)
    ok_count = sum(1 for x in h if x.get('ok'))
    fail_count = total - ok_count
    return total, ok_count, fail_count


# ═══════════════════════════════════════
#  COMMENT GENERATOR
# ═══════════════════════════════════════

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
        if not pp:
            return t
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
        if len(t) < 3:
            return t
        i = random.randint(1, len(t) - 2)
        return t[:i] + t[i] + t[i:] if t[i].isalpha() else t


# ═══════════════════════════════════════
#  TIKTOK API
# ═══════════════════════════════════════

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

    def login_cookie(self, session_id):
        self.sid = session_id.strip()
        self.s.cookies.set('sessionid', self.sid, domain='.tiktok.com', path='/')
        self.s.headers.update({
            'User-Agent': self.UA, 'Accept': 'text/html',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        try:
            r = self.s.get('https://www.tiktok.com/', timeout=30)
            self._tokens(r)
            m = re.search(r'"uniqueId":"([^"]+)"', r.text)
            if m:
                self.username = m.group(1)
                return True, self.username
            if len(r.text) > 50000:
                self.username = 'ok'
                return True, self.username
            return False, 'Cookie nevalidn'
        except requests.exceptions.ConnectionError:
            return False, 'Net interneta'
        except requests.exceptions.Timeout:
            return False, 'Timeout'
        except Exception as e:
            return False, str(e)

    def login_password(self, email, password):
        pwd = hashlib.md5(password.encode()).hexdigest()
        did = str(random.randint(7000000000000000000, 7999999999999999999))
        iid = str(random.randint(7000000000000000000, 7999999999999999999))
        params = {
            'aid': '1233', 'device_id': did, 'iid': iid,
            'os_api': '28', 'device_type': 'SM-S928B',
            'device_brand': 'samsung', 'os_version': '14',
            'app_name': 'musical_ly', 'version_code': '2023501030',
            'channel': 'googleplay', 'language': 'en',
        }
        data = {
            'mix_mode': '1', 'email': email,
            'password': pwd, 'username': '', 'mobile': '',
        }
        self.s.headers.update({
            'User-Agent': 'com.zhiliaoapp.musically/2023501030 TTNet/3.1.0',
            'Content-Type': 'application/x-www-form-urlencoded',
        })
        try:
            r = self.s.post(
                'https://api22-normal-c-useast2a.tiktokv.com/passport/user/login/',
                params=params, data=data, timeout=30,
            )
            j = r.json()
            if j.get('error_code', -1) == 0 or j.get('message') == 'success':
                d = j.get('data', {})
                self.sid = d.get('session_key', '')
                for c in r.cookies:
                    if c.name == 'sessionid':
                        self.sid = c.value
                self.username = d.get('username', '')
                self.s.cookies.set('sessionid', self.sid, domain='.tiktok.com', path='/')
                self.s.headers['User-Agent'] = self.UA
                return True, self.username
            msg = j.get('data', {}).get('description', j.get('message', '?'))
            return False, str(msg)
        except requests.exceptions.ConnectionError:
            return False, 'Net interneta'
        except Exception as e:
            return False, str(e)

    def _tokens(self, r):
        try:
            for c in self.s.cookies:
                if c.name == 'tt_csrf_token':
                    self.csrf = c.value
                elif c.name == 'msToken':
                    self.ms = c.value
        except Exception:
            pass

    def search(self, keyword, count=30):
        ids = []
        try:
            self.s.headers['Accept'] = 'text/html'
            self.s.headers['Referer'] = 'https://www.tiktok.com/'
            r = self.s.get(
                'https://www.tiktok.com/search/video?q=' + quote(keyword),
                timeout=30,
            )
            self._tokens(r)
            for m in re.finditer(r'(?:video/|"id":"|"aweme_id":")\s*(\d{15,25})', r.text):
                ids.append(m.group(1))
        except Exception:
            pass
        seen = set()
        unique = []
        for v in ids:
            if v not in seen:
                seen.add(v)
                unique.append(v)
        return unique[:count]

    def comment(self, video_id, text):
        try:
            self.s.headers['Accept'] = 'text/html'
            self.s.headers['Referer'] = 'https://www.tiktok.com/'
            r = self.s.get('https://www.tiktok.com/video/' + video_id, timeout=20)
            self._tokens(r)
            time.sleep(random.uniform(0.5, 1.5))
            self.s.headers.update({
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': 'https://www.tiktok.com/video/' + video_id,
                'Origin': 'https://www.tiktok.com',
            })
            if self.csrf:
                self.s.headers['X-CSRFToken'] = self.csrf
            params = {'aid': '1988'}
            if self.ms:
                params['msToken'] = self.ms
            r = self.s.post(
                'https://www.tiktok.com/api/comment/publish/',
                params=params,
                data={
                    'aweme_id': video_id, 'text': text,
                    'text_extra': '[]', 'is_self_see': '0',
                },
                timeout=20,
            )
            if r.status_code == 200:
                j = r.json()
                if j.get('status_code') == 0:
                    return True, 'OK'
                return False, j.get('status_msg', '?')
            return False, 'HTTP ' + str(r.status_code)
        except Exception as e:
            return False, str(e)

    def reply(self, video_id, text):
        try:
            self.s.headers['Accept'] = 'application/json'
            self.s.headers['Referer'] = 'https://www.tiktok.com/video/' + video_id
            r = self.s.get(
                'https://www.tiktok.com/api/comment/list/',
                params={'aid': '1988', 'aweme_id': video_id, 'count': '5', 'cursor': '0'},
                timeout=20,
            )
            cid = ''
            if r.status_code == 200:
                cc = r.json().get('comments', [])
                if cc:
                    cid = str(cc[0].get('cid', ''))
            if not cid:
                return self.comment(video_id, text)
            time.sleep(random.uniform(0.5, 1.5))
            self.s.headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://www.tiktok.com',
            })
            if self.csrf:
                self.s.headers['X-CSRFToken'] = self.csrf
            r = self.s.post(
                'https://www.tiktok.com/api/comment/publish/',
                params={'aid': '1988'},
                data={
                    'aweme_id': video_id, 'text': text,
                    'reply_id': cid, 'text_extra': '[]', 'is_self_see': '0',
                },
                timeout=20,
            )
            if r.status_code == 200:
                j = r.json()
                if j.get('status_code') == 0:
                    return True, 'OK'
                return False, j.get('status_msg', '?')
            return False, 'HTTP ' + str(r.status_code)
        except Exception as e:
            return False, str(e)


# ═══════════════════════════════════════
#  UI
# ═══════════════════════════════════════

KV = '''
#:import dp kivy.metrics.dp
#:import sp kivy.metrics.sp
#:import Animation kivy.animation.Animation

<SoftCard@BoxLayout>:
    orientation: 'vertical'
    padding: dp(16)
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: 0.11, 0.11, 0.16, 0.95
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(16)]

<SoftInput@TextInput>:
    multiline: False
    size_hint_y: None
    height: dp(48)
    font_size: sp(14)
    background_normal: ''
    background_active: ''
    background_color: 0, 0, 0, 0
    foreground_color: 0.93, 0.93, 0.96, 1
    hint_text_color: 0.35, 0.35, 0.45, 1
    cursor_color: 0.45, 0.65, 1, 1
    padding: dp(16), dp(14), dp(16), dp(14)
    canvas.before:
        Color:
            rgba: 0.14, 0.14, 0.21, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]
    canvas.after:
        Color:
            rgba: (0.35, 0.55, 0.95, 0.6) if self.focus else (0.2, 0.2, 0.3, 0.4)
        Line:
            rounded_rectangle: [self.x, self.y, self.width, self.height, dp(12)]
            width: dp(1.5) if self.focus else dp(1)

<GlowButton@Button>:
    font_size: sp(16)
    bold: True
    size_hint_y: None
    height: dp(52)
    background_normal: ''
    background_down: ''
    color: 1, 1, 1, 1
    bg_color: 0.25, 0.5, 0.95, 1
    canvas.before:
        Color:
            rgba: self.bg_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]

<SmallButton@Button>:
    font_size: sp(13)
    size_hint_y: None
    height: dp(44)
    background_normal: ''
    background_down: ''
    color: 1, 1, 1, 1
    bg_color: 0.14, 0.14, 0.21, 1
    canvas.before:
        Color:
            rgba: self.bg_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]

<SoftToggle@ToggleButton>:
    font_size: sp(13)
    background_normal: ''
    background_down: ''
    color: 1, 1, 1, 1
    size_hint_y: None
    height: dp(42)
    canvas.before:
        Color:
            rgba: (0.25, 0.45, 0.85, 1) if self.state == 'down' else (0.14, 0.14, 0.21, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(11)]

<StatCard@BoxLayout>:
    orientation: 'vertical'
    padding: dp(8)
    bg: 0.11, 0.13, 0.19, 1
    canvas.before:
        Color:
            rgba: self.bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]

<SectionLabel@Label>:
    font_size: sp(11)
    bold: True
    size_hint_y: None
    height: dp(28)
    halign: 'left'
    text_size: self.size
    valign: 'center'
    color: 0.45, 0.65, 1, 0.9

ScreenManager:
    id: sm

    # ═══ LOGIN SCREEN ═══
    Screen:
        name: 'login'
        canvas.before:
            Color:
                rgba: 0.055, 0.055, 0.08, 1
            Rectangle:
                pos: self.pos
                size: self.size

        ScrollView:
            do_scroll_x: False
            bar_width: dp(0)
            BoxLayout:
                orientation: 'vertical'
                padding: dp(20), dp(16)
                spacing: dp(12)
                size_hint_y: None
                height: self.minimum_height

                Widget:
                    size_hint_y: None
                    height: dp(10)

                BoxLayout:
                    size_hint_y: None
                    height: dp(60)
                    spacing: dp(10)
                    padding: dp(4)
                    Label:
                        text: 'TikTok'
                        font_size: sp(30)
                        bold: True
                        color: 0.95, 0.95, 0.98, 1
                        halign: 'right'
                        text_size: self.size
                        valign: 'center'
                    Label:
                        text: 'Bot'
                        font_size: sp(30)
                        bold: True
                        color: 0.35, 0.6, 1, 1
                        halign: 'left'
                        text_size: self.size
                        valign: 'center'

                Label:
                    id: status_label
                    text: app.status
                    font_size: sp(12)
                    size_hint_y: None
                    height: dp(24)
                    color: 0.5, 0.7, 0.9, 0.8
                    halign: 'center'
                    text_size: self.size

                # History button
                SmallButton:
                    text: 'ISTORIYA KOMMENTARIEV'
                    bg_color: 0.12, 0.15, 0.25, 1
                    on_release: app.show_history()

                Widget:
                    size_hint_y: None
                    height: dp(4)

                SoftCard:
                    size_hint_y: None
                    height: self.minimum_height
                    SectionLabel:
                        text: 'SPOSOB VHODA'
                    BoxLayout:
                        size_hint_y: None
                        height: dp(42)
                        spacing: dp(8)
                        SoftToggle:
                            id: btn_cookie
                            text: 'Cookie'
                            group: 'login'
                            state: 'down'
                            on_state: app.switch_login('cookie')
                        SoftToggle:
                            id: btn_pass
                            text: 'Email + Parol'
                            group: 'login'
                            on_state: app.switch_login('password')
                    BoxLayout:
                        id: cookie_box
                        orientation: 'vertical'
                        size_hint_y: None
                        height: dp(95)
                        opacity: 1
                        spacing: dp(6)
                        Label:
                            text: 'Chrome > tiktok.com > vojdi >\\njavascript:prompt("c",document.cookie)\\nsessionid=XXX kopiruesh XXX'
                            font_size: sp(9)
                            color: 0.4, 0.4, 0.5, 0.7
                            size_hint_y: None
                            height: dp(40)
                            halign: 'left'
                            text_size: self.size
                        SoftInput:
                            id: inp_cookie
                            hint_text: 'Vstav sessionid'
                    BoxLayout:
                        id: pass_box
                        orientation: 'vertical'
                        size_hint_y: None
                        height: dp(0)
                        opacity: 0
                        spacing: dp(6)
                        SoftInput:
                            id: inp_email
                            hint_text: 'Email'
                        SoftInput:
                            id: inp_pass
                            hint_text: 'Parol'
                            password: True

                SoftCard:
                    size_hint_y: None
                    height: self.minimum_height
                    SectionLabel:
                        text: 'POISKOVIY ZAPROS'
                    SoftInput:
                        id: inp_keyword
                        hint_text: 'Naprimer: tg yuzy'

                SoftCard:
                    size_hint_y: None
                    height: self.minimum_height
                    SectionLabel:
                        text: 'KOMMENTARII'
                    Label:
                        text: 'Bot chereiduet i delaet unikalnym'
                        font_size: sp(10)
                        color: 0.4, 0.4, 0.5, 0.6
                        size_hint_y: None
                        height: dp(18)
                        halign: 'left'
                        text_size: self.size
                    SoftInput:
                        id: inp_c1
                        hint_text: 'Variant 1 (obyazatelno)'
                    SoftInput:
                        id: inp_c2
                        hint_text: 'Variant 2'
                    SoftInput:
                        id: inp_c3
                        hint_text: 'Variant 3'
                    SoftInput:
                        id: inp_c4
                        hint_text: 'Variant 4'

                SoftCard:
                    size_hint_y: None
                    height: self.minimum_height
                    SectionLabel:
                        text: 'NASTROYKI'
                    BoxLayout:
                        size_hint_y: None
                        height: dp(44)
                        spacing: dp(10)
                        Label:
                            text: 'Kol-vo video'
                            color: 0.7, 0.7, 0.78, 1
                            font_size: sp(13)
                            halign: 'left'
                            text_size: self.size
                            valign: 'center'
                        SoftInput:
                            id: inp_count
                            text: '30'
                            input_filter: 'int'
                            size_hint_x: 0.25
                            halign: 'center'
                            height: dp(42)
                    BoxLayout:
                        size_hint_y: None
                        height: dp(44)
                        spacing: dp(8)
                        Label:
                            text: 'Pauza (sek)'
                            color: 0.7, 0.7, 0.78, 1
                            font_size: sp(13)
                            halign: 'left'
                            text_size: self.size
                            valign: 'center'
                        SoftInput:
                            id: inp_dmin
                            text: '10'
                            input_filter: 'int'
                            size_hint_x: 0.15
                            halign: 'center'
                            height: dp(42)
                        Label:
                            text: '-'
                            color: 0.4, 0.4, 0.5, 1
                            size_hint_x: 0.05
                        SoftInput:
                            id: inp_dmax
                            text: '25'
                            input_filter: 'int'
                            size_hint_x: 0.15
                            halign: 'center'
                            height: dp(42)
                    BoxLayout:
                        size_hint_y: None
                        height: dp(44)
                        Label:
                            text: 'Otvety na kommenty'
                            color: 0.7, 0.7, 0.78, 1
                            font_size: sp(13)
                            halign: 'left'
                            text_size: self.size
                            valign: 'center'
                        Switch:
                            id: sw_reply
                            active: False
                            size_hint_x: 0.3

                GlowButton:
                    text: 'ZAPUSTIT'
                    on_release: app.start()

                Widget:
                    size_hint_y: None
                    height: dp(20)

    # ═══ RUN SCREEN ═══
    Screen:
        name: 'run'
        canvas.before:
            Color:
                rgba: 0.055, 0.055, 0.08, 1
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            orientation: 'vertical'

            BoxLayout:
                size_hint_y: None
                height: dp(56)
                padding: dp(4)
                spacing: dp(4)
                canvas.before:
                    Color:
                        rgba: 0.08, 0.08, 0.12, 0.95
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
                    font_size: sp(17)
                    bold: True
                    color: 0.93, 0.93, 0.97, 1
                    halign: 'left'
                    text_size: self.size
                    valign: 'center'

            Widget:
                size_hint_y: None
                height: dp(8)

            BoxLayout:
                size_hint_y: None
                height: dp(80)
                padding: dp(12), 0
                spacing: dp(10)
                StatCard:
                    bg: 0.1, 0.12, 0.2, 0.9
                    Label:
                        id: anim_sv
                        text: str(app.sv)
                        font_size: sp(28)
                        bold: True
                        color: 0.4, 0.65, 1, 1
                    Label:
                        text: 'video'
                        font_size: sp(10)
                        color: 0.4, 0.45, 0.6, 0.7
                StatCard:
                    bg: 0.08, 0.16, 0.12, 0.9
                    Label:
                        id: anim_sc
                        text: str(app.sc)
                        font_size: sp(28)
                        bold: True
                        color: 0.35, 0.85, 0.5, 1
                    Label:
                        text: 'otpravleno'
                        font_size: sp(10)
                        color: 0.35, 0.5, 0.4, 0.7
                StatCard:
                    bg: 0.18, 0.1, 0.1, 0.9
                    Label:
                        id: anim_se
                        text: str(app.se)
                        font_size: sp(28)
                        bold: True
                        color: 1, 0.45, 0.4, 1
                    Label:
                        text: 'oshibki'
                        font_size: sp(10)
                        color: 0.55, 0.35, 0.35, 0.7

            Widget:
                size_hint_y: None
                height: dp(6)

            SoftCard:
                padding: dp(10)
                ScrollView:
                    id: lscr
                    do_scroll_x: False
                    bar_width: dp(2)
                    bar_color: 0.3, 0.5, 0.9, 0.3
                    Label:
                        id: lbl
                        text: app.log
                        font_size: sp(11)
                        color: 0.65, 0.67, 0.73, 1
                        size_hint_y: None
                        height: max(self.texture_size[1] + dp(20), lscr.height)
                        text_size: self.width - dp(16), None
                        halign: 'left'
                        valign: 'top'
                        padding: dp(6), dp(4)
                        markup: True

            BoxLayout:
                size_hint_y: None
                height: dp(62)
                padding: dp(14), dp(8)
                spacing: dp(10)
                GlowButton:
                    id: bp
                    text: 'PAUZA'
                    bg_color: 0.65, 0.48, 0.12, 1
                    on_release: app.pause()
                GlowButton:
                    text: 'STOP'
                    bg_color: 0.75, 0.22, 0.22, 1
                    on_release: app.stop()

    # ═══ HISTORY SCREEN ═══
    Screen:
        name: 'history'
        canvas.before:
            Color:
                rgba: 0.055, 0.055, 0.08, 1
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            orientation: 'vertical'

            # Header
            BoxLayout:
                size_hint_y: None
                height: dp(56)
                padding: dp(4)
                spacing: dp(4)
                canvas.before:
                    Color:
                        rgba: 0.08, 0.08, 0.12, 0.95
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
                    text: 'Istoriya'
                    font_size: sp(18)
                    bold: True
                    color: 0.93, 0.93, 0.97, 1
                    halign: 'left'
                    text_size: self.size
                    valign: 'center'

            Widget:
                size_hint_y: None
                height: dp(8)

            # Total stats
            BoxLayout:
                size_hint_y: None
                height: dp(70)
                padding: dp(12), 0
                spacing: dp(10)

                StatCard:
                    bg: 0.1, 0.12, 0.2, 0.9
                    Label:
                        id: hist_total
                        text: str(app.hist_total)
                        font_size: sp(24)
                        bold: True
                        color: 0.4, 0.65, 1, 1
                    Label:
                        text: 'vsego'
                        font_size: sp(10)
                        color: 0.4, 0.45, 0.6, 0.7

                StatCard:
                    bg: 0.08, 0.16, 0.12, 0.9
                    Label:
                        id: hist_ok
                        text: str(app.hist_ok)
                        font_size: sp(24)
                        bold: True
                        color: 0.35, 0.85, 0.5, 1
                    Label:
                        text: 'uspeshno'
                        font_size: sp(10)
                        color: 0.35, 0.5, 0.4, 0.7

                StatCard:
                    bg: 0.18, 0.1, 0.1, 0.9
                    Label:
                        id: hist_fail
                        text: str(app.hist_fail)
                        font_size: sp(24)
                        bold: True
                        color: 1, 0.45, 0.4, 1
                    Label:
                        text: 'oshibok'
                        font_size: sp(10)
                        color: 0.55, 0.35, 0.35, 0.7

            Widget:
                size_hint_y: None
                height: dp(6)

            # History list
            SoftCard:
                padding: dp(10)
                ScrollView:
                    id: hist_scroll
                    do_scroll_x: False
                    bar_width: dp(2)
                    bar_color: 0.3, 0.5, 0.9, 0.3
                    Label:
                        id: hist_label
                        text: app.history_text
                        font_size: sp(11)
                        color: 0.65, 0.67, 0.73, 1
                        size_hint_y: None
                        height: max(self.texture_size[1] + dp(20), hist_scroll.height)
                        text_size: self.width - dp(16), None
                        halign: 'left'
                        valign: 'top'
                        padding: dp(6), dp(4)
                        markup: True

            # Clear button
            BoxLayout:
                size_hint_y: None
                height: dp(62)
                padding: dp(14), dp(8)
                spacing: dp(10)

                GlowButton:
                    text: 'OBNOVIT'
                    bg_color: 0.2, 0.35, 0.7, 1
                    on_release: app.refresh_history()

                GlowButton:
                    text: 'OCHISTIT'
                    bg_color: 0.6, 0.18, 0.18, 1
                    on_release: app.clear_history()
'''


# ═══════════════════════════════════════
#  APP
# ═══════════════════════════════════════

class BotApp(App):
    status = StringProperty('Vvedi dannye i nazmi Zapustit')
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
            root = Builder.load_string(KV)
            return root
        except Exception as e:
            print('UI Error: ' + str(e))
            return Builder.load_string(
                'BoxLayout:\n Label:\n  text: "UI Error"'
            )

    def switch_login(self, mode):
        try:
            self.login_mode = mode
            ids = self.root.ids
            if mode == 'cookie':
                Animation(height=dp(95), opacity=1, d=0.3).start(ids.cookie_box)
                Animation(height=0, opacity=0, d=0.3).start(ids.pass_box)
            else:
                Animation(height=0, opacity=0, d=0.3).start(ids.cookie_box)
                Animation(height=dp(110), opacity=1, d=0.3).start(ids.pass_box)
        except Exception:
            pass

    # ── History ──

    def show_history(self):
        try:
            self.refresh_history()
            self.root.ids.sm.current = 'history'
        except Exception:
            pass

    def close_history(self):
        try:
            self.root.ids.sm.current = 'login'
        except Exception:
            pass

    def refresh_history(self):
        try:
            self.history_text = format_history()
            t, o, f = get_stats()
            self.hist_total = t
            self.hist_ok = o
            self.hist_fail = f
        except Exception:
            self.history_text = 'Oshibka zagruzki'

    def clear_history(self):
        try:
            save_history([])
            self.refresh_history()
        except Exception:
            pass

    # ── Start/Stop ──

    def start(self):
        try:
            if requests is None:
                self.status = 'Net biblioteki requests'
                return

            ids = self.root.ids
            kw = ids.inp_keyword.text.strip()
            c1 = ids.inp_c1.text.strip()

            if not kw:
                self.status = 'Vvedi poiskoviy zapros!'
                return
            if not c1:
                self.status = 'Vvedi hotya by 1 komment!'
                return

            templates = [c1]
            for f in [ids.inp_c2, ids.inp_c3, ids.inp_c4]:
                t = f.text.strip()
                if t:
                    templates.append(t)

            try:
                count = int(ids.inp_count.text)
            except Exception:
                count = 30
            try:
                dmin = int(ids.inp_dmin.text)
            except Exception:
                dmin = 10
            try:
                dmax = int(ids.inp_dmax.text)
            except Exception:
                dmax = 25
            dmax = max(dmax, dmin + 2)

            cfg = {
                'mode': self.login_mode,
                'cookie': ids.inp_cookie.text.strip(),
                'email': ids.inp_email.text.strip(),
                'password': ids.inp_pass.text.strip(),
                'keyword': kw,
                'templates': templates,
                'count': count,
                'dmin': dmin,
                'dmax': dmax,
                'reply': ids.sw_reply.active,
            }

            self.sv = 0
            self.sc = 0
            self.se = 0
            self.log = ''
            self.running = True
            self.is_paused = False
            self.run_title = kw

            Clock.schedule_once(lambda dt: self._go_run(), 0.1)
            threading.Thread(target=self._run_safe, args=(cfg,), daemon=True).start()

        except Exception as e:
            self.status = 'Oshibka: ' + str(e)

    def _go_run(self):
        try:
            self.root.ids.sm.current = 'run'
        except Exception:
            pass

    def _run_safe(self, cfg):
        try:
            self._run(cfg)
        except Exception as e:
            self._log('[color=ff6666]Crash: ' + str(e) + '[/color]')
            self.running = False

    def _run(self, cfg):
        self._log('[color=7799ff]Proveryayu internet...[/color]')
        try:
            requests.get('https://www.google.com', timeout=10)
        except Exception:
            self._log('[color=ff6666]Net interneta![/color]')
            return

        bot = TikTok()
        self._log('[color=7799ff]Vhozhu v akkaunt...[/color]')

        if cfg['mode'] == 'password':
            if not cfg['email'] or not cfg['password']:
                self._log('[color=ff6666]Vvedi email i parol![/color]')
                return
            ok, msg = bot.login_password(cfg['email'], cfg['password'])
        else:
            if not cfg['cookie']:
                self._log('[color=ff6666]Vstav cookie![/color]')
                return
            ok, msg = bot.login_cookie(cfg['cookie'])

        if not ok:
            self._log('[color=ff6666]Oshibka vhoda: ' + str(msg) + '[/color]')
            return
        self._log('[color=66dd88]Voshel: @' + str(msg) + '[/color]\n')

        self._log('[color=8899bb]Ishu video...[/color]')
        videos = bot.search(cfg['keyword'], cfg['count'])
        if not videos:
            self._log('[color=ff6666]Video ne naydeny[/color]')
            return
        self._log('[color=66dd88]Naydeno: ' + str(len(videos)) + '[/color]\n')

        gen = CommentGen(cfg['templates'])

        for i, vid in enumerate(videos):
            if not self.running:
                break
            while self.is_paused and self.running:
                time.sleep(0.5)
            if not self.running:
                break

            text = gen.next()
            self._log(
                '[color=7799ff][' + str(i + 1) + '/' +
                str(len(videos)) + '][/color]  ' + text
            )

            try:
                if cfg['reply']:
                    ok, msg = bot.reply(vid, text)
                else:
                    ok, msg = bot.comment(vid, text)
            except Exception as e:
                ok = False
                msg = str(e)

            # save to history
            add_to_history(vid, text, ok, '' if ok else msg)

            if ok:
                self._upd('sc')
                self._log('[color=66dd88]   OK[/color]')
            else:
                self._upd('se')
                self._log('[color=ff6666]   ' + str(msg) + '[/color]')
                if 'login' in str(msg).lower() or 'session' in str(msg).lower():
                    self._log('[color=ffbb44]Sessiya istekla[/color]')
                    break

            self._upd('sv')

            if i < len(videos) - 1 and self.running:
                w = random.uniform(cfg['dmin'], cfg['dmax'])
                self._log('[color=8899bb]   ' + str(int(w)) + 's...[/color]\n')
                time.sleep(w)

        self._log('\n[color=7799ff]Gotovo![/color]')
        self.running = False

    def _log(self, msg):
        Clock.schedule_once(lambda dt: self._add_log(msg))

    def _add_log(self, msg):
        try:
            self.log += msg + '\n'
            Clock.schedule_once(lambda dt: self._do_scroll(), 0.1)
        except Exception:
            pass

    def _do_scroll(self):
        try:
            self.root.ids.lscr.scroll_y = 0
        except Exception:
            pass

    def _upd(self, attr):
        def do(dt):
            try:
                setattr(self, attr, getattr(self, attr) + 1)
            except Exception:
                pass
        Clock.schedule_once(do)

    def stop(self):
        self.running = False
        self._log('[color=ff6666]Ostanovleno[/color]')

    def pause(self):
        self.is_paused = not self.is_paused
        try:
            self.root.ids.bp.text = 'DALSHE' if self.is_paused else 'PAUZA'
        except Exception:
            pass
        if self.is_paused:
            self._log('[color=ffbb44]Pauza[/color]')
        else:
            self._log('[color=66dd88]Prodolzhayu[/color]')

    def go_back(self):
        self.running = False
        try:
            Clock.schedule_once(
                lambda dt: setattr(self.root.ids.sm, 'current', 'login'), 0.1
            )
        except Exception:
            pass


if __name__ == '__main__':
    try:
        BotApp().run()
    except Exception as e:
        print('FATAL: ' + str(e))
