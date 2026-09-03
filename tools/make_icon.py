"""Draw the application icon.

Original artwork on purpose: a generic voxel cube plus a play arrow says
"start a block-game server" without borrowing Mojang's textures or wordmark.
Everything is drawn at 4x and downscaled, so the edges stay clean at 16px
where Windows shows it in the taskbar.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "assets"
S = 1024                      # working size, downscaled at the end
SIZES = [16, 24, 32, 48, 64, 128, 256]

BG_TOP = (43, 48, 58)
BG_BOTTOM = (24, 26, 32)
GRASS = (110, 190, 96)
GRASS_DARK = (72, 140, 66)
DIRT = (129, 92, 62)
DIRT_DARK = (96, 66, 44)
PLAY = (245, 250, 245)
PLAY_EDGE = (36, 120, 52)


def rounded_background(img: Image.Image) -> None:
    d = ImageDraw.Draw(img)
    # a soft vertical gradient reads better than flat fill at large sizes
    for y in range(S):
        t = y / S
        d.line([(0, y), (S, y)],
               fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=S // 5,
                                           fill=255)
    img.putalpha(mask)


def cube(d: ImageDraw.ImageDraw) -> None:
    """A simple isometric block: bright top, two shaded sides."""
    cx, cy = S // 2, int(S * 0.54)
    w, h = int(S * 0.30), int(S * 0.17)     # half-width, half-height of the top
    depth = int(S * 0.24)

    top = [(cx, cy - h), (cx + w, cy), (cx, cy + h), (cx - w, cy)]
    left = [(cx - w, cy), (cx, cy + h), (cx, cy + h + depth), (cx - w, cy + depth)]
    right = [(cx + w, cy), (cx, cy + h), (cx, cy + h + depth), (cx + w, cy + depth)]

    d.polygon(top, fill=GRASS)
    d.polygon(left, fill=DIRT)
    d.polygon(right, fill=DIRT_DARK)
    # a grass rim on the two visible sides
    rim = int(S * 0.045)
    d.polygon([(cx - w, cy), (cx, cy + h), (cx, cy + h + rim), (cx - w, cy + rim)],
              fill=GRASS_DARK)
    d.polygon([(cx + w, cy), (cx, cy + h), (cx, cy + h + rim), (cx + w, cy + rim)],
              fill=(60, 118, 56))


def play(d: ImageDraw.ImageDraw) -> None:
    """The start arrow, floating above the block."""
    cx, cy = S // 2, int(S * 0.35)
    r = int(S * 0.16)
    tri = [(cx - r * 0.72, cy - r), (cx - r * 0.72, cy + r), (cx + r, cy)]
    d.polygon(tri, fill=PLAY, outline=PLAY_EDGE, width=max(2, S // 160))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (S, S))
    rounded_background(img)
    d = ImageDraw.Draw(img)
    cube(d)
    play(d)

    png = OUT / "icon.png"
    img.resize((256, 256), Image.LANCZOS).save(png)
    img.save(OUT / "icon@1024.png")
    frames = [img.resize((n, n), Image.LANCZOS) for n in SIZES]
    frames[-1].save(OUT / "icon.ico", format="ICO",
                    sizes=[(n, n) for n in SIZES])
    print("เขียนแล้ว:", OUT / "icon.ico", "และ", png)


if __name__ == "__main__":
    main()
