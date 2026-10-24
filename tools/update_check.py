"""
Vérifie le système de mise à jour contre un FAUX serveur GitHub local (rien n'est téléchargé sur internet).

    python tools/update_check.py
"""
import hashlib
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

NEW_EXE = b"MZ" + os.urandom(300_000)
STATE = {"mode": "ok", "body": "- Anti-spam\n- Corrections", "tag": "v9.9.9"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, data, ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_port}"
        if self.path == "/repos/moi/depot/releases/latest":
            assets = [{"name": "AUTO_FISHER.exe", "browser_download_url": base + "/dl/exe", "size": len(NEW_EXE)}]
            if STATE["mode"] != "nosha":
                assets.append({"name": "AUTO_FISHER.exe.sha256", "browser_download_url": base + "/dl/sha"})
            if STATE["mode"] == "noassets":
                assets = []
            self._send(200, json.dumps({"tag_name": STATE["tag"], "body": STATE["body"], "assets": assets}).encode())
        elif self.path == "/repos/moi/vide/releases/latest":
            self._send(404, b"{}")
        elif self.path == "/repos/moi/limite/releases/latest":
            self._send(403, b"{}")
        elif self.path == "/dl/exe":
            data = NEW_EXE if STATE["mode"] != "tamper" else NEW_EXE[:-1] + b"X"
            self._send(200, data, "application/octet-stream")
        elif self.path == "/dl/sha":
            self._send(200, (hashlib.sha256(NEW_EXE).hexdigest() + "  AUTO_FISHER.exe\n").encode(), "text/plain")
        else:
            self._send(404, b"")


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["AUTO_FISHER_API"] = f"http://127.0.0.1:{srv.server_port}"
from config import updater as U   # noqa: E402

ok_all = True
def check(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("OK  " if cond else "KO  ") + name + (f"  {extra}" if extra else ""))

# --- versions
check("comparaison de versions", U.is_newer("v2.10.0", "2.9.9") and not U.is_newer("2.1", "2.1.0")
      and not U.is_newer("2.0.0", "2.1.0") and U.is_newer("3", "2.9.9"))
# --- vérification
st, info = U.check("moi/depot", "2.1.0")
check("version plus récente détectée", st == "available" and info.version == "9.9.9", getattr(info, "version", info))
check("notes de version lues, pas obligatoire", "Anti-spam" in info.notes and not info.mandatory)
check("déjà à jour", U.check("moi/depot", "9.9.9")[0] == "uptodate")
STATE["body"] = "Faille corrigée.\n[OBLIGATOIRE]"
check("marqueur [OBLIGATOIRE] reconnu", U.check("moi/depot", "2.1.0")[1].mandatory)
STATE["body"] = "- ok"
check("dépôt non configuré", U.check("", "2.1.0")[0] == "disabled" and U.check("pasbon", "1")[0] == "disabled")
st, msg = U.check("moi/vide", "2.1.0"); check("aucune release publiée : message clair", st == "error" and "publiée" in msg, msg)
st, msg = U.check("moi/limite", "2.1.0"); check("limite GitHub : message clair", st == "error" and "limite" in msg, msg)
STATE["mode"] = "noassets"; st, msg = U.check("moi/depot", "2.1.0")
check("release sans fichier (build pas fini) : message clair", st == "error" and "pas encore prêt" in msg, msg)
STATE["mode"] = "nosha"; st, msg = U.check("moi/depot", "2.1.0")
check("release sans empreinte : refusée", st == "error", msg)
STATE["mode"] = "ok"
os.environ["AUTO_FISHER_API"] = "http://127.0.0.1:1"            # personne n'écoute : hors ligne
st, msg = U.check("moi/depot", "2.1.0"); check("hors ligne : pas de plantage, message clair", st == "error" and "connexion" in msg, msg)
os.environ["AUTO_FISHER_API"] = f"http://127.0.0.1:{srv.server_port}"

# --- téléchargement
st, info = U.check("moi/depot", "2.1.0")
d = tempfile.mkdtemp(); dest = os.path.join(d, "AUTO_FISHER.exe.new"); prog = []
U.download(info, dest, progress=prog.append, require_pe=True)
check("téléchargement + empreinte valides", open(dest, "rb").read() == NEW_EXE and prog and prog[-1] == 1.0)
STATE["mode"] = "tamper"; dest2 = os.path.join(d, "x.new")
try:
    U.download(info, dest2, require_pe=True); bad = False
except U.UpdateError as e:
    bad = "corrompu" in str(e)
check("fichier FALSIFIÉ refusé et supprimé", bad and not os.path.exists(dest2))
STATE["mode"] = "ok"
# --- hôte interdit (comportement réel, sans l'override de test)
del os.environ["AUTO_FISHER_API"]
evil = U.UpdateInfo("9", "", False, "https://evil.example.com/a.exe", "https://evil.example.com/a.sha256")
try:
    U.download(evil, os.path.join(d, "e.new")); refused = False
except U.UpdateError:
    refused = True
check("hôte non-GitHub refusé", refused and not U._allowed("http://github.com/x") and U._allowed("https://github.com/x")
      and U._allowed("https://objects.githubusercontent.com/x"))

# --- remplacement et retour arrière
cur = os.path.join(d, "AUTO_FISHER.exe"); open(cur, "wb").write(b"MZ-ANCIEN")
new = os.path.join(d, "AUTO_FISHER.exe.new"); open(new, "wb").write(b"MZ-NOUVEAU")
old = U.install(new, cur)
check("remplacement : nouvelle version en place, ancienne gardée en .old",
      open(cur, "rb").read() == b"MZ-NOUVEAU" and open(old, "rb").read() == b"MZ-ANCIEN")
open(new, "wb").write(b"MZ-V3"); real = os.replace; calls = {"n": 0}
def flaky(a, b):
    calls["n"] += 1
    if calls["n"] == 2: raise OSError("verrouillé")
    return real(a, b)
os.replace = flaky
try:
    U.install(new, cur); rolled = False
except U.UpdateError:
    rolled = True
finally:
    os.replace = real
check("échec en cours de route : retour à l'ancienne version", rolled and open(cur, "rb").read() == b"MZ-NOUVEAU")
print("\nTOUT OK" if ok_all else "\nECHEC")
sys.exit(0 if ok_all else 1)
