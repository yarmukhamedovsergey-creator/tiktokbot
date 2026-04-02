"""
TikTok Auto Commenter v3 — Android App
"""

import os
import json
import time
import random
import hashlib
import re
import threading
from urllib.parse import quote

import requests

from kivy.app import App
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.properties import StringProperty, NumericProperty
from kivy.utils import platform

if platform == 'android':
    try:
        from android.permissions import request_permissions, Permission
        request_permissions([Permission.INTERNET])
    except:
        pass

EMOJIS = [
    '\U0001f525','\U0001f4af','\U0001f44d','\u2728','\U0001f4aa',
    '\U0001f64c','\u2764\ufe0f','\U0001f60a','\U0001f440','\U0001f3af',
    '\u2b50','\U0001f31f','\U0001f4ab','\U0001f389','\U0001f919',
    '\U0001f44f','\U0001f4a5','\U0001f680','\U0001f48e','\U0001f3c6',
    '\U0001f60e','\U0001f91e','\u2705','\U0001f51d','\U0001fae1',
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
            'User-Agent': self.UA,
            'Accept': 'text/html',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        try:
            r = self.s.get('https://www.tiktok.com/', timeout=20)
            self._tokens(r)
            m = re.search(r'"uniqueId":"([^"]+)"', r.text)
            if m:
                self.username = m.group(1)
                return True, self.username
            if len(r.text) > 50000:
                self.username = 'ok'
                return True, self.username
            return False, 'Cookie bad'
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
            'User-Agent': 'com.zhiliaoapp.musically/2023501030 (Linux; U; Android 14; en_US; SM-S928B) TTNet/3.1.0',
            'Content-Type': 'application/x-www-form-urlencoded',
        })
        try:
            r = self.s.post(
                'https://api22-normal-c-useast2a.tiktokv.com/passport/user/login/',
                params=params, data=data, timeout=20,
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
            return False, msg
        except Exception as e:
            return False, str(e)

    def _tokens(self, r):
        for c in self.s.cookies:
            if c.name == 'tt_csrf_token':
                self.csrf = c.value
            elif c.name == 'msToken':
                self.ms = c.value

    def search(self, keyword, count=30):
        ids = []
        try:
            self.s.headers['Accept'] = 'text/html'
            self.s.headers['Referer'] = 'https://www.tiktok.com/'
            r = self.s.get(
                'https://www.tiktok.com/search/video?q=' + quote(keyword),
                timeout=20,
            )
            self._tokens(r)
            for m in re.finditer(r'(?:video/|"id":"|"aweme_id":")\s*(\d{15,25})', r.text):
                ids.append(m.group(1))
        except:
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
            r = self.s.get('https://www.tiktok.com/video/' + video_id, timeout=15)
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
                timeout=15,
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
                timeout=15,
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
                timeout=15,
            )
            if r.status_code == 200:
                j = r.json()
                if j.get('status_code') == 0:
                    return True, 'OK'
                return False, j.get('status_msg', '?')
            return False, 'HTTP ' + str(r.status_code)
        except Exception as e:
            return False, str(e)


