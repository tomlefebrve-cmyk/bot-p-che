# AUTO FISHER (FishBot)

Assistant pour le mini-jeu de pêche (FiveM) + auto-clic.

## Pour l'utilisateur final
Voir `LISEZMOI.txt` : double-clic sur `AUTO_FISHER.exe`, rien à installer.

## Fabriquer AUTO_FISHER.exe (une seule fois, sur Windows)
- **Avec Python installé** : double-clic sur `build_exe.bat` → `AUTO_FISHER.exe` apparaît à la racine.
- **Sans rien installer** : pousse le projet sur GitHub, onglet *Actions* → *Fabriquer AUTO_FISHER.exe*
  → *Run workflow*, puis télécharge l'exe dans *Artifacts*.

Le .exe est un seul fichier. Réglages et templates sont dans `%APPDATA%\AUTO_FISHER`.
Au premier lancement il crée un raccourci « AUTO FISHER » sur le bureau.

## Mises à jour automatiques
Versions publiées sur GitHub Releases : l'exe est fabriqué par GitHub (`.github/workflows/build-exe.yml`),
le logiciel propose la mise à jour (bouton, jamais silencieux), vérifie l'empreinte SHA-256 puis se remplace.
Mode d'emploi complet : `PUBLIER_UNE_MISE_A_JOUR.txt`. À remplir : `UPDATE_REPO` dans `config/version.py`.

## Lancer depuis les sources
```bash
pip install -r requirements.txt
python main.py
```

## Fonctions
- **Pêche** : lit la lettre (Z/Q/S/D) avec les templates de `templates/keys/` (forme + vote sur
  plusieurs images, refuse de deviner si deux lettres se ressemblent), suit l'arc et le curseur,
  appuie quand le curseur est sur l'arc. Trois dispositions de couleurs : arc bleu/curseur rouge,
  rouge/rouge (séparés par le mouvement), arc rouge/curseur bleu.
- **Calibration automatique** (page Pêche) : trouve le cercle, la disposition et les couleurs
  réelles de TON écran, et les enregistre.
- **Fenêtre debug** (tableau de bord) : image capturée en direct avec cercle, lettre, arc, curseur.
- **Touches** : envoyées selon la disposition réelle du clavier (AZERTY compris). `pydirectinput` seul
  envoie des positions QWERTY : Z et Q partaient sur W et A. Bouton « Tester les touches » (page Pêche).
- **Anti-spam** (réglable, activé par défaut) : n'appuie que sur un vrai mini-jeu (arc stable, lettre
  confirmée, curseur qui avance régulièrement, re-vérifié juste avant l'appui), limite les appuis
  (`anti_spam_max` par `anti_spam_window_s`), ralentit puis fait une pause après des échecs en série.
- **Pause automatique** (pêche et auto-clic) : marche X s / pause Y s, en boucle.
- **Auto-clic** : intervalle h/min/s/ms, infini ou N clics, bouton gauche/droit, position actuelle ou
  X/Y (choix d'un point à l'écran), raccourcis clavier modifiables. Arrêt immédiat, sans clic en trop.

## Vérifications sans le jeu
```bash
python tools/sim_check.py [red|blue]   # faux mini-jeu + vrai moteur de pêche
python tools/autocal_check.py          # calibration auto sur 6 « écrans » de couleurs différentes
python tools/clicker_check.py          # auto-clic : intervalle, nombre de clics, pause auto, arrêt immédiat
python tools/antispam_check.py         # faux mini-jeux : le bot ne doit pas appuyer dans le vide
python tools/update_check.py           # mises à jour : faux serveur GitHub, falsification, retour arrière
python tools/keys_check.py             # Z/Q/S/D envoyées sur la bonne touche, AZERTY et QWERTY
```

## Réglages utiles (`user_config.json`)
`target_color` (`blue` / `red` / `red_blue`), `key_min_confidence` (0.75), `key_min_margin` (0.06),
`key_votes_needed` (2), `circle_fallback` (true), `key_send_mode` (`layout` / `classic`),
`cycle_enabled` / `cycle_run_s` / `cycle_pause_s`, `anti_spam` / `anti_spam_max` / `anti_spam_window_s` /
`anti_spam_pause_s` / `anti_spam_fail_limit`.
