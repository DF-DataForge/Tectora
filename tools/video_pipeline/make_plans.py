#!/usr/bin/env python3
"""Draw the fictional top-view plans the roof videos draw on.

The demo has no satellite key, so the drawing gets an uploaded plan as its
background: a house with an L-shaped flat roof and its garage, seen from
above, each with one side measured on site (the dimension line). The
storyboards click in the pixels of these images (the drawing's world
coordinates), so the shapes are listed in ``PLANS`` and the images are
deterministic.

    python tools/video_pipeline/make_plans.py   # → assets/plan_*.png
"""
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"

# Per plan: image size, roof outline (pixels), the measured side (two corners
# and its real length) and extras drawn on the roof.
PLANS = {
    "plan_woning": {
        "size": (1600, 1000),
        "px_per_m": 76,
        "origin": (330, 130),
        # L-shaped main roof, in metres from the origin.
        "roof": [(0, 0), (12.4, 0), (12.4, 6.0), (7.0, 6.0), (7.0, 9.5), (0, 9.5)],
        "measured": (0, 1, "12,40 m"),
        "skylight": None,
        "wall": None,
        "label": "Woning — plat dak",
    },
    "plan_garage": {
        "size": (1600, 1000),
        "px_per_m": 140,
        "origin": (366, 248),
        "roof": [(0, 0), (6.2, 0), (6.2, 3.6), (0, 3.6)],
        "measured": (0, 1, "6,20 m"),
        "skylight": None,
        # The house wall the garage roof is built against (left side).
        "wall": (-1.2, -1.0, 0.0, 4.6),
        "label": "Garage — plat dak",
    },
}


def to_px(plan, point):
    ox, oy = plan["origin"]
    scale = plan["px_per_m"]
    return (round(ox + point[0] * scale), round(oy + point[1] * scale))


def corners(name):
    """The roof's corners in image pixels: where the storyboard clicks."""
    plan = PLANS[name]
    return [to_px(plan, p) for p in plan["roof"]]


def texture(size, base, spread, seed, dots=60000):
    rng = random.Random(seed)
    image = Image.new("RGB", size, base)
    draw = ImageDraw.Draw(image)
    for _ in range(dots):
        x, y = rng.randrange(size[0]), rng.randrange(size[1])
        d = rng.randint(-spread, spread)
        draw.point((x, y), tuple(max(0, min(255, c + d)) for c in base))
    return image.filter(ImageFilter.GaussianBlur(0.6))


def draw_plan(name):
    plan = PLANS[name]
    size = plan["size"]
    image = texture(size, (122, 160, 98), 26, seed=name)            # lawn
    draw = ImageDraw.Draw(image)
    # A paved strip along the front and a hedge at the back.
    draw.rectangle((0, size[1] - 120, size[0], size[1]), fill=(178, 174, 166))
    draw.rectangle((0, 0, size[0], 36), fill=(70, 104, 62))

    roof = corners(name)
    # Shadow, then the gravel roof inside a light roof edge.
    shadow = [(x + 14, y + 16) for x, y in roof]
    draw.polygon(shadow, fill=(70, 86, 60))
    gravel = texture(size, (150, 148, 142), 34, seed=name + "-gravel")
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(roof, fill=255)
    image.paste(gravel, (0, 0), mask)
    draw.line(roof + [roof[0]], fill=(222, 222, 216), width=14, joint="curve")
    draw.line(roof + [roof[0]], fill=(96, 96, 92), width=3)

    if plan["wall"]:
        x1, y1, x2, y2 = plan["wall"]
        a, b = to_px(plan, (x1, y1)), to_px(plan, (x2, y2))
        draw.rectangle((a[0] + 14, a[1] + 16, b[0] + 14, b[1] + 16), fill=(70, 86, 60))
        draw.rectangle((a, b), fill=(176, 92, 70), outline=(110, 56, 44), width=4)
        wall_font = ImageFont.truetype(FONT, 30)
        text = "gevel woning"
        layer = Image.new("RGBA", (int(draw.textlength(text, font=wall_font)) + 8, 40), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((4, 0), text, fill=(255, 255, 255), font=wall_font)
        layer = layer.rotate(90, expand=True)
        image.paste(layer, ((a[0] + b[0]) // 2 - layer.width // 2, (a[1] + b[1]) // 2 - layer.height // 2), layer)

    if plan["skylight"]:
        cx, cy, r = plan["skylight"]
        (px, py), radius = to_px(plan, (cx, cy)), r * plan["px_per_m"]
        draw.ellipse((px - radius, py - radius, px + radius, py + radius),
                     fill=(196, 222, 236), outline=(240, 240, 240), width=6)

    # The side measured on site: a dimension line above it.
    a, b, text = plan["measured"]
    (x1, y1), (x2, y2) = roof[a], roof[b]
    y = min(y1, y2) - 52
    red = (200, 40, 40)
    draw.line((x1, y, x2, y), fill=red, width=4)
    for x in (x1, x2):
        draw.line((x, y - 18, x, y + 18), fill=red, width=4)
    font = ImageFont.truetype(FONT, 40)
    w = draw.textlength(text, font=font)
    mid = (x1 + x2) / 2
    draw.rectangle((mid - w / 2 - 12, y - 30, mid + w / 2 + 12, y + 28), fill=(255, 255, 255))
    draw.text((mid - w / 2, y - 26), text, fill=red, font=font)

    label_font = ImageFont.truetype(FONT, 34)
    draw.text((40, size[1] - 92), plan["label"], fill=(40, 40, 40), font=label_font)
    path = os.path.join(HERE, "assets", name + ".png")
    image.save(path, optimize=True)
    return path


def main():
    for name in PLANS:
        print(draw_plan(name), corners(name))


if __name__ == "__main__":
    main()