KV = '''
#:import dp kivy.metrics.dp
#:import sp kivy.metrics.sp

ScreenManager:
    id: sm

    Screen:
        name: 'login'
        canvas.before:
            Color:
                rgba: 0.06, 0.06, 0.09, 1
            Rectangle:
                pos: self.pos
                size: self.size
        ScrollView:
            do_scroll_x: False
            BoxLayout:
                orientation: 'vertical'
                padding: dp(20)
                spacing: dp(8)
                size_hint_y: None
                height: self.minimum_height

                Label:
                    text: 'TikTok Bot'
                    font_size: sp(28)
                    bold: True
                    size_hint_y: None
                    height: dp(50)
                    color: 1,1,1,1

                Label:
                    text: app.status
                    font_size: sp(13)
                    size_hint_y: None
                    height: dp(30)
                    color: 0.5,0.8,1,1

                Label:
                    text: 'СПОСОБ ВХОДА'
                    font_size: sp(12)
                    color: 0.4,0.7,1,1
                    size_hint_y: None
                    height: dp(25)
                    halign: 'left'
                    text_size: self.size
                    bold: True

                BoxLayout:
                    size_hint_y: None
                    height: dp(42)
                    spacing: dp(6)
                    ToggleButton:
                        id: btn_cookie
                        text: 'Cookie'
                        group: 'login'
                        state: 'down'
                        font_size: sp(13)
                        background_normal: ''
                        background_color: (0.2,0.4,0.8,1) if self.state=='down' else (0.15,0.15,0.22,1)
                        on_state: app.switch_login('cookie')
                    ToggleButton:
                        id: btn_pass
                        text: 'Email + Пароль'
                        group: 'login'
                        font_size: sp(13)
                        background_normal: ''
                        background_color: (0.2,0.4,0.8,1) if self.state=='down' else (0.15,0.15,0.22,1)
                        on_state: app.switch_login('password')

                BoxLayout:
                    id: cookie_box
                    orientation: 'vertical'
                    size_hint_y: None
                    height: dp(100)
                    spacing: dp(4)
                    Label:
                        text: 'Chrome > tiktok.com > войди > адресная строка:\\njavascript:prompt("c",document.cookie)\\nнайди sessionid=XXX скопируй XXX'
                        font_size: sp(9)
                        color: 0.4,0.4,0.5,1
                        size_hint_y: None
                        height: dp(45)
                        halign: 'left'
                        text_size: self.size
                    TextInput:
                        id: inp_cookie
                        hint_text: 'Вставь sessionid'
                        multiline: False
                        size_hint_y: None
                        height: dp(44)
                        font_size: sp(14)
                        background_color: 0.15,0.15,0.22,1
                        foreground_color: 1,1,1,1
                        hint_text_color: 0.4,0.4,0.5,1
                        cursor_color: 0.4,0.7,1,1
                        padding: dp(12), dp(10)

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
                        height: dp(44)
                        font_size: sp(14)
                        background_color: 0.15,0.15,0.22,1
                        foreground_color: 1,1,1,1
                        hint_text_color: 0.4,0.4,0.5,1
                        padding: dp(12), dp(10)
                    TextInput:
                        id: inp_pass
                        hint_text: 'Пароль'
                        multiline: False
                        password: True
                        size_hint_y: None
                        height: dp(44)
                        font_size: sp(14)
                        background_color: 0.15,0.15,0.22,1
                        foreground_color: 1,1,1,1
                        hint_text_color: 0.4,0.4,0.5,1
                        padding: dp(12), dp(10)

                Label:
                    text: 'ПОИСК'
                    font_size: sp(12)
                    color: 0.4,0.7,1,1
                    size_hint_y: None
                    height: dp(25)
                    halign: 'left'
                    text_size: self.size
                    bold: True

                TextInput:
                    id: inp_keyword
                    hint_text: 'Что искать'
                    multiline: False
                    size_hint_y: None
                    height: dp(44)
                    font_size: sp(14)
                    background_color: 0.15,0.15,0.22,1
                    foreground_color: 1,1,1,1
                    hint_text_color: 0.4,0.4,0.5,1
                    padding: dp(12), dp(10)

                Label:
                    text: 'КОММЕНТАРИИ'
                    font_size: sp(12)
                    color: 0.4,0.7,1,1
                    size_hint_y: None
                    height: dp(25)
                    halign: 'left'
                    text_size: self.size
                    bold: True

                TextInput:
                    id: inp_c1
                    hint_text: 'Вариант 1 (обязательно)'
                    multiline: False
                    size_hint_y: None
                    height: dp(42)
                    font_size: sp(14)
                    background_color: 0.15,0.15,0.22,1
                    foreground_color: 1,1,1,1
                    hint_text_color: 0.4,0.4,0.5,1
                    padding: dp(12), dp(10)

                TextInput:
                    id: inp_c2
                    hint_text: 'Вариант 2'
                    multiline: False
                    size_hint_y: None
                    height: dp(42)
                    font_size: sp(14)
                    background_color: 0.15,0.15,0.22,1
                    foreground_color: 1,1,1,1
                    hint_text_color: 0.4,0.4,0.5,1
                    padding: dp(12), dp(10)

                TextInput:
                    id: inp_c3
                    hint_text: 'Вариант 3'
                    multiline: False
                    size_hint_y: None
                    height: dp(42)
                    font_size: sp(14)
                    background_color: 0.15,0.15,0.22,1
                    foreground_color: 1,1,1,1
                    hint_text_color: 0.4,0.4,0.5,1
                    padding: dp(12), dp(10)

                TextInput:
                    id: inp_c4
                    hint_text: 'Вариант 4'
                    multiline: False
                    size_hint_y: None
                    height: dp(42)
                    font_size: sp(14)
                    background_color: 0.15,0.15,0.22,1
                    foreground_color: 1,1,1,1
                    hint_text_color: 0.4,0.4,0.5,1
                    padding: dp(12), dp(10)

                Label:
                    text: 'НАСТРОЙКИ'
                    font_size: sp(12)
                    color: 0.4,0.7,1,1
                    size_hint_y: None
                    height: dp(25)
                    halign: 'left'
                    text_size: self.size
                    bold: True

                BoxLayout:
                    size_hint_y: None
                    height: dp(42)
                    spacing: dp(8)
                    Label:
                        text: 'Видео:'
                        color: 0.7,0.7,0.8,1
                        font_size: sp(14)
                    TextInput:
                        id: inp_count
                        text: '30'
                        multiline: False
                        input_filter: 'int'
                        size_hint_x: 0.3
                        font_size: sp(15)
                        background_color: 0.15,0.15,0.22,1
                        foreground_color: 1,1,1,1
                        padding: dp(10), dp(10)
                        halign: 'center'

                BoxLayout:
                    size_hint_y: None
                    height: dp(42)
                    spacing: dp(8)
                    Label:
                        text: 'Пауза сек:'
                        color: 0.7,0.7,0.8,1
                        font_size: sp(14)
                    TextInput:
                        id: inp_dmin
                        text: '10'
                        multiline: False
                        input_filter: 'int'
                        size_hint_x: 0.15
                        font_size: sp(15)
                        background_color: 0.15,0.15,0.22,1
                        foreground_color: 1,1,1,1
                        padding: dp(10), dp(10)
                        halign: 'center'
                    Label:
                        text: '-'
                        color: 0.5,0.5,0.6,1
                        size_hint_x: 0.05
                    TextInput:
                        id: inp_dmax
                        text: '25'
                        multiline: False
                        input_filter: 'int'
                        size_hint_x: 0.15
                        font_size: sp(15)
                        background_color: 0.15,0.15,0.22,1
                        foreground_color: 1,1,1,1
                        padding: dp(10), dp(10)
                        halign: 'center'

                BoxLayout:
                    size_hint_y: None
                    height: dp(42)
                    Label:
                        text: 'Ответы на комменты:'
                        color: 0.7,0.7,0.8,1
                        font_size: sp(14)
                    Switch:
                        id: sw_reply
                        active: False

                Button:
                    text: 'ЗАПУСТИТЬ'
                    font_size: sp(18)
                    bold: True
                    size_hint_y: None
                    height: dp(54)
                    background_normal: ''
                    background_color: 0.15,0.45,1,1
                    on_release: app.start()

                Widget:
                    size_hint_y: None
                    height: dp(30)

    Screen:
        name: 'run'
        canvas.before:
            Color:
                rgba: 0.06, 0.06, 0.09, 1
            Rectangle:
                pos: self.pos
                size: self.size
        BoxLayout:
            orientation: 'vertical'

            BoxLayout:
                size_hint_y: None
                height: dp(50)
                padding: dp(6)
                canvas.before:
                    Color:
                        rgba: 0.1,0.1,0.15,1
                    Rectangle:
                        pos: self.pos
                        size: self.size
                Button:
                    text: '<'
                    size_hint_x: None
                    width: dp(44)
                    font_size: sp(20)
                    background_normal: ''
                    background_color: 0,0,0,0
                    color: 1,1,1,1
                    on_release: app.go_back()
                Label:
                    text: app.run_title
                    font_size: sp(16)
                    bold: True
                    color: 1,1,1,1
                    halign: 'left'
                    text_size: self.size
                    valign: 'center'

            BoxLayout:
                size_hint_y: None
                height: dp(68)
                padding: dp(6)
                spacing: dp(6)

                BoxLayout:
                    orientation: 'vertical'
                    canvas.before:
                        Color:
                            rgba: 0.1,0.12,0.18,1
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(8)]
                    Label:
                        text: str(app.sv)
                        font_size: sp(22)
                        bold: True
                        color: 0.4,0.7,1,1
                    Label:
                        text: 'видео'
                        font_size: sp(10)
                        color: 0.5,0.5,0.6,1

                BoxLayout:
                    orientation: 'vertical'
                    canvas.before:
                        Color:
                            rgba: 0.1,0.15,0.12,1
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(8)]
                    Label:
                        text: str(app.sc)
                        font_size: sp(22)
                        bold: True
                        color: 0.3,0.9,0.4,1
                    Label:
                        text: 'отправлено'
                        font_size: sp(10)
                        color: 0.5,0.5,0.6,1

                BoxLayout:
                    orientation: 'vertical'
                    canvas.before:
                        Color:
                            rgba: 0.15,0.1,0.1,1
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(8)]
                    Label:
                        text: str(app.se)
                        font_size: sp(22)
                        bold: True
                        color: 1,0.4,0.3,1
                    Label:
                        text: 'ошибки'
                        font_size: sp(10)
                        color: 0.5,0.5,0.6,1

            ScrollView:
                id: lscr
                do_scroll_x: False
                Label:
                    id: lbl
                    text: app.log
                    font_size: sp(11)
                    color: 0.7,0.7,0.75,1
                    size_hint_y: None
                    height: max(self.texture_size[1] + dp(20), lscr.height)
                    text_size: self.width - dp(20), None
                    halign: 'left'
                    valign: 'top'
                    padding: dp(10), dp(6)
                    markup: True

            BoxLayout:
                size_hint_y: None
                height: dp(52)
                padding: dp(8)
                spacing: dp(8)
                canvas.before:
                    Color:
                        rgba: 0.1,0.1,0.15,1
                    Rectangle:
                        pos: self.pos
                        size: self.size
                Button:
                    id: bp
                    text: 'ПАУЗА'
                    font_size: sp(14)
                    bold: True
                    background_normal: ''
                    background_color: 0.75,0.55,0.1,1
                    on_release: app.pause()
                Button:
                    text: 'СТОП'
                    font_size: sp(14)
                    bold: True
                    background_normal: ''
                    background_color: 0.85,0.2,0.2,1
                    on_release: app.stop()
'''


