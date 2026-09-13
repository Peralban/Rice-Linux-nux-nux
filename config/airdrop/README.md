# AirDrop

AirDrop depuis Arch vers/depuis un iPhone, via
[airdrop-mt7921](https://github.com/jedbillyb/airdrop-mt7921) piloté par
l'onglet AirDrop du notch.

Le dépôt amont est cloné dans `~/.local/share/airdrop-mt7921`, **qui n'est pas
versionné ici**. Tout ce dossier existe donc pour une seule raison : un
`git pull` là-bas écrase les correctifs, et il faut pouvoir les remettre.

## État

| | |
|---|---|
| Réception | 12/12 fichiers vérifiés valides, photos jusqu'à ~7 Mo |
| Envoi | ne marche pas — l'iPhone ne s'annonce jamais en receveur |
| Wi-Fi | jamais coupé (mode P2P-GO) |

Matériel : MT7922 `[14c3:0616]`, driver `mt7921e` — l'amont n'a testé que le
MT7921.

## Remettre les correctifs après un `git pull` amont

```sh
cd ~/.local/share/airdrop-mt7921
git apply ~/.rice-repo/config/airdrop/patches/00-local-changes.patch
sudo install -o root -g root -m 755 daemon/airdrop-helper /usr/local/bin/airdrop-helper
```

Puis, dans le venv d'opendrop (lui non plus n'est pas versionné) :

```sh
cd ~/owl/.venv-opendrop/lib/python3.*/site-packages
patch -p1 -i ~/.rice-repo/config/airdrop/patches/opendrop-zeroconf-update-service.patch
patch -p1 -i ~/.rice-repo/config/airdrop/patches/opendrop-salvage-truncated.patch
```

Et dans le clone d'owl (`~/owl`, pas versionné non plus) :

```sh
cd ~/owl
git apply ~/.rice-repo/config/airdrop/patches/owl-overlap-under-widen.patch
make -C build owl
sudo install -o root -g root -m 755 build/daemon/owl /usr/local/bin/airdrop-owl
```

`config.example` va dans `~/.config/airdrop/config`.

## Ce que corrigent ces patches

**`00-local-changes.patch`** — trois choses dans le dépôt amont :

- `PHY` était codé en dur à `phy0` dans `airdrop-helper`, alors que
  `airdrop.sh` le dérive correctement de l'interface. Après un rechargement du
  driver la carte revient en `phy1` et `iw phy phy0 interface add` sort en
  ENOENT, que le démon rapporte comme un problème de sudoers.
- `MT76` était calculé **avant** `PHY`, donc le chemin contenait un trou
  (`ieee80211//mt76`) et les contournements `runtime-pm`/`deep-sleep` étaient
  sautés en silence — exactement la panne « le monitor ne capture rien » que
  l'amont documente.
- Le hook de consentement n'acceptait que `swaynag`, absent sous Hyprland : il
  refusait donc tous les transferts. Porté sur `hyprland-dialog`, qui écrit le
  bouton choisi sur stdout et supprime toute la mécanique de fichiers-marqueurs.

**`opendrop-zeroconf-update-service.patch`** — `AirDropBrowser` n'avait pas de
`update_service`, obligatoire depuis python-zeroconf 0.3x. L'exception était
levée *dans* le thread du ServiceBrowser et le tuait : plus aucune découverte
ensuite. Et c'est un appareil qui se réannonce — donc précisément la cible
cherchée — qui déclenche un `update` plutôt qu'un `add`.

**`opendrop-salvage-truncated.patch`** — le plus utile des trois.

Un transfert interrompu était intégralement jeté. Mesure sur 17 transferts
interrompus : **13 contenaient déjà le fichier complet** et ne perdaient que le
terminateur du conteneur ; le JPEG extrait était identique au sha256 près.

Le patch récupère ces octets, et surtout **vérifie** ce qu'il rend. La
vérification marche la structure du cpio ODC à la main, parce que libarchive
**complète à zéro** un membre tronqué jusqu'à sa taille annoncée : un fichier
de la bonne taille peut se terminer par 949 265 octets nuls. Comparer les
tailles ne détecte donc rien. Ce qui est incomplet est suffixé `.partial` —
livrer en silence une photo à moitié vide qui s'ouvre quand même serait pire
qu'un échec franc.

