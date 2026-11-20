from __future__ import annotations

from pathlib import Path

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont


OUT_DIR = Path(__file__).resolve().parents[1] / "src" / "technical_drawing_analysis" / "sample_data"


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT_28 = font(28)
FONT_30 = font(30)
FONT_34 = font(34)
FONT_42 = font(42)
FONT_58 = font(58)


def line(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], width: int = 3) -> None:
    draw.line(xy, fill="black", width=width)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int]) -> None:
    line(draw, (*start, *end), 2)
    sx, sy = start
    ex, ey = end
    if abs(ex - sx) >= abs(ey - sy):
        direction = 1 if ex > sx else -1
        points = [(ex, ey), (ex - direction * 18, ey - 8), (ex - direction * 18, ey + 8)]
    else:
        direction = 1 if ey > sy else -1
        points = [(ex, ey), (ex - 8, ey - direction * 18), (ex + 8, ey - direction * 18)]
    draw.polygon(points, fill="black")


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: str = "normal") -> None:
    selected = {"small": FONT_28, "medium": FONT_30, "normal": FONT_34, "large": FONT_42, "title": FONT_58}[size]
    draw.text(xy, value, fill="black", font=selected)


def title_block(draw: ImageDraw.ImageDraw, w: int, h: int, title: str, drawing_no: str, material: str) -> None:
    left = 80
    top = h - 380
    right = w - 80
    bottom = h - 70
    draw.rectangle((left, top, right, bottom), outline="black", width=3)
    line(draw, (left, top + 78, right, top + 78), 2)
    line(draw, (left, top + 180, right, top + 180), 2)
    line(draw, (w - 620, top, w - 620, bottom), 2)
    line(draw, (w - 330, top + 180, w - 330, bottom), 2)
    line(draw, (w - 620, top + 245, right, top + 245), 2)
    text(draw, (left + 20, top + 22), "MASSE IN MM", "small")
    text(draw, (left + 20, top + 105), "ALLGEMEINTOLERANZEN", "small")
    text(draw, (w - 600, top + 22), "ZEICHNUNG NICHT SKALIEREN", "small")
    text(draw, (w - 600, top + 105), "TITEL", "small")
    text(draw, (w - 600, top + 138), title, "normal")
    text(draw, (w - 600, top + 196), "ZEICHNUNGSNR.", "small")
    text(draw, (w - 600, top + 257), drawing_no, "medium")
    text(draw, (w - 310, top + 196), "MATERIAL", "small")
    text(draw, (w - 310, top + 257), material, "medium")


def make_canvas(w: int, h: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, w - 40, h - 40), outline="#999999", width=4)
    draw.rectangle((80, 80, w - 80, h - 80), outline="#bbbbbb", width=2)
    return image, draw


def bracket_holder() -> None:
    w, h = 1500, 2100
    image, draw = make_canvas(w, h)
    title_block(draw, w, h, "Halter", "TZ-1001", "PLA")
    part = [(330, 470), (800, 470), (800, 1320), (690, 1320), (690, 700), (440, 700), (440, 1320), (330, 1320)]
    draw.line(part + [part[0]], fill="black", width=4)
    draw.arc((390, 510, 740, 860), start=180, end=360, fill="black", width=4)
    draw.arc((445, 575, 685, 815), start=180, end=360, fill="black", width=3)
    for cx in (390, 740):
        draw.ellipse((cx - 25, 520 - 25, cx + 25, 520 + 25), outline="black", width=3)
        line(draw, (cx - 55, 520, cx + 55, 520), 1)
        line(draw, (cx, 465, cx, 575), 1)
    text(draw, (265, 335), "2x Ø3.40 ±0.10")
    arrow(draw, (390, 390), (390, 500))
    arrow(draw, (740, 390), (740, 500))
    text(draw, (885, 415), "4.00  (+0.10 / -0.20)")
    text(draw, (850, 840), "60.00 ±0.10")
    arrow(draw, (960, 470), (960, 1320))
    arrow(draw, (960, 1320), (960, 470))
    text(draw, (850, 1395), "7.50  (+0.10 / -0.20)")
    arrow(draw, (330, 1410), (800, 1410))
    text(draw, (650, 1380), "6.95")
    text(draw, (615, 230), "R8.05")
    text(draw, (490, 190), "R11.20")
    text(draw, (1050, 1495), "Ra 6.5", "title")
    line(draw, (1030, 1470, 1110, 1585), 2)
    text(draw, (150, 1450), "// 0.6 A")
    draw.rectangle((500, 1120, 570, 1175), outline="black", width=2)
    text(draw, (520, 1128), "A")
    image.save(OUT_DIR / "bracket-holder.png")


