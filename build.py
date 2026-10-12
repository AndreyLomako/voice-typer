"""Сборка VoiceTyper hs для текущей ОС (PyInstaller).

  python build.py            → dist/  + готовый архив в release/
  python build.py --smoke    → ещё и проверка распознавания собранной программой

Windows: release/VoiceTyper-hs.exe
macOS:   release/VoiceTyper-hs-macOS-arm64.zip  (внутри «VoiceTyper hs.app»)
Linux:   release/VoiceTyper-hs-linux-x86_64.tar.gz
"""
from __future__ import annotations

import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST, RELEASE = ROOT / "dist", ROOT / "release"
SEP = ";" if os.name == "nt" else ":"

sys.path.insert(0, str(ROOT))
from voicetyper import APP_DISPLAY, AUTHOR, __version__  # noqa: E402

COMMON = [
    "--noconfirm", "--clean",
    "--collect-data", "customtkinter",
    "--collect-data", "faster_whisper",
    "--collect-binaries", "ctranslate2",
    "--collect-binaries", "onnxruntime",
    "--add-data", f"assets/icon.ico{SEP}assets",
    "--add-data", f"assets/icon.png{SEP}assets",
    "--exclude-module", "matplotlib", "--exclude-module", "pandas", "--exclude-module", "scipy",
    "--exclude-module", "torch", "--exclude-module", "IPython", "--exclude-module", "pytest",
]


def pyinstaller(*args: str) -> None:
    subprocess.check_call([sys.executable, "-m", "PyInstaller", *COMMON, *args, "run.py"], cwd=ROOT)


def build_windows() -> Path:
    pyinstaller("--onefile", "--windowed", "--name", "VoiceTyper-hs",
                "--icon", "assets/icon.ico", "--version-file", "version_info.txt")
    out = RELEASE / "VoiceTyper-hs.exe"
    shutil.copy2(DIST / "VoiceTyper-hs.exe", out)
    return out


def build_macos() -> Path:
    pyinstaller("--windowed", "--onedir", "--name", APP_DISPLAY,
                "--icon", "assets/icon-256.png",
                "--osx-bundle-identifier", "com.andreylomako.voicetyper-hs",
                "--hidden-import", "keyring.backends.macOS")
    app = DIST / f"{APP_DISPLAY}.app"
    plist_path = app / "Contents" / "Info.plist"
    with open(plist_path, "rb") as f:
        info = plistlib.load(f)
    info.update({
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "NSHumanReadableCopyright": f"© 2026 {AUTHOR}. MIT License",
        # без этого macOS молча отдаёт тишину вместо звука с микрофона
        "NSMicrophoneUsageDescription": "VoiceTyper hs записывает речь, чтобы превратить её в текст.",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
    })
    with open(plist_path, "wb") as f:
        plistlib.dump(info, f)
    # Info.plist изменён — подпись нужно обновить (ad-hoc, без сертификата разработчика)
    subprocess.check_call(["codesign", "--force", "--deep", "--sign", "-", str(app)])
    arch = "arm64" if platform.machine() == "arm64" else "x86_64"
    out = RELEASE / f"VoiceTyper-hs-macOS-{arch}.zip"
    subprocess.check_call(["ditto", "-c", "-k", "--keepParent", str(app), str(out)])
    return out


def build_linux() -> Path:
    pyinstaller("--onefile", "--name", "VoiceTyper-hs",
                "--hidden-import", "pynput.keyboard._xorg", "--hidden-import", "pynput.mouse._xorg",
                "--hidden-import", "pystray._xorg",
                "--hidden-import", "keyring.backends.SecretService")
    staging = DIST / "VoiceTyper-hs-linux"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    shutil.copy2(DIST / "VoiceTyper-hs", staging / "VoiceTyper-hs")
    shutil.copy2(ROOT / "assets" / "icon-256.png", staging / "voicetyper-hs.png")
    shutil.copy2(ROOT / "packaging" / "linux" / "install.sh", staging / "install.sh")
    os.chmod(staging / "install.sh", 0o755)
    os.chmod(staging / "VoiceTyper-hs", 0o755)
    out = RELEASE / f"VoiceTyper-hs-linux-{platform.machine()}.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        tar.add(staging, arcname="VoiceTyper-hs")
    return out


def built_binary() -> Path:
    if sys.platform == "win32":
        return DIST / "VoiceTyper-hs.exe"
    if sys.platform == "darwin":
        return DIST / f"{APP_DISPLAY}.app" / "Contents" / "MacOS" / APP_DISPLAY
    return DIST / "VoiceTyper-hs"


def smoke_test() -> None:
    """Собранная программа должна распознать тестовую фразу."""
    wav, out = ROOT / "tests" / "speech_ru.wav", ROOT / "build" / "smoke.txt"
    out.parent.mkdir(exist_ok=True)
    subprocess.check_call([str(built_binary()), "--transcribe-file", str(wav), str(out), "base"], timeout=900)
    text = out.read_text(encoding="utf-8")
    print("Распознано:", text)
    if "привет" not in text.lower():
        sys.exit("Проверка не пройдена: в результате нет слова «Привет»")


def main() -> None:
    subprocess.check_call([sys.executable, "make_icon.py"], cwd=ROOT)
    RELEASE.mkdir(exist_ok=True)
    builder = {"win32": build_windows, "darwin": build_macos}.get(sys.platform, build_linux)
    out = builder()
    print(f"Готово: {out.relative_to(ROOT)} ({out.stat().st_size / 1e6:.0f} МБ)")
    if "--smoke" in sys.argv:
        smoke_test()


if __name__ == "__main__":
    main()
