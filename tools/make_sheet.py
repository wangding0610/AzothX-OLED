from PIL import Image
import pages, time

# ?????? + ????????3x?
tiles = []
for name, img in [
    ("clock", pages.clock()),
    ("stats", pages.stats()),
    ("net", pages.net()),
    ("pomodoro", pages.pomodoro(18*60+42, 25*60)),
]:
    img.save(f"page_{name}.png")
    tiles.append(img)

S = 3
gap = 8
sheet = Image.new("L", (pages.W*S, (pages.H*S+gap)*len(tiles)), 25)
for i, t in enumerate(tiles):
    sheet.paste(t.resize((pages.W*S, pages.H*S), Image.NEAREST), (0, i*(pages.H*S+gap)))
sheet.save("pages_sheet.png")
print("pages_sheet.png", sheet.size)
