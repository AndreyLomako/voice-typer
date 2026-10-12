#!/bin/sh
# Установка VoiceTyper hs для текущего пользователя (без sudo):
# программа в ~/.local/bin, ярлык в меню приложений.
set -e
cd "$(dirname "$0")"

BIN="$HOME/.local/bin"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
mkdir -p "$BIN" "$APPS" "$ICONS"

install -m 755 VoiceTyper-hs "$BIN/VoiceTyper-hs"
install -m 644 voicetyper-hs.png "$ICONS/voicetyper-hs.png"
cat > "$APPS/voicetyper-hs.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=VoiceTyper hs
Comment=Голосовой ввод в любое поле
Exec=$BIN/VoiceTyper-hs
Icon=voicetyper-hs
Categories=Utility;Accessibility;
Terminal=false
EOF

echo "Установлено: $BIN/VoiceTyper-hs"
missing=""
ldconfig -p 2>/dev/null | grep -q libportaudio.so.2 || missing="$missing libportaudio2"
command -v xclip >/dev/null 2>&1 || command -v xsel >/dev/null 2>&1 || missing="$missing xclip"
if [ -n "$missing" ]; then
    echo "Нужны системные пакеты:$missing"
    echo "  Ubuntu/Debian: sudo apt install$missing"
    echo "  Fedora:        sudo dnf install portaudio xclip"
fi
if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
    echo "Внимание: сейчас сессия Wayland. Для глобальных клавиш и вставки выберите сессию Xorg на экране входа."
fi
