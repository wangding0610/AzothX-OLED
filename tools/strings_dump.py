"""Extract ASCII and UTF-16LE strings from a binary into a UTF-8 text file."""
import re
import sys

ASCII_RE = re.compile(rb"[\x20-\x7e]{4,}")
UTF16_RE = re.compile(rb"(?:[\x20-\x7e]\x00){4,}")


def main(path, out):
    data = open(path, "rb").read()
    lines = []
    for m in ASCII_RE.finditer(data):
        lines.append(f"{m.start():08x} A  {m.group().decode('ascii', 'replace')}")
    for m in UTF16_RE.finditer(data):
        lines.append(f"{m.start():08x} W  {m.group().decode('utf-16-le', 'replace')}")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(f"# {path}\n")
        fh.write("\n".join(lines))
    print(f"{path}: {len(lines)} strings -> {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
