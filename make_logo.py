"""Generate a 512x512 WebP logo for the Notion email integration."""

from PIL import Image, ImageDraw, ImageFont

SIZE = 512
BG = "#191919"          # Notion dark
WHITE = "#FFFFFF"
GRAY = "#AAAAAA"
ACCENT = "#4A90D9"      # blue accent

img = Image.new("RGBA", (SIZE, SIZE), BG)
d = ImageDraw.Draw(img)

# ── Rounded background card ────────────────────────────────────────────────────
card_margin = 48
card = [card_margin, card_margin, SIZE - card_margin, SIZE - card_margin]
d.rounded_rectangle(card, radius=48, fill="#2B2B2B")

# ── Envelope body ─────────────────────────────────────────────────────────────
ex, ey = 120, 170
ew, eh = 272, 190
d.rounded_rectangle([ex, ey, ex + ew, ey + eh], radius=12, fill=WHITE)

# Envelope flap (triangle)
flap = [(ex, ey), (ex + ew, ey), (ex + ew // 2, ey + 90)]
d.polygon(flap, fill=ACCENT)

# Envelope fold lines (V crease at bottom of flap)
mid_x = ex + ew // 2
d.line([(ex, ey + eh), (mid_x, ey + 95)], fill=GRAY, width=2)
d.line([(ex + ew, ey + eh), (mid_x, ey + 95)], fill=GRAY, width=2)

# ── "N" badge (Notion mark) ────────────────────────────────────────────────────
bx, by, br = 340, 160, 44
d.ellipse([bx - br, by - br, bx + br, by + br], fill=WHITE)
# Draw N manually with lines
nx, ny = bx - 18, by - 22
d.line([(nx, ny + 44), (nx, ny)], fill=BG, width=7)
d.line([(nx, ny), (nx + 36, ny + 44)], fill=BG, width=7)
d.line([(nx + 36, ny + 44), (nx + 36, ny)], fill=BG, width=7)

# ── Label ─────────────────────────────────────────────────────────────────────
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
except OSError:
    font = ImageFont.load_default()
    small = font

label = "Email Analyzer"
bbox = d.textbbox((0, 0), label, font=font)
lw = bbox[2] - bbox[0]
d.text(((SIZE - lw) // 2, 390), label, font=font, fill=WHITE)

sub = "× Notion"
bbox2 = d.textbbox((0, 0), sub, font=small)
sw = bbox2[2] - bbox2[0]
d.text(((SIZE - sw) // 2, 428), sub, font=small, fill=GRAY)

# ── Save ──────────────────────────────────────────────────────────────────────
out = "logo.webp"
img.save(out, "WEBP", quality=90)
print(f"Saved {out}")
