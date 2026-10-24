"""
Fabrique AUTO_FISHER.exe : UN seul fichier, sans Python ni dossier à installer chez l'utilisateur.
Lancé par build_exe.bat (ou : python tools/build_exe.py).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

import PyInstaller.__main__  # noqa: E402

sep = os.pathsep
args = [
    "--noconfirm", "--clean",
    "--onefile",                    # un seul fichier
    "--windowed",                   # pas de fenêtre de terminal
    "--name", "AUTO_FISHER",
    "--distpath", os.path.join(ROOT, "dist"),
    "--workpath", os.path.join(ROOT, "build"),
    "--specpath", os.path.join(ROOT, "build"),
    "--collect-all", "customtkinter",
    "--hidden-import", "PIL._tkinter_finder",
    "--add-data", f"{os.path.join(ROOT, 'templates')}{sep}templates",     # lettres Z/Q/S/D
    "--add-data", f"{os.path.join(ROOT, 'assets')}{sep}assets",           # icône
    "--exclude-module", "matplotlib", "--exclude-module", "pandas", "--exclude-module", "scipy",
]
if sys.platform == "win32":
    args += ["--icon", os.path.join(ROOT, "assets", "auto_fisher.ico")]
args.append(os.path.join(ROOT, "main.py"))
PyInstaller.__main__.run(args)
