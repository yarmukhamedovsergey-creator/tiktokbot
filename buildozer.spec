[app]
title = TikTok Bot
package.name = tiktokbot
package.domain = com.mybot
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 3.0
requirements = python3,kivy==2.2.1,requests,urllib3,charset-normalizer,idna,certifi,pillow
android.permissions = INTERNET
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
orientation = portrait
fullscreen = 0
android.presplash_color = #0F0F17

[buildozer]
log_level = 2
warn_on_root = 1
