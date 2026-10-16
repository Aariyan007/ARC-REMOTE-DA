"""
Remote tools: the phone-facing tool layer (file search/download today; email,
scripts, app installs and Wi-Fi land in later changes).

Deliberately light: importing this package must not pull in the voice/ML stack,
so the server and its tests can use it anywhere.
"""
