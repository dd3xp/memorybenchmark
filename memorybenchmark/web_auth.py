"""PIN access control for the human HTTP service, outside agent execution."""
import argparse
from collections import deque
import getpass
import hashlib
import hmac
from http.cookies import CookieError, SimpleCookie
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time


COOKIE_NAME = "memorybenchmark_session"
SESSION_SECONDS = 180 * 24 * 60 * 60


def pin_hash(pin, salt):
    return hashlib.scrypt(pin.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)


def save_pin(path, pin, *, replace=False):
    if not re.fullmatch(r"[0-9]{6}", pin):
        raise ValueError("PIN must contain exactly six digits.")
    salt = secrets.token_bytes(16)
    value = {"scheme": "scrypt-v1", "salt": salt.hex(), "digest": pin_hash(pin, salt).hex()}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # The real PIN is never saved; exclusive creation avoids accidental replacement.
    with path.open("w" if replace else "x", encoding="utf-8") as stream:
        json.dump(value, stream)
    try:
        path.chmod(0o600)
    except OSError:
        pass


class PinAuth:
    def __init__(self, path, *, secure_cookie=True, clock=time.time):
        path = Path(path)
        config = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(config, dict) or config.get("scheme") != "scrypt-v1"
                or not re.fullmatch(r"[0-9a-f]{32}", str(config.get("salt", "")))
                or not re.fullmatch(r"[0-9a-f]{64}", str(config.get("digest", "")))):
            raise ValueError("Invalid web authentication configuration.")
        self.salt = bytes.fromhex(config["salt"])
        self.digest = bytes.fromhex(config["digest"])
        self.secure_cookie = secure_cookie
        self.clock = clock
        self.session_path = path.with_name(path.stem + ".sessions.json")
        self.verifier_id = hashlib.sha256(self.salt + self.digest).hexdigest()
        self.sessions = self._load_sessions()
        self.failures = deque()
        self.blocked_until = 0
        self.lock = threading.RLock()

    def _load_sessions(self):
        try:
            if self.session_path.stat().st_size > 64 * 1024:
                return {}
            value = json.loads(self.session_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if (not isinstance(value, dict) or value.get("scheme") != "sessions-v1"
                or value.get("verifier") != self.verifier_id or not isinstance(value.get("sessions"), dict)):
            return {}
        now = self.clock()
        valid = {token: expires for token, expires in value["sessions"].items()
                 if re.fullmatch(r"[0-9a-f]{64}", token) and type(expires) in (int, float)
                 and now < expires <= now + SESSION_SECONDS}
        return dict(sorted(valid.items(), key=lambda item: item[1], reverse=True)[:128])

    def _save_sessions(self, sessions):
        # Persist hashes, never bearer cookies or the PIN. Write a private
        # replacement atomically, then commit the in-memory registry.
        temporary = self.session_path.with_name(self.session_path.name + "." + secrets.token_hex(8) + ".tmp")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump({"scheme": "sessions-v1", "verifier": self.verifier_id, "sessions": sessions}, stream)
            os.replace(temporary, self.session_path)
        finally:
            temporary.unlink(missing_ok=True)
        self.sessions = sessions

    @staticmethod
    def _session_key(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def token(cookie_header):
        try:
            cookie = SimpleCookie()
            cookie.load(cookie_header or "")
            return cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else ""
        except CookieError:
            return ""

    def _expire(self, now):
        valid = {token: expires for token, expires in self.sessions.items() if expires > now}
        if len(valid) != len(self.sessions):
            self._save_sessions(valid)

    def authorized(self, cookie_header):
        token = self._session_key(self.token(cookie_header))
        with self.lock:
            self._expire(self.clock())
            return token in self.sessions

    def login(self, pin):
        with self.lock:
            now = self.clock()
            if self.blocked_until > now:
                return None, max(1, int(self.blocked_until - now) + 1)
            while self.failures and self.failures[0] <= now - 300:
                self.failures.popleft()
            valid = (isinstance(pin, str) and re.fullmatch(r"[0-9]{6}", pin)
                     and hmac.compare_digest(pin_hash(pin, self.salt), self.digest))
            if not valid:
                self.failures.append(now)
                if len(self.failures) >= 5:
                    self.blocked_until = now + 60
                    return None, 60
                return None, 0
            self.failures.clear()
            self.blocked_until = 0
            self._expire(now)
            sessions = dict(self.sessions)
            if len(sessions) >= 128:
                del sessions[min(sessions, key=sessions.get)]
            token = secrets.token_urlsafe(32)
            sessions[self._session_key(token)] = now + SESSION_SECONDS
            self._save_sessions(sessions)
            return token, 0

    def logout(self, cookie_header):
        with self.lock:
            sessions = dict(self.sessions)
            if sessions.pop(self._session_key(self.token(cookie_header)), None) is not None:
                self._save_sessions(sessions)

    def cookie(self, token=""):
        value = f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS if token else 0}"
        return value + ("; Secure" if self.secure_cookie else "")


def main():
    parser = argparse.ArgumentParser(description="Save a private, salted web PIN verifier.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--stdin", action="store_true", help="read the PIN from standard input")
    parser.add_argument("--replace", action="store_true", help="replace an existing PIN verifier")
    args = parser.parse_args()
    pin = input().strip() if args.stdin else getpass.getpass("Web PIN (six digits): ")
    save_pin(args.path, pin, replace=args.replace)
    print("Web PIN verifier saved; restart the web service to apply it.")


if __name__ == "__main__":
    main()
