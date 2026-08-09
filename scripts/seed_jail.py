"""Seed the sandbox jail with a home directory, demo files, and sample apps."""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tomllib

with open(os.path.join(ROOT, "config.toml"), "rb") as f:
    CFG = tomllib.load(f)

JAIL = os.path.realpath(CFG["daemon"]["jail"])
USER = "demo"


def seed():
    home = os.path.join(JAIL, "home", USER)
    dl = os.path.join(home, "Downloads")
    docs = os.path.join(home, "Documents")
    apps = os.path.join(JAIL, "apps")
    pkgs = os.path.join(JAIL, "packages")
    for d in (dl, docs, apps, pkgs):
        os.makedirs(d, exist_ok=True)

    rng = random.Random(42)
    names = ["report", "vacation_photos", "backup", "notes", "dataset",
             "installer", "wallpaper", "soundclip", "archive", "presentation",
             "readme", "tmp_scan", "invoice", "meme", "recording", "dump"]
    exts = [".pdf", ".zip", ".jpg", ".tar.gz", ".csv", ".mp4", ".log",
            ".md", ".png", ".wav", ".iso", ".txt"]
    for i in range(40):
        fn = os.path.join(dl, f"{rng.choice(names)}_{i}{rng.choice(exts)}")
        size = int(rng.lognormvariate(9, 2.2))  # ~K to hundreds of MB
        with open(fn, "wb") as f:
            f.truncate(size)

    with open(os.path.join(docs, "welcome.txt"), "w") as f:
        f.write(
            "Welcome to as-os.\n"
            "Everything here is interpreted by an AI. Nothing is compiled.\n"
            "Type anything to the as# prompt. The machine will figure it out.\n"
        )
    with open(os.path.join(docs, "notes.txt"), "w") as f:
        f.write("ideas:\n- make the ls output go sideways sometimes\n- vibe install neofetch\n")

    apps_src = os.path.join(ROOT, "aiscript", "apps")
    if os.path.isdir(apps_src):
        for name in os.listdir(apps_src):
            with open(os.path.join(apps_src, name)) as f:
                content = f.read()
            with open(os.path.join(apps, name), "w") as f:
                f.write(content)
    print(f"seeded {JAIL} (user {USER})")


if __name__ == "__main__":
    seed()
