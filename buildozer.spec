[app]

title = Excavator Offset Calculator
package.name = excavatoroffsetcalc
package.domain = org.bharathbommeeshwar

source.dir = .
source.include_exts = py,png,jpg,jpeg,ico,kv,atlas
source.include_patterns = assets/*

version = 1.0

# numpy is required (core calculations); no matplotlib - diagrams are
# drawn natively with Kivy graphics instructions for a smaller, more
# reliable Android build.
requirements = python3,kivy==2.3.1,numpy,pillow

p4a.branch = v2024.01.21

icon.filename = %(source.dir)s/assets/icon.png

orientation = portrait
fullscreen = 0

android.permissions =

# Reasonable modern defaults; raise minapi if you hit device-support
# issues, or leave as-is for broad compatibility.
android.minapi = 24
android.api = 33
android.ndk_api = 24

android.archs = arm64-v8a, armeabi-v7a

# Accept SDK licenses automatically on first build (still requires you
# to have Java + the Android SDK/NDK reachable from this machine, which
# buildozer downloads on first run if not already present).
android.accept_sdk_license = True

log_level = 2

[buildozer]
warn_on_root = 0
