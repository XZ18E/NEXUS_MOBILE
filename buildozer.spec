[app]
title = NEXUS Calendar
package.name = nexuscalendar
package.domain = org.nexus
source.dir = .
source.include_exts = py
source.exclude_dirs = tests, bin, .github, .buildozer
version = 1.0.0
requirements = python3,kivy==2.3.0,plyer,sqlite3,pyjnius
orientation = portrait
fullscreen = 0
android.permissions = POST_NOTIFICATIONS
android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
