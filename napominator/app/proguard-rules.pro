# Vosk
-keep class org.vosk.** { *; }
-keep class com.sun.jna.** { *; }
-dontwarn com.sun.jna.**

# ical4android
-keep class at.bitfire.ical4android.** { *; }

# OkHttp
-dontwarn okhttp3.**
-keep class okhttp3.** { *; }
