"""Генерирует assets/icon.ico из той же отрисовки, что и значок в трее."""
from voicetyper.tray import COLORS, draw_icon

img = draw_icon(COLORS["idle"], 256)
img.save("assets/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.resize((128, 128)).save("assets/icon.png")
img.save("assets/icon-256.png")
print("assets/icon.ico")
