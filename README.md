# rice-repo

Configuration Hyprland sur Arch Linux, construite au-dessus des dotfiles
[JaKooLit](https://github.com/JaKooLit/Hyprland-Dots) et étendue avec quatre
applications GTK4 maison.

Le principe qui gouverne tout le dépôt : **aucune couleur n'est écrite en dur.**
Le fond d'écran détermine la palette, et tout le reste s'y aligne
automatiquement — barre, panneaux, lanceur, terminal, notifications.

---

## Les quatre applications

Écrites en Python + GTK4 / libadwaita, bilingues français / anglais avec
sélecteur de langue, et thémées par la palette du système.

| | Raccourci | Rôle |
|---|---|---|
| **HyprSettings** | `Super + Maj + K` | Panneau de réglages : espacements, décoration, flou, barre, souris et clavier |
| **HyprKeys** | `Super + Maj + /` | Éditeur graphique des raccourcis — capture la combinaison de touches à la volée |
| **HyprWhale** | clic sur la baleine | Menu Docker : conteneurs, démarrage/arrêt, terminal, journaux |
| **CheatSheet** | `Super + /` | Liste filtrable des raccourcis dans rofi |

### HyprSettings

Chaque curseur s'applique **en direct** via `hyprctl keyword` ; rien n'est écrit
sur disque tant qu'on n'a pas cliqué sur *Enregistrer*. Il écrit dans quatre
fichiers différents selon le réglage — `looknfeel.conf`, `input.conf`, la config
waybar et sa feuille de style — en ne touchant que la valeur concernée.

### HyprKeys

Lit et réécrit `keybinds.conf` en préservant commentaires, ordre et mise en
forme. Le bouton de combinaison capture les touches réellement pressées et les
traduit en syntaxe Hyprland (`$mainMod SHIFT, S`).

### HyprWhale

Se rafraîchit toutes les 3 secondes en arrière-plan. Les couleurs d'état
(vert / ambre / rouge) sont **volontairement exclues** du thème : un conteneur
planté doit rester rouge même sous un accent vert.

Le menu contextuel `⋯` s'adapte à l'état — *Supprimer* est grisé sur un
conteneur actif, *Ouvrir localhost:port* sur un conteneur arrêté.

---

## Le thème réactif

`Super + W` ouvre le sélecteur de fond d'écran. Une fois l'image choisie,
[matugen](https://github.com/InioX/matugen) en extrait une palette Material You
et régénère **onze fichiers**, puis prévient chaque application concernée :

| Cible | Fichier généré | Signal envoyé |
|---|---|---|
| waybar | `waybar/colors.css` | `pkill -SIGUSR2 waybar` |
| hyprland | `hypr/colors.conf` | `hyprctl reload` |
| kitty | `kitty/colors.conf` | `kill -SIGUSR1 $(pidof kitty)` |
| GTK 3 et 4 | `gtk-*/colors.css` | `pkill -SIGUSR1 -f HyprWhale.py` |
| vicinae | `themes/matugen.toml` | `vicinae theme set matugen` |
| rofi, cava, spicetify, vesktop | — | — |

Les applications GTK héritent de la palette parce que `gtk-3.0/gtk.css` et
`gtk-4.0/gtk.css` importent le `colors.css` que matugen écrit. **Sans ces deux
fichiers d'une ligne, matugen génère les couleurs mais GTK ne les lit jamais** —
c'est le piège le plus discret de toute cette configuration.

---

## Raccourcis

### Fenêtres

| | |
|---|---|
| `Super + Q` | Fermer |
| `Super + Maj + Q` | Tuer le processus |
| `Super + Espace` | Flottant ↔ tuilé |
| `Super + Maj + F` | Plein écran |
| `Super + J` | Inverser le sens de découpe |
| `Super + ← ↑ ↓ →` | Déplacer le focus |
| `Super + Ctrl + ← ↑ ↓ →` | Déplacer la fenêtre |
| `Super + Maj + ← ↑ ↓ →` | Redimensionner |

### Applications

| | |
|---|---|
| `Alt + Espace` | Lanceur Vicinae |
| `Super + Entrée` | Terminal |
| `Super + Maj + Entrée` | Terminal flottant |
| `Super + E` | Thunar |
| `Super + Maj + E` | Yazi |
| `Super + B` | Navigateur |
| `Super + C` | Pipette à couleur |
| `Super + Maj + S` | Capture — enregistrée **et** copiée dans le presse-papier |
| `Super + L` | Verrouillage |
| `Ctrl + Alt + Suppr` | Quitter Hyprland |

### Apparence

| | |
|---|---|
| `Super + W` | Fond d'écran + régénération de la palette |
| `Super + Ctrl + B` | Style de la waybar |
| `Super + Alt + B` | Disposition de la waybar |
| `Super + R` | Redémarrer waybar et swaync |
| `Super + H` | Masquer la barre |

### Espaces de travail

`Super + 1…0` pour naviguer, `Super + Maj + 1…0` pour y envoyer la fenêtre,
`Super + molette` pour défiler, trois doigts horizontalement sur le pavé tactile.

---

## Dépendances

```bash
sudo pacman -S --needed \
  hyprland waybar rofi kitty swaync hyprlock hypridle hyprpolkitagent \
  awww matugen-bin thunar yazi \
  gnome-keyring seahorse \
  brightnessctl hyprpicker playerctl wl-clipboard grim slurp \
  blueman network-manager-applet pavucontrol nwg-displays mission-center \
  docker docker-compose docker-buildx lazydocker \
  python-gobject gtk4 libadwaita \
  ttf-jetbrains-mono-nerd noto-fonts-emoji fastfetch btop
```

```bash
yay -S vicinae-bin
```

Docker demande deux étapes de plus :

```bash
sudo systemctl enable --now docker.socket
sudo usermod -aG docker $USER
```

Puis **redémarrer**. Une simple déconnexion ne suffit pas : le gestionnaire
`user@1000.service` survit à la fermeture de session et conserve les groupes
qu'il avait au démarrage.

---

## Installation

```bash
git clone <url-du-depot> ~/.rice-repo
cd ~/.rice-repo && ./install.sh
```

`install.sh` crée un lien symbolique dans `~/.config` pour chaque fichier du
dépôt, en sauvegardant ce qu'il remplace sous `~/.config-backup-<date>`.

Les fichiers ne sont **jamais copiés** : `~/.config/hypr/hyprland.conf` est un
lien vers `~/.rice-repo/config/hypr/hyprland.conf`. Éditer l'un ou l'autre
revient au même, et `git status` voit les modifications immédiatement.

---

## Structure

```
config/
├── hypr/
│   ├── hyprland.conf          autostart, moniteur, sources
│   ├── configs/               keybinds, windowrules, tags, looknfeel, input, animations
│   └── scripts/               les quatre applications + capture, wallpaper
├── waybar/
│   ├── UserModules            modules Docker et curseur de luminosité
│   ├── Modules                définitions de base (tray, mpris, backlight…)
│   ├── configs/               dispositions de barre
│   └── style/                 feuilles de style
├── matugen/                   chaîne de génération de palette
├── swaync/themes/             centre de notifications
└── gtk-3.0, gtk-4.0/          les deux lignes qui branchent GTK sur matugen
```

---

## Notes

Quelques pièges rencontrés en construisant cette configuration, gardés ici parce
qu'ils ne sont écrits nulle part ailleurs.

**Hyprland 0.56 a changé la syntaxe des règles de fenêtres.** `class:^(kitty)$`
devient `match:class ^(kitty)$`, `float` devient `float true`, `ignorealpha`
devient `ignore_alpha`, et `ignorezero` n'existe plus. Le format `.conf` lui-même
disparaîtra en 0.57 au profit du Lua.

**Le paquet `swww` a été renommé `awww`.** Les configurations qui appellent
encore `swww-daemon` échouent en silence.

**matugen 4.x** refuse de choisir entre plusieurs couleurs candidates sans
terminal interactif : `--prefer saturation` est obligatoire depuis un raccourci.
Il a aussi abandonné `arguments = [...]` dans `[config.wallpaper]` au profit
d'une commande unique contenant `{{ image }}`.

**Hyprland agrandit les fenêtres flottantes autour de leur centre.** Un popup qui
grandit remonte donc hors de l'écran. HyprWhale corrige en réancrant son coin
haut-gauche à chaque image, via la socket IPC (0,16 ms) plutôt que `hyprctl`
(10 ms).

**GTK agrandit une fenêtre mappée mais ne la rétrécit jamais.**
`set_default_size` n'a aucun effet après l'affichage ; il faut demander la
retaille au compositeur avec la hauteur que `measure()` renvoie.

**Les glyphes Nerd Font vivent dans la zone privée Unicode.** Une espace
parasite après un glyphe (`" "`) décale visiblement l'icône dans sa bulle.
