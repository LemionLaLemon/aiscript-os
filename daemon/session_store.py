import json
import os
import re

from .session import Session

_SAFE_NAME = re.compile(r'[^A-Za-z0-9._-]')


class SessionStore:
    """Persists session state (messages + config) to
    jail/home/<user>/.as/sessions/<name>.json.

    The system prompt is NOT persisted: it is rebuilt fresh on load so that
    live data (uptime, apps, packages, current user) is always current.
    """

    def __init__(self, jail, user=None):
        self.jail = jail
        self.user = user

    def _dir(self):
        if self.user:
            base = os.path.join(self.jail, "home", self.user, ".as", "sessions")
        else:
            base = os.path.join(self.jail, ".as", "sessions")
        os.makedirs(base, exist_ok=True)
        return base

    def _path(self, name):
        safe = _SAFE_NAME.sub("_", name or "session")
        return os.path.join(self._dir(), f"{safe}.json")

    def save(self, session):
        if session.temp_session:
            return
        data = session.to_dict()
        path = self._path(session.name)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)

    def load(self, name):
        path = self._path(name)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def list(self):
        out = []
        d = self._dir()
        if not os.path.isdir(d):
            return out
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json"):
                continue
            path = os.path.join(d, fn)
            try:
                with open(path) as f:
                    data = json.load(f)
            except Exception:
                continue
            turns = sum(1 for m in data.get("messages", [])
                        if m.get("role") == "user")
            out.append({
                "name": data.get("name", fn[:-5]),
                "turns": turns,
                "temp_session": bool(data.get("temp_session", False)),
                "name_locked": bool(data.get("name_locked", False)),
                "mtime": os.path.getmtime(path),
            })
        return out

    def latest(self):
        """Return the name of the most recently modified saved session,
        or None if there are none."""
        items = self.list()
        if not items:
            return None
        items.sort(key=lambda i: i["mtime"], reverse=True)
        return items[0]["name"]

    def delete(self, name):
        path = self._path(name)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def rename(self, old, new):
        """Rename a saved session file. Returns (ok, err)."""
        old_path = self._path(old)
        if not os.path.exists(old_path):
            return False, "no such session"
        new_path = self._path(new)
        if os.path.exists(new_path):
            return False, "a session with that name already exists"
        try:
            with open(old_path) as f:
                data = json.load(f)
            data["name"] = new
            with open(new_path, "w") as f:
                json.dump(data, f)
            os.remove(old_path)
        except Exception as e:
            return False, str(e)
        return True, None
