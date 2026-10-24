"""Écrit la version dans config/version.py :  python tools/set_version.py v2.1.0"""
import os
import re
import sys

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "version.py")
ver = sys.argv[1].lstrip("vV").strip()
if not re.fullmatch(r"\d+(\.\d+){0,3}", ver):
    sys.exit(f"Version invalide : {sys.argv[1]!r} (attendu : 2.1.0)")
s = open(path, encoding="utf-8").read()
s = re.sub(r'__version__ = "[^"]*"', f'__version__ = "{ver}"', s)
open(path, "w", encoding="utf-8").write(s)
print("version =", ver)
