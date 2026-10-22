from pathlib import Path
import datetime
import importlib.util
import sys
from PIL import Image, ImageChops, ImageDraw, ImageFont

root = Path.cwd()
out = root / 'evidence' / 'font-fix'
sys.path.insert(0, str(root / 'tools'))
import pages, oled

def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, out / 'before-source' / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

old_pages = load('old_pages', 'tools/pages.py')
old_oled = load('old_oled', 'tools/oled.py')
now = datetime.datetime(2026, 10, 22, 9, 14, 27)
old_image = old_pages.clock(now)
new_image = pages.clock(now)

def decode(data):
    return Image.frombytes('L', (208,64), bytes(v for b in data for v in ((b % 16)*17, (b // 16)*17)))

old_display = decode(old_oled.render_4bpp(old_image,208,64))
order_fixed = decode(oled.render_4bpp(old_image,208,64))
new_display = decode(oled.render_4bpp(new_image,208,64))
old_display.save(out / 'before-panel-simulation.png')
order_fixed.save(out / 'order-only-panel-simulation.png')
new_display.save(out / 'after-panel-simulation.png')
new_display.resize((1040,320),Image.Resampling.NEAREST).save(out / 'after-5x.png')
new_image.save(out / 'after.png')
font = ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf',18)
sheet = Image.new('RGB',(1040,3*355),(30,30,30))
d = ImageDraw.Draw(sheet)
for i,(label,img) in enumerate([
    ('OLD: device decode (neighboring pixels swapped)',old_display),
    ('FIX: corrected pixel order, same original font/style',order_fixed),
    ('FINAL: corrected pixel order + crisp text',new_display),
]):
    d.text((8,i*355+5),label,font=font,fill='white')
    sheet.paste(img.resize((1040,320),Image.Resampling.NEAREST),(0,i*355+30))
sheet.save(out / 'pixel-order-comparison.png')
quantized = old_image.point(lambda v:(v//16)*17)
wrong = sum(a != b for a,b in zip(old_display.tobytes(),quantized.tobytes()))
assert order_fixed.tobytes() == quantized.tobytes()
assert new_display.tobytes() == new_image.point(lambda v:(v//16)*17).tobytes()
print(f'Old device decode: {wrong} pixels differ from intended 4bpp image')
print('Corrected device decode: 0 pixels differ, for both soft and crisp')