class BotApp(App):
    status = StringProperty('Введи данные и жми Запустить')
    log = StringProperty('')
    run_title = StringProperty('')
    sv = NumericProperty(0)
    sc = NumericProperty(0)
    se = NumericProperty(0)

    def build(self):
        self.title = 'TikTok Bot'
        self.running = False
        self.is_paused = False
        self.login_mode = 'cookie'
        return Builder.load_string(KV)

    def switch_login(self, mode):
        self.login_mode = mode
        ids = self.root.ids
        if mode == 'cookie':
            ids.cookie_box.height = 100
            ids.cookie_box.opacity = 1
            ids.pass_box.height = 0
            ids.pass_box.opacity = 0
        else:
            ids.cookie_box.height = 0
            ids.cookie_box.opacity = 0
            ids.pass_box.height = 100
            ids.pass_box.opacity = 1

    def start(self):
        ids = self.root.ids
        kw = ids.inp_keyword.text.strip()
        c1 = ids.inp_c1.text.strip()
        if not kw:
            self.status = 'Введи поисковый запрос'
            return
        if not c1:
            self.status = 'Введи хотя бы 1 комментарий'
            return

        templates = [c1]
        for f in [ids.inp_c2, ids.inp_c3, ids.inp_c4]:
            t = f.text.strip()
            if t:
                templates.append(t)

        try:
            count = int(ids.inp_count.text)
        except:
            count = 30
        try:
            dmin = int(ids.inp_dmin.text)
        except:
            dmin = 10
        try:
            dmax = int(ids.inp_dmax.text)
        except:
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
        self.root.ids.sm.current = 'run'
        threading.Thread(target=self._run, args=(cfg,), daemon=True).start()

    def _run(self, cfg):
        bot = TikTok()
        self._log('[color=6699ff]Запуск...[/color]')

        if cfg['mode'] == 'password':
            ok, msg = bot.login_password(cfg['email'], cfg['password'])
        else:
            if not cfg['cookie']:
                self._log('[color=ff5555]Вставь cookie![/color]')
                return
            ok, msg = bot.login_cookie(cfg['cookie'])

        if not ok:
            self._log('[color=ff5555]Ошибка входа: ' + str(msg) + '[/color]')
            return
        self._log('[color=55ff55]Вошел как @' + str(msg) + '[/color]\n')

        self._log('[color=aaaaaa]Ищу видео...[/color]')
        videos = bot.search(cfg['keyword'], cfg['count'])
        if not videos:
            self._log('[color=ff5555]Видео не найдены[/color]')
            return
        self._log('[color=55ff55]Найдено: ' + str(len(videos)) + '[/color]\n')

        gen = CommentGen(cfg['templates'])

        for i, vid in enumerate(videos):
            if not self.running:
                break
            while self.is_paused and self.running:
                time.sleep(0.5)
            if not self.running:
                break

            text = gen.next()
            self._log('[color=6699ff][' + str(i+1) + '/' + str(len(videos)) + '][/color] ' + text)

            if cfg['reply']:
                ok, msg = bot.reply(vid, text)
            else:
                ok, msg = bot.comment(vid, text)

            if ok:
                self._upd('sc')
                self._log('[color=55ff55]  OK[/color]')
            else:
                self._upd('se')
                self._log('[color=ff5555]  ' + msg + '[/color]')
                if 'login' in msg.lower() or 'session' in msg.lower():
                    self._log('[color=ffaa00]Сессия истекла[/color]')
                    break

            self._upd('sv')

            if i < len(videos) - 1 and self.running:
                w = random.uniform(cfg['dmin'], cfg['dmax'])
                self._log('[color=aaaaaa]  ' + str(int(w)) + 'с...[/color]\n')
                time.sleep(w)

        self._log('\n[color=6699ff]ГОТОВО[/color]')
        self.running = False

    def _log(self, msg):
        Clock.schedule_once(lambda dt: setattr(self, 'log', self.log + msg + '\n'))
        Clock.schedule_once(lambda dt: self._scroll())

    def _scroll(self):
        try:
            self.root.ids.lscr.scroll_y = 0
        except:
            pass

    def _upd(self, attr):
        def do(dt):
            setattr(self, attr, getattr(self, attr) + 1)
        Clock.schedule_once(do)

    def stop(self):
        self.running = False
        self._log('[color=ff5555]СТОП[/color]')

    def pause(self):
        self.is_paused = not self.is_paused
        try:
            self.root.ids.bp.text = 'ДАЛЬШЕ' if self.is_paused else 'ПАУЗА'
        except:
            pass

    def go_back(self):
        self.stop()
        self.root.ids.sm.current = 'login'


if __name__ == '__main__':
    BotApp().run()
