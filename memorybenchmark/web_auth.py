"""PIN access control for the human HTTP service, outside agent execution."""
import argparse
from collections import deque
import getpass
import hashlib
import hmac
from http.cookies import CookieError, SimpleCookie
import json
from pathlib import Path
import re
import secrets
import threading
import time


COOKIE_NAME = "memorybenchmark_session"
SESSION_SECONDS = 12 * 60 * 60


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
    def __init__(self, path, *, secure_cookie=True, clock=time.monotonic):
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        if (not isinstance(config, dict) or config.get("scheme") != "scrypt-v1"
                or not re.fullmatch(r"[0-9a-f]{32}", str(config.get("salt", "")))
                or not re.fullmatch(r"[0-9a-f]{64}", str(config.get("digest", "")))):
            raise ValueError("Invalid web authentication configuration.")
        self.salt = bytes.fromhex(config["salt"])
        self.digest = bytes.fromhex(config["digest"])
        self.secure_cookie = secure_cookie
        self.clock = clock
        self.sessions = {}
        self.failures = deque()
        self.blocked_until = 0
        self.lock = threading.RLock()

    @staticmethod
    def token(cookie_header):
        try:
            cookie = SimpleCookie()
            cookie.load(cookie_header or "")
            return cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else ""
        except CookieError:
            return ""

    def _expire(self, now):
        self.sessions = {token: expires for token, expires in self.sessions.items() if expires > now}

    def authorized(self, cookie_header):
        token = self.token(cookie_header)
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
            if len(self.sessions) >= 128:
                del self.sessions[min(self.sessions, key=self.sessions.get)]
            token = secrets.token_urlsafe(32)
            self.sessions[token] = now + SESSION_SECONDS
            return token, 0

    def logout(self, cookie_header):
        with self.lock:
            self.sessions.pop(self.token(cookie_header), None)

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
