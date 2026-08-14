# "Share to Faseeh Scan" and home-screen shortcuts

## Incoming shares (Android)

When a user shares a PDF/image from WhatsApp, Gmail, a file manager, etc.,
Faseeh Scan appears in the chooser and receives the file(s), encrypts them,
and auto-backs them up.

Implementation:

- The Flutter plugin `receive_sharing_intent` is declared under
  `[tool.flet.flutter.pubspec.dependencies]` in `pyproject.toml`.
- `extensions/faseeh_share` is a Flet extension wrapping it and forwarding
  payloads to Python as page events (`faseeh_share_receive`).
- `faseeh_scan/features/share_intent.py` provides `ShareIntentService`,
  which the UI subscribes to.
- The app must declare Android intent filters for `ACTION_SEND` and
  `ACTION_SEND_MULTIPLE` with `mimeType */*`. Because Flet's pyproject does
  not directly support arbitrary intent filters, add them to the generated
  `build/flutter/android/app/src/main/AndroidManifest.xml` after `flet build
  apk`, or include them via a Flet build template. A minimal snippet:

```xml
<intent-filter>
    <action android:name="android.intent.action.SEND"/>
    <category android:name="android.intent.category.DEFAULT"/>
    <data android:mimeType="*/*"/>
</intent-filter>
<intent-filter>
    <action android:name="android.intent.action.SEND_MULTIPLE"/>
    <category android:name="android.intent.category.DEFAULT"/>
    <data android:mimeType="*/*"/>
</intent-filter>
```

## Home-screen shortcut ("Scan now")

The Flutter `quick_actions` plugin exposes a long-press app-icon shortcut
("Scan document"). It is declared as a Flutter dependency and handled by a
small Flet extension that sends a `faseeh_shortcut_scan` page event. Tapping
the shortcut opens the app directly into the scan flow.

Both features degrade gracefully: on desktop/web they are simply absent, and
all other functionality works unchanged.
