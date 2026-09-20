#!/usr/bin/env python3
"""A compact waybar module for Docker: icon plus the number of running
containers.

Emits JSON for waybar ("return-type": "json").
Stays silent if Docker is not installed, so the module disappears.
"""

import json
import shutil
import subprocess

ICON = ""  # nf-linux-docker


def emit(text, tooltip, css_class):
    print(json.dumps({"text": text, "tooltip": tooltip, "class": css_class}), flush=True)


def docker(*args, timeout=4):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def main():
    if shutil.which("docker") is None:
        return  # module hidden

    try:
        info = docker("info")
    except (subprocess.SubprocessError, OSError):
        emit(ICON, "Docker ne répond pas", "stopped")
        return

    if info.returncode != 0:
        message = info.stderr.lower()
        if "permission denied" in message:
            emit(ICON, "Docker : accès refusé\nReconnecte-toi pour activer ton groupe docker", "error")
        else:
            emit(ICON, "Docker est arrêté\nsudo systemctl start docker.socket", "stopped")
        return

    listing = docker("ps", "--format", "{{.Names}}\t{{.Status}}")
    running = [line for line in listing.stdout.splitlines() if line.strip()]

    every = docker("ps", "-aq")
    total = len([line for line in every.stdout.splitlines() if line.strip()])

    if not running:
        emit(ICON, f"Aucun conteneur actif\n{total} conteneur(s) au total", "idle")
        return

    rows = []
    for line in running[:10]:
        name, _, status = line.partition("\t")
        rows.append(f"  {name}  ·  {status}")
    if len(running) > 10:
        rows.append(f"  … et {len(running) - 10} de plus")

    tooltip = f"{len(running)} actif(s) sur {total}\n" + "\n".join(rows)
    emit(f"{ICON} {len(running)}", tooltip, "running")


if __name__ == "__main__":
    main()
