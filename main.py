"""Entry point for the Medical Reports Backup Flet app.

Run locally:
    python main.py            # opens a desktop window
    flet run --web main.py    # runs in browser

Build for Android (on a machine with the Android SDK / Flutter):
    flet build apk
"""

import flet as ft

from medical_reports.ui.app import main as app_main

if __name__ == "__main__":
    ft.run(app_main)
