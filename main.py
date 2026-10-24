"""
AUTO FISHER 2.0 — point d'entrée
Structure :
  bot/          moteur, capture, clavier
  detection/    cercle, zone bleue, trait, touche
  interface/    UI CustomTkinter
  config/       paramètres
  assets/       sons, icônes
  templates/    images de référence (touches, raretés)
  tools/        utilitaires
"""
from __future__ import annotations

import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main():
    from config.settings import ensure_default_templates
    ensure_default_templates()
    from interface.app import run
    run()


if __name__ == "__main__":
    main()
