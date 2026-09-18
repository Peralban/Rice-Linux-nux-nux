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
| Réception | 8/9 sur la dernière série, jusqu'à 10,3 Mo (`.pptx`, en direct) |
| Envoi | ne marche pas — l'iPhone ne s'annonce jamais en receveur |
| Wi-Fi | jamais coupé (mode P2P-GO) |

Matériel : MT7922 `[14c3:0616]`, driver `mt7921e` — l'amont n'a testé que le
MT7921.

## Remettre les correctifs après un `git pull` amont

Depuis le 15 septembre 2026, l'essentiel de ce qui vivait ici est **dans
l'amont** : la PR jedbillyb/airdrop-mt7921#1 a été mergée (`a08aae3`), avec la
dérivation du phy, l'ordre de `MT76`, la cascade de consentement et les deux
correctifs opendrop. Ce qui reste local tient en un seul correctif.

```sh
cd ~/.local/share/airdrop-mt7921
git apply ~/.rice-repo/config/airdrop/patches/00-local-changes.patch
sudo install -o root -g root -m 755 daemon/airdrop-helper /usr/local/bin/airdrop-helper
```

### Recréer le venv d'opendrop en partant de rien

Il n'est pas versionné, et c'est voulu : les deux correctifs ci-dessous le
décrivent exactement — `patch -R --dry-run` les ré-applique à l'envers sans
erreur, donc ils correspondent au code en place et rien ne se perd.

Cette machine n'a pas `pip` au niveau système, seulement `uv` :

```sh
uv venv --python 3.14 ~/owl/.venv-opendrop
uv pip install --python ~/owl/.venv-opendrop/bin/python opendrop==0.13.0
```

La version compte : les correctifs sont écrits contre **0.13.0**, et
`patch` refusera de s'appliquer sur une autre.

Puis, dans le venv d'opendrop :

