#!/bin/sh

if command -v launchctl >/dev/null 2>&1; then
    launchctl start com.user.macos-cleanup-service >/dev/null 2>&1 || true
fi

if [ -x "$HOME/.local/libexec/macos-cleanup-service/status.py" ]; then
    /usr/bin/python3 "$HOME/.local/libexec/macos-cleanup-service/status.py" 2>/dev/null || true
fi
