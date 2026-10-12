[app]
title = AURELIAN AI
package.name = aurelian
package.domain = com.aurelian
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,md
version = 1.1.0
requirements = python3,kivy,telethon
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,WAKE_LOCK
android.api = 35
android.minapi = 26
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
p4a.bootstrap = sdl2

[buildozer]
log_level = 2
warn_on_root = 0
