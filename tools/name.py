"""Final name card for the ROG Azoth X OLED: 208x64, 4bpp, two frames."""
import time

from PIL import Image, ImageDraw

from oled import RogOled, _font, crisp, dongle_pairing, render_4bpp

W, H = 208, 64
LINES = ["LITTLE CODE", "SAUCE"]


def compose(lines, width, height, thresh=140):
    img = Image.new("L", (width, height), 0)
    d = ImageDraw.Draw(img)
    line_h = height // len(lines)
    y = 0
    for text in lines:
        size = line_h + 2
        while size > 6:
            f = _font(size)
            b = d.textbbox((0, 0), text, font=f)
            if b[2] - b[0] <= width - 2 and b[3] - b[1] <= line_h:
                break
            size -= 1
        f = _font(size)
        b = d.textbbox((0, 0), text, font=f)
        d.text(((width - (b[2] - b[0])) // 2 - b[0],
                y + (line_h - (b[3] - b[1])) // 2 - b[1]), text, 255, font=f)
        y += line_h
    return crisp(img, thresh)


img = compose(LINES, W, H)
img.save("preview.png")
img.resize((W * 6, H * 6), Image.NEAREST).save("preview_zoom.png")

payload = bytearray()
frames = 2
payload += frames.to_bytes(2, "little")
for _ in range(frames):
    payload += (1000).to_bytes(2, "little")
payload += render_4bpp(img, W, H) * frames
print(f"{W}x{H} 4bpp, {len(payload)} bytes -> {(len(payload) + 58) // 59} packets")

pairing = dongle_pairing()
rid = pairing["ctrl_report_id"] if pairing else 2
for attempt in range(1, 4):
    dev = RogOled(0xFF00, rid, chunk=59 if pairing else 60, verbose=False, wait_link=20)
    try:
        dev.animation_upload(bytes(payload))
        print("done")
        break
    except Exception as exc:  # noqa: BLE001
        print("  aborted:", exc)
        time.sleep(2)
    finally:
        dev.close()
