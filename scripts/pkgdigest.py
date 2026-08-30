#!/usr/bin/env python3
"""A digest of the nutrai package, identical on host and inside the container.

`docker compose restart` restarts a container from the image it already has,
so on a `build:` service it redeploys nothing. Every "restarted the bot" claim
on 26 Aug 2026 was false for that reason: eight commits of resolver guards,
provenance and notification changes sat in git while the container ran the
image built days earlier. Nothing in the logs said so — the bot started
cleanly, because it started cleanly with the old code.

So `make reload` compares this digest across the two and fails loudly when they
disagree. A deployment you cannot verify is a deployment you have to trust, and
this one was wrong for a day.
"""
import hashlib
import pathlib
import sys

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "nutrai")
h = hashlib.sha256()
for f in sorted(root.rglob("*.py")):
    h.update(str(f.relative_to(root)).encode())
    h.update(f.read_bytes())
print(h.hexdigest()[:16])
