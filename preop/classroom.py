"""
In-class demo: give each student their own example patient case.

One Roster is shared by every browser session of the Streamlit app, so it is thread-safe. It lives in memory
only: an app restart forgets the assignments and students sign in again. Each student's schedule changes and
decisions stay in their own session, so two students who end up with the same patient do not affect each other.
"""
from __future__ import annotations

import secrets
import threading
from itertools import zip_longest

from . import criteria as C
from . import schedule as S

SHOWCASE = "S082"  # the presenter's walkthrough case; students get the others
# The AI login's case: the board shows it as Ready, but the H&P family history describes a brother's reaction to
# anesthesia that suggests malignant hyperthermia. Only reading the note finds it. Ready cases are not in the
# student pool, so no student gets this one.
AI_CASE = "S054"
ORDER = {"resched": 0, "later": 1, "hold": 2, "open": 3}


def case_pool():
    """Cases with something to act on, taking turns by procedure so students sitting together get different
    surgeries. Cases with a schedule suggestion come first because they show the most of the app."""
    by_proc = {}
    for x in sorted(S.board(), key=lambda x: (ORDER.get(x["state"], 9), x["id"])):
        if x["id"] != SHOWCASE and x["state"] != "ready":
            by_proc.setdefault(x["case"]["procedure"], []).append(x["id"])
    return [sid for row in zip_longest(*(by_proc.get(p, []) for p in C.PROCEDURES)) for sid in row if sid]


class Roster:
    """Signed-in students: token -> name and assigned case. Cases are handed out in pool order, wrapping around
    if there are more students than cases."""

    def __init__(self, pool=None):
        self.pool = list(pool or case_pool())
        self._lock = threading.Lock()
        self._users = {}
        self._next = 0

    def join(self, name, ai=False):
        """ai=True marks the one login allowed to run AI reviews (it uses the project's API key). That login always
        gets AI_CASE and does not use up a case from the student pool."""
        with self._lock:
            token = secrets.token_urlsafe(6)
            if ai:
                sid = AI_CASE
            else:
                sid = self.pool[self._next % len(self.pool)]
                self._next += 1
            self._users[token] = dict(name=name, sid=sid, ai=ai)
            return token

    def reset(self):
        """Sign everyone out; the next student gets the first case in the pool again."""
        with self._lock:
            self._users.clear()
            self._next = 0

    def get(self, token):
        with self._lock:
            u = self._users.get(token)
            return dict(u) if u else None

    def __len__(self):
        with self._lock:
            return len(self._users)