```sh
cd ~/owl/.venv-opendrop/lib/python3.*/site-packages
patch -p1 -i ~/.rice-repo/config/airdrop/patches/opendrop-zeroconf-update-service.patch
patch -p1 -i ~/.rice-repo/config/airdrop/patches/opendrop-salvage-truncated.patch
patch -p1 -i ~/.rice-repo/config/airdrop/patches/opendrop-send-multifile.patch
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

**`00-local-changes.patch`** — une seule chose désormais, la **vérification
d'interfaces** dans la boucle de santé d'`airdropd`.

Elle ne vérifiait que les **processus**, jamais que leurs **interfaces**
existaient encore. owl continue de tourner sur un vif moniteur supprimé sous
lui sans un mot, `awdl0` survit comme une coquille sans radio derrière, et la
barre affiche `armed` devant une pile morte. Elle teste maintenant `awdl0`, le
moniteur qu'owl utilise réellement (`ackvif`) et, **en bi-canal seulement**,
`go0` — ce dernier point corrigé le 15 septembre, parce que `DUALCHAN` vaut la
chaîne `0` quand il est éteint, qui n'est pas vide : `${DUALCHAN:+go0}`
réclamait donc `go0` en mono-canal, où il n'existe jamais, et déclarait morte
une pile parfaitement vivante.

C'est l'issue Peralban/airdrop-mt7921#3 ; le reste de ce correctif est parti
en amont avec la PR #1.

Les deux correctifs opendrop qui suivent sont **en amont depuis la PR #1** ;
les copies gardées ici servent à reconstruire le venv, qui n'est pas le
clone. Elles sont reprises telles quelles de `patches/` amont, y compris la
correction du gzip tronqué que jedbillyb a ajoutée dans `2329e69`.

**`opendrop-zeroconf-update-service.patch`** — `AirDropBrowser` n'avait pas de
`update_service`, obligatoire depuis python-zeroconf 0.3x. L'exception était
levée *dans* le thread du ServiceBrowser et le tuait : plus aucune découverte
ensuite. Et c'est un appareil qui se réannonce — donc précisément la cible
cherchée — qui déclenche un `update` plutôt qu'un `add`.

**`opendrop-send-multifile.patch`** — un transfert au lieu de N.

Le protocole porte plusieurs fichiers dans un seul `/Ask` : `send_ask()`
construit déjà une entrée par fichier. Deux choses l'empêchaient d'arriver
jusque-là. La ligne de commande déclarait `-f` au singulier, et
`send_upload()` emballait son argument dans une liste d'un élément
(`for f in [file_path]`), donc même une vraie liste n'aurait pas traversé.

`-f` est maintenant répétable et `send_upload` accepte une chaîne ou une
liste, comme `send_ask`. Avec le changement correspondant dans `airdropd`,
cinq fichiers font un transfert et **une seule** demande d'acceptation sur le
téléphone, au lieu de cinq.

`-u` refuse toujours plus d'un fichier : un lien est un lien.

**`opendrop-salvage-truncated.patch`** — le plus utile des trois.

Un transfert interrompu était intégralement jeté. Mesure sur 17 transferts
interrompus : **9 contenaient déjà le fichier complet** et ne perdaient que le
terminateur du conteneur ; le JPEG extrait était identique au sha256 près.

Le patch récupère ces octets, et surtout **vérifie** ce qu'il rend. La
vérification marche la structure du cpio ODC à la main, parce que libarchive
**complète à zéro** un membre tronqué jusqu'à sa taille annoncée : un fichier
de la bonne taille peut se terminer par 949 265 octets nuls. Comparer les
tailles ne détecte donc rien. Ce qui est incomplet est suffixé `.partial` —
livrer en silence une photo à moitié vide qui s'ouvre quand même serait pire
qu'un échec franc.

**Le délai suit le rythme du lien**, il n'est pas constant. Un délai fixe de 30 s
s'ajoutait à chaque transfert sauvé — sur 43 s mesurées, trente étaient du vide.
Mais raccourcir bêtement couperait un transfert simplement lent. Premier essai,
abandonné : déclencher un palier court près de `TotalBytes`. Ça suppose que
l'expéditeur s'arrête au bord, ce qui est faux — mesuré, les arrêts vont de
440 octets à 943 642 octets avant la fin, soit 0,03 % à 24 %. Aucun seuil ne
couvre les deux.

Donc le code n'essaie plus de deviner où est la fin : il observe l'écart entre
deux lectures réussies et arme le délai à six fois le pire écart déjà vu, borné
entre 8 et 30 s. Un lien régulier tombe au plancher, un lien saccadé laisse le
délai monter seul. Vérifié en conditions réelles : `worst gap seen 3.2s` a donné
19 s d'attente au lieu de 30, sur un transfert de 6 Mo arrivé complet — et un
palier fixe de 8 s aurait coupé celui-là.

Il ajoute aussi un délai d'expiration sur **toutes** les lectures de socket, pas
seulement sur `/Upload` : `_next_chunk` bloquait dans `readline()` sans limite,
donc un téléphone qui se tait figeait la boucle pour toujours et même les octets
déjà reçus restaient dans le tampon. Le délai est posé en attribut de classe du
handler, parce que `handle_ask` lit son corps de requête **avant** d'appeler le
hook de consentement : un téléphone qui se taisait là bloquait sans fenêtre de
confirmation et sans une ligne de journal. C'était exactement la « vidéo
refusée » vue pendant les essais.

**Le cas gzip tronqué**, corrigé par jedbillyb dans `2329e69` après la revue.
La branche gzip décompressait avec `GzipFile.read()`, qui lève `EOFError` sur
un flux sans marqueur de fin — or un transfert coupé est exactement ça. La
vérification était donc **entièrement sautée** sur le cas même pour lequel le
sauvetage existe, et les membres bourrés de zéros par libarchive n'étaient
jamais renommés `.partial` : un fichier à moitié vide passait pour intact.
Remplacé par `zlib.decompressobj(16 + zlib.MAX_WBITS)`, qui rend tout ce qui
est arrivé sans lever. Rejoué ici sur un fichier de 300 Ko coupé à 60 % :
avant `EOFError` et rien de renommé, après 184 418 octets rendus et
`IMG_0001.JPG` reconnu incomplet.

**`owl-overlap-under-widen.patch`** — **à ne pas appliquer pour l'instant**, voir
la réserve à la fin de cette section. owl ne mesurait le recouvrement de
canaux que dans la branche `intersect`. La ligne de santé `CHAN` du démon lit
ces lignes-là : passer en `widen` la rendait donc muette, `overlap=0/16` en
permanence, alors que les transferts passaient. L'indicateur était éteint par
le réglage même qu'on voulait surveiller — et j'ai diagnostiqué dessus deux
fois. Le patch compte le recouvrement aussi sous `widen` (il ne change rien à
ce qui est annoncé : élargir modifie la séquence émise, pas la position de la
radio, que le chanctx du GO tient sur un canal — donc la réponse est la même
sous toutes les stratégies). Le compagnon côté démon accepte les deux
étiquettes, `intersect:` et `overlap:`, il est dans `00-local-changes.patch`.

Réserve, mesurée le 2026-09-13 au soir : avec ce binaire, la réponse à `/Ask`
mettait 11, 15 puis 19,6 s, contre 2 à 4 s avec le binaire d'origine, et les
transferts mouraient à 10 ko/s. Le coût direct est pourtant négligeable — 2,3 %
des lignes du journal, 1,6 ko/s écrits dans un tmpfs. Mais **deux choses ont
changé en même temps** entre les deux séries : le binaire, et un `wifi-reset`
suivi d'un redémarrage propre après trois reconstructions successives. On ne
peut donc pas attribuer l'amélioration à l'un plutôt qu'à l'autre. Le test qui
tranche : réinstaller ce binaire **sans** refaire de reset, et regarder la
latence de l'`/Ask`. Tant qu'il n'est pas fait, c'est le binaire d'origine qui
tourne.

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
- Cinq transferts sur neuf s'arrêtent à **99,2 à 99,9 %** de `TotalBytes` : le
  téléphone envoie tout sauf les deux derniers kilo-octets, puis se tait. Ces
  transferts-là sont finis, et on passe 30 s dans le délai d'expiration à le
  découvrir — sur 41, 31, 62 et 61 s mesurées, trente sont du vide. Rendre le
  délai proportionné à ce qui reste est le prochain gain, et il est gratuit.
- `wifi-reset` arrache `owl` et `awdl0` sous une pile armée, qui se reconstruit
  alors en boucle autour d'un `opendrop` orphelin et reste bloquée en `waking`.
  L'ordre est : interrupteur sur off, `wifi-reset`, interrupteur sur on.
- La boucle de santé vérifiait que les **processus** vivaient, jamais que leurs
  **interfaces** existaient. owl continue de tourner sur un vif moniteur
  supprimé sous lui sans rien dire, et `awdl0` survit comme une coquille sans
  radio derrière : la barre affiche `armed` devant une pile morte. Vu trois
  fois en une nuit — après un rechargement du driver, et après deux
  arrêts/relances trop rapprochés. Elle teste maintenant `awdl0`, le moniteur
  qu'owl utilise réellement (`ackvif`) et `go0`, et nomme celui qui manque.
- Le chemin AWDL et la station tombent **indépendamment** : mesuré à la même
  seconde sur la même radio, 70 % de perte vers le téléphone et 0 % vers la
  box. Surveiller la station ne dit donc rien de l'état d'AirDrop, et c'est
  pour ça que `tools/linkwatch.sh` mesure les deux séparément.
- `airdrop.sh` laisse un `owl` orphelin quand il est interrompu, et le run
  suivant meurt sur `Could not open device: awdl0`.
- NetworkManager prend `go0` en charge et lui donne la route par défaut via
  DHCP, ce qui éjecte la station. D'où
  `/etc/NetworkManager/conf.d/99-airdrop-unmanaged.conf`.
