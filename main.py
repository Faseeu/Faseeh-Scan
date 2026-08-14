"""Entry point for Faseeh Scan.

Run locally:
    python main.py                 # opens a desktop window
    flet run --web main.py         # runs in your browser (safe: no phone data)

Build for Android (on a machine with the Android SDK / Flutter):
    flet build apk
    # or use the helper: ./scripts/build_apk.sh
"""

import flet as ft
from faseeh_scan.ui.app import App


def main(page: ft.Page):
    App(page)


if __name__ == "__main__":
    ft.app(target=main)
