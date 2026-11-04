"""Generate maskable PWA icons (192/512): emerald tile + white K, glyph inside
the 80% safe zone required by Android adaptive icons."""
from PIL import Image, ImageDraw, ImageFont

GREEN = (5, 150, 105, 255)      # emerald-600 (#059669)
GREEN_DARK = (4, 120, 87, 255)  # emerald-700

def make(size: int, path: str):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # full-bleed vertical gradient-ish background (maskable needs full bleed)
    d.rectangle([0, 0, size, size], fill=GREEN_DARK)
    d.rectangle([0, 0, size, size * 2 // 5], fill=GREEN)
    # subtle diagonal accent
    d.polygon([(0, size), (size * 2 // 5, size), (0, size * 3 // 5)], fill=(4, 108, 78, 255))

    # glyph inside safe zone: content box = 66% of canvas, centered
    box = int(size * 0.66)
    x0 = (size - box) // 2
    # bold K drawn from rectangles (no font dependency, always crisp)
    k = box
    stem_w = int(k * 0.20)
    stem_h = k
    # stem
    d.rounded_rectangle([x0, (size - stem_h) // 2, x0 + stem_w, (size + stem_h) // 2],
                        radius=stem_w // 5, fill=(255, 255, 255, 255))
    # upper arm
    arm_w = int(k * 0.17)
    upper = [(x0 + stem_w + int(k * 0.06), (size - stem_h) // 2),
             (x0 + stem_w + int(k * 0.06) + arm_w, (size - stem_h) // 2),
             (x0 + k, (size + stem_h) // 2 - int(k * 0.02)),
             (x0 + k - arm_w, (size + stem_h) // 2 - int(k * 0.02))]
    d.polygon(upper, fill=(255, 255, 255, 255))
    # lower arm
    lower = [(x0 + k - arm_w, (size - stem_h) // 2 + int(k * 0.02)),
             (x0 + k, (size - stem_h) // 2 + int(k * 0.02)),
             (x0 + stem_w + int(k * 0.06) + arm_w, (size + stem_h) // 2),
             (x0 + stem_w + int(k * 0.06), (size + stem_h) // 2)]
    d.polygon(lower, fill=(255, 255, 255, 255))

    img.save(path, "PNG")
    print(f"wrote {path} ({size}x{size})")

make(192, "/home/z/my-project/public/icons/icon-maskable-192.png")
make(512, "/home/z/my-project/public/icons/icon-maskable-512.png")
