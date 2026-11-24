"""Cari versi macOS minimum yang dibutuhkan sebuah .app (nilai terbesar dari semua biner di dalamnya).

Pemakaian: python tools/macos_min_version.py "dist/Koreksi LJK.app" [--set-plist]
--set-plist menulis LSMinimumSystemVersion ke Info.plist, supaya macOS yang terlalu lama
menampilkan pesan yang jelas, bukan crash.
"""
import os
import re
import subprocess
import sys
from pathlib import Path


def is_macho(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            m = f.read(4)
    except OSError:
        return False
    return m in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca")


def min_versions(p: Path):
    out = subprocess.run(["otool", "-l", str(p)], capture_output=True, text=True).stdout
    vers = []
    lines = out.splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if line in ("cmd LC_BUILD_VERSION", "cmd LC_VERSION_MIN_MACOSX"):
            for nxt in lines[i + 1:i + 6]:
                m = re.match(r"\s*(minos|version)\s+([\d.]+)", nxt)
                if m:
                    vers.append(tuple(int(x) for x in m.group(2).split(".")))
                    break
    return vers


def main():
    app = Path(sys.argv[1])
    found = []
    for root, _, files in os.walk(app):
        for n in files:
            p = Path(root) / n
            if p.is_symlink() or not is_macho(p):
                continue
            for v in min_versions(p):
                found.append((v, p.relative_to(app)))
    if not found:
        print("tidak ada biner Mach-O"); return
    found.sort(reverse=True)
    top = found[0][0]
    ver = ".".join(map(str, top[:2] if len(top) > 1 else top))
    print(f"macOS minimum: {ver}")
    for v, p in found[:8]:
        print(f"  {'.'.join(map(str, v))}  {p}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"### {app.name}: macOS minimum **{ver}**\n\n")
            for v, p in found[:8]:
                f.write(f"- {'.'.join(map(str, v))} — `{p}`\n")
    if "--set-plist" in sys.argv:
        plist = app / "Contents" / "Info.plist"
        subprocess.run(["plutil", "-replace", "LSMinimumSystemVersion", "-string", ver, str(plist)], check=True)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"minos={ver}\n")


if __name__ == "__main__":
    main()
