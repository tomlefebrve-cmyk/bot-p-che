# 🎃 FishBot - Bot de Pêche GTA RP

<div align="center">

![Version](https://img.shields.io/badge/version-2.0.0-orange?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python)
![Platform](https://img.shields.io/badge/Windows%20%7C%20macOS-black?style=for-the-badge)

**Bot de pêche automatique avec interface Halloween**

</div>

---

## ✨ Aperçu

Interface moderne thème Halloween avec tableau de bord complet :

- 🎃 **Tableau de bord** en temps réel
- 🐟 Compteur de poissons pêchés
- 🎯 Contrôle du bot (Démarrer / Arrêter)
- ⚙️ Paramètres de pêche personnalisables
- 📜 Journal d'activité
- 🎒 Inventaire

---

## 🚀 Installation

### 1. Télécharger
Télécharge la dernière version depuis les **Releases** ou clone le repo :

```bash
git clone https://github.com/tomlefebrve-cmyk/bot-p-che.git
cd bot-p-che
```

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 3. Lancer le bot

**Windows :**
```bash
start.bat
```
ou
```bash
python main.py
```

**macOS / Linux :**
```bash
chmod +x start.sh
./start.sh
```

---

## 🎮 Utilisation

1. Lance ton jeu **GTA RP** en mode fenêtré ou borderless
2. Ouvre **FishBot**
3. Configure tes paramètres de pêche (lieu, appât, intervalle...)
4. Clique sur **▶ Démarrer**
5. Laisse le bot pêcher pour toi 🎣

### Raccourcis
| Touche | Action          |
|--------|-----------------|
| `F8`   | Start / Stop    |
| `F7`   | Afficher panneau|

---

## ⚙️ Configuration

Tu peux modifier le fichier `user_config.json` pour ajuster :
- Intervalle entre les lancers
- Quantité d'appâts
- Mode de pêche
- etc.

---

## 📁 Structure du projet

```
autofisher/
├── main.py              # Point d'entrée
├── config.py            # Configuration
├── user_config.json     # Config utilisateur
├── requirements.txt     # Dépendances
├── start.bat / start.sh # Scripts de lancement
├── core/                # Logique principale
├── detection/           # Détection (cercle, touches...)
├── ui/                  # Interface graphique
├── templates/           # Images de détection
└── assets/              # Ressources (sons, images)
```

---

## 🛠️ Prérequis

- Python **3.10** ou supérieur
- Windows 10/11 (recommandé) ou macOS
- Droits **Accessibilité** + **Enregistrement d'écran** (macOS)

---

## 📝 Notes

- Le bot fonctionne mieux en **fenêtré** ou **borderless**
- Évite le plein écran exclusif
- Pense à calibrer les couleurs si la détection est mauvaise

---

<div align="center">

**Fait avec 🎃 par [tomlefebrve-cmyk](https://github.com/tomlefebrve-cmyk)**

</div>
