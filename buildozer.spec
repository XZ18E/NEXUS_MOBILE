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
android.api = 33
android.ndk = 25b
android.ndk_api = 24
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True
android.add_src = widget/java
android.add_resources = widget/res/layout:layout, widget/res/drawable:drawable, widget/res/xml:xml
android.manifest.intent_filters = widget/intent_filters.xml

p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
