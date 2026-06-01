"""py2app build config for Olwen.app.

    python3 setup.py py2app
"""
from setuptools import setup

APP = ["olwen_app.py"]
DATA_FILES: list = []
OPTIONS = {
    "argv_emulation": False,    "plist": {
        "CFBundleName": "Olwen",
        "CFBundleDisplayName": "Olwen",
        "CFBundleIdentifier": "com.olwen.app",
        "CFBundleShortVersionString": "0.4.0",
        "CFBundleVersion": "0.4.0",
        "LSUIElement": False,             # show in Dock (False = real app, not menu-bar-only)
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.productivity",
        "LSMinimumSystemVersion": "11.0",
        # macOS will only show our "we use accessibility" prompt with a reason here.
        "NSAppleEventsUsageDescription": "Olwen needs Apple Events to control other apps on your behalf.",
        "NSAccessibilityUsageDescription": "Olwen needs Accessibility access to move the cursor and send keystrokes when you ask him to.",
    },
    "packages": [
        "fastapi",
        "uvicorn",
        "pydantic",
        "pyautogui",
        "mss",
        "PIL",
        "starlette",
        "anyio",
    ],
    "includes": [
        "objc",
        "AppKit",
        "Foundation",
        "PyObjCTools",
    ],
}

setup(
    app=APP,
    name="Olwen",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