def adapter_plate() -> None:
    w, h = 1800, 1300
    image, draw = make_canvas(w, h)
    title_block(draw, w, h, "Adapterplatte", "TZ-1002", "AL-6061")
    draw.rectangle((360, 210, 1280, 770), outline="black", width=4)
    for cx, cy in ((500, 350), (1140, 350), (500, 630), (1140, 630)):
        draw.ellipse((cx - 45, cy - 45, cx + 45, cy + 45), outline="black", width=3)
        line(draw, (cx - 80, cy, cx + 80, cy), 1)
        line(draw, (cx, cy - 80, cx, cy + 80), 1)
    draw.rectangle((690, 390, 950, 590), outline="black", width=3)
    text(draw, (375, 115), "4x Ø8.00 DURCH")
    text(draw, (1030, 125), "SENKUNG Ø14.00 x 4.00")
    text(draw, (725, 800), "200.00 ±0.15")
    arrow(draw, (360, 820), (1280, 820))
    arrow(draw, (1280, 820), (360, 820))
    text(draw, (1285, 465), "120.00 ±0.10")
    arrow(draw, (1330, 210), (1330, 770))
    arrow(draw, (1330, 770), (1330, 210))
    text(draw, (665, 335), "80.00")
    text(draw, (1370, 220), "A")
    draw.rectangle((1350, 205, 1400, 255), outline="black", width=2)
    text(draw, (220, 835), "FASE 1.0 x 45°")
    text(draw, (1140, 835), "EBENHEIT 0.05 A")
    image.save(OUT_DIR / "adapter-plate.png")


def shaft_collar() -> None:
    w, h = 1800, 1300
    image, draw = make_canvas(w, h)
    title_block(draw, w, h, "Wellenring", "TZ-1003", "C45 STAHL")
    y = 490
    profile = [(300, y - 90), (520, y - 90), (520, y - 135), (980, y - 135), (980, y - 75), (1300, y - 75)]
    lower = [(1300, y + 75), (980, y + 75), (980, y + 135), (520, y + 135), (520, y + 90), (300, y + 90)]
    draw.line(profile + lower + [profile[0]], fill="black", width=4)
    line(draw, (260, y, 1340, y), 1)
    text(draw, (350, 235), "Ø22.00 h7")
    arrow(draw, (410, 300), (410, y - 90))
    arrow(draw, (410, 680), (410, y + 90))
    text(draw, (640, 185), "Ø35.00 ±0.05")
    arrow(draw, (760, 275), (760, y - 135))
    arrow(draw, (760, 710), (760, y + 135))
    text(draw, (1060, 265), "M24 x 1.5")
    text(draw, (455, 815), "25.00")
    text(draw, (720, 815), "45.00")
    text(draw, (1035, 815), "30.00")
    arrow(draw, (300, 780), (520, 780))
    arrow(draw, (520, 780), (980, 780))
    arrow(draw, (980, 780), (1300, 780))
    text(draw, (1280, 175), "Ra 1.6", "large")
    line(draw, (1240, 170, 1300, 250), 2)
    text(draw, (220, 890), "SCHARFE KANTEN BRECHEN 0.2")
    text(draw, (1220, 890), "KOAXIALITAET Ø0.03 A")
    image.save(OUT_DIR / "shaft-collar.png")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bracket_holder()
    adapter_plate()
    shaft_collar()


if __name__ == "__main__":
    main()