Il ajoute aussi un délai d'expiration sur **toutes** les lectures de socket, pas
seulement sur `/Upload` : `_next_chunk` bloquait dans `readline()` sans limite,
donc un téléphone qui se tait figeait la boucle pour toujours et même les octets
déjà reçus restaient dans le tampon. Le délai est posé en attribut de classe du
handler, parce que `handle_ask` lit son corps de requête **avant** d'appeler le
hook de consentement : un téléphone qui se taisait là bloquait sans fenêtre de
confirmation et sans une ligne de journal. C'était exactement la « vidéo
refusée » vue pendant les essais.

**`owl-overlap-under-widen.patch`** — owl ne mesurait le recouvrement de
canaux que dans la branche `intersect`. La ligne de santé `CHAN` du démon lit
ces lignes-là : passer en `widen` la rendait donc muette, `overlap=0/16` en
permanence, alors que les transferts passaient. L'indicateur était éteint par
le réglage même qu'on voulait surveiller — et j'ai diagnostiqué dessus deux
fois. Le patch compte le recouvrement aussi sous `widen` (il ne change rien à
ce qui est annoncé : élargir modifie la séquence émise, pas la position de la
radio, que le chanctx du GO tient sur un canal — donc la réponse est la même
sous toutes les stratégies). Le compagnon côté démon accepte les deux
étiquettes, `intersect:` et `overlap:`, il est dans `00-local-changes.patch`.

## Outils

- `tools/mdns-peek.py` — décode ce qui passe réellement sur le groupe mDNS
  d'`awdl0`. Distingue « le téléphone interroge » de « le téléphone s'annonce »,
  ce qu'un compteur de paquets confond.
- `tools/blewake-dbus.py` — annonce Continuity BLE via `bluetoothd` plutôt que
  `btmgmt`, et se réenregistre toutes les 3 s (la puce est un combo Wi-Fi/BT :
  reconfigurer la radio réinitialise le contrôleur et emporte l'annonce).
  N'a pas suffi à réveiller l'iPhone.
- `tools/ab-tally.sh` — compte démarrés/complets/bloqués pour comparer deux
  réglages.
- `tools/recv-tally.sh` — relit le journal d'opendrop et classe chaque transfert
  en direct / sauvé / partiel / perdu. C'est le chiffre du tableau d'état plus
  haut ; il ne se déduit pas du nombre de fichiers dans `~/Downloads`, où un
  `.dvzip` restant peut aussi bien contenir le fichier entier que rien.

## Mesuré, à ne pas refaire

- `intersect` (défaut amont) n'a **jamais** terminé un transfert ; `widen` en
  terminait environ un sur quatre *avant* le sauvetage, et les douze derniers
  après. La justification théorique du commentaire amont est démentie par la
  mesure.
- `rcv_space` est sain (~71 Ko) : le patch `recv-window` fonctionne, le tampon
  n'est pas le goulot.
- Le lien est marginal : `cwnd=2`, RTT 408 ms, gigue 772 ms, ~33 % de
  retransmissions — conséquence du partage d'une seule radio entre la station
  et AWDL.
- Le suffixe `~stale` de la ligne `CHAN` signifie qu'on **chevauche** le pair :
  c'est la branche saine. Il marque le canal du pair comme non réactualisé,
  parce qu'owl ne le rapporte que lorsqu'il n'y a plus de recouvrement. Lu
  comme « lien mort », il fait redémarrer une pile qui marchait.
- Le débit se dégrade avec le temps sur une même pile : ~50 ko/s en début de
  série, ~8 ko/s une heure plus tard. Au-delà de ~10 Mo le transfert ne tient
  pas dans la fenêtre de dix minutes du réglage *Tout le monde*.
- `airdrop.sh` laisse un `owl` orphelin quand il est interrompu, et le run
  suivant meurt sur `Could not open device: awdl0`.
- NetworkManager prend `go0` en charge et lui donne la route par défaut via
  DHCP, ce qui éjecte la station. D'où
  `/etc/NetworkManager/conf.d/99-airdrop-unmanaged.conf`.
