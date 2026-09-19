"""Regression tests for the recall overlay window-scan fix.

Background: every persistent/labels/status draw pass called
find_window_by_id() once per saved window, and each call re-scanned ALL OS
windows via the mac accessibility API. Under window load a single draw pass
overran the 2s canvas watchdog (talon.log 2026-09-18: 700+ overruns with the
draw_persistent -> find_window_by_id -> a.windows() stack), stalling every
canvas/mode-indicator command behind the clogged callback.

The fix resolves all saved entries against ONE per-pass window map
(recall_commands.get_windows_by_id()) and skips redundant persistent
redraws when nothing moved. These tests assert:

1. Behavior parity — hits, misses (id None / window gone), zero-rect
   windows, and archived entries render exactly as the old per-entry scan
   did (oracle = the old algorithm, run against a frozen snapshot).
2. Scan bound — each draw pass performs exactly ONE OS-window scan no
   matter how many saved windows exist (this is what keeps the pass inside
   the watchdog interval under load).
3. Redraw skipping — re-showing the already-tracked window, or clearing an
   already-clear highlight, schedules no new redraw.

Self-contained: builds a fake `talon` package in sys.modules (no Talon
running, no network, hermetic). Lives in `.tests/` (dot-prefixed) so the
Talon runtime loader skips it.
"""

import importlib
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = str(Path(__file__).resolve().parent.parent)


# ── Fake Talon runtime ────────────────────────────────────────────────

class FakeRect:
    def __init__(self, x=0, y=0, width=0, height=0):
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class FakeTextRect:
    def __init__(self, width, height):
        self.width = width
        self.height = height


class FakePaint:
    class Style:
        FILL = "FILL"
        STROKE = "STROKE"
        STROKE_AND_FILL = "STROKE_AND_FILL"

    def __init__(self):
        self.textsize = 12
        self.style = None
        self.color = None
        self.stroke_width = 0
        self.imagefilter = None

    def measure_text(self, s):
        # (advance, bounds) — draw code uses [1].width / [1].height.
        return (None, FakeTextRect(len(s) * 7, self.textsize))


class FakeSkiaCanvas:
    """Records draw ops; exposes .paint like the real Skia canvas."""

    def __init__(self):
        self.paint = FakePaint()
        self.texts = []    # (text, x, y, color)
        self.circles = []  # (color, x, y, r)
        self.rects = []
        self.paths = 0
        self.lines = 0

    def draw_text(self, text, x, y):
        self.texts.append((text, x, y, self.paint.color))

    def draw_circle(self, x, y, r):
        self.circles.append((self.paint.color, x, y, r))

    def draw_rect(self, rect):
        self.rects.append(rect)

    def draw_path(self, path):
        self.paths += 1

    def draw_line(self, x1, y1, x2, y2):
        self.lines += 1

    def save(self):
        pass

    def restore(self):
        pass

    def clip_rect(self, rect):
        pass


class FakeCanvas:
    freezes = 0

    def __init__(self):
        self.draw_handlers = []
        self.mouse_handlers = []
        self.blocks_mouse = False
        self.closed = False

    @classmethod
    def from_screen(cls, screen):
        return cls()

    @classmethod
    def from_rect(cls, rect):
        c = cls()
        c.rect = rect
        return c

    def register(self, event, handler):
        if event == "draw":
            self.draw_handlers.append(handler)
        else:
            self.mouse_handlers.append(handler)

    def unregister(self, event, handler):
        pass

    def freeze(self):
        type(self).freezes += 1

    def close(self):
        self.closed = True

    def move(self, x, y):
        pass


class FakeScreen:
    def __init__(self):
        self.rect = FakeRect(0, 0, 1920, 1080)
        self.visible_rect = FakeRect(0, 0, 1920, 1080)
        self.scale = 1


class FakeCron:
    def __init__(self):
        self.afters = []  # (spec, fn)
        self.cancelled = []

    def after(self, spec, fn):
        job = object()
        self.afters.append((spec, fn))
        return job

    def interval(self, spec, fn):
        return object()

    def cancel(self, job):
        self.cancelled.append(job)


class FakeApp:
    def __init__(self, name, windows, counters, latency=0.0):
        self.name = name
        self._windows = windows
        self._counters = counters
        self._latency = latency
        for w in windows:
            w.app = self

    def windows(self):
        self._counters["windows_calls"] += 1
        if self._latency:
            import time
            time.sleep(self._latency)
        return list(self._windows)


class FakeWindow:
    def __init__(self, wid, title="win", rect=None):
        self.id = wid
        self.title = title
        self.rect = rect if rect is not None else FakeRect(0, 0, 800, 600)
        self.app = None
        self.focused = False

    def focus(self):
        self.focused = True


class FakeUI:
    def __init__(self, counters):
        self._counters = counters
        self._apps = []
        self._active = None
        self._screen = FakeScreen()
        self._callbacks = {}

    def set_apps(self, apps):
        self._apps = apps

    def apps(self, background=False):
        self._counters["apps_calls"] += 1
        return list(self._apps)

    def windows(self):
        return [w for a in self._apps for w in a.windows()]

    def active_window(self):
        return self._active

    def main_screen(self):
        return self._screen

    def register(self, event, cb):
        self._callbacks.setdefault(event, []).append(cb)

    def fire(self, event, *args):
        for cb in list(self._callbacks.get(event, [])):
            cb(*args)


class _UserActions:
    def __getattr__(self, name):
        def _dummy(*args, **kwargs):
            return {}
        return _dummy


class FakeActions:
    def __init__(self):
        self.user = _UserActions()

    def __getattr__(self, name):
        def _dummy(*args, **kwargs):
            return None
        return _dummy


class FakeModule:
    def __call__(self, *args, **kwargs):
        return None

    def tag(self, *args, **kwargs):
        return None

    def list(self, *args, **kwargs):
        return None

    def capture(self, *args, **kwargs):
        def deco(fn):
            return fn
        return deco

    def action_class(self, cls):
        return cls

    def setting(self, *args, **kwargs):
        return None


class FakeContext:
    def __init__(self):
        self.lists = {}
        self.tags = []


def _install_fake_talon(counters, ui):
    """Install a fake `talon` package tree in sys.modules. Returns cron."""
    cron = FakeCron()

    talon = types.ModuleType("talon")
    talon.Module = FakeModule
    talon.Context = FakeContext
    talon.actions = FakeActions()
    talon.cron = cron
    ui.Window = FakeWindow  # `-> ui.Window` annotations resolve at def time
    talon.ui = ui
    talon.app = types.SimpleNamespace(platform="mac")
    talon.registry = types.SimpleNamespace(lists={})
    talon.scope = types.SimpleNamespace(get=lambda *a, **k: set())
    talon.settings = types.SimpleNamespace(get=lambda *a, **k: None)
    talon.skia = types.SimpleNamespace(
        Path=types.SimpleNamespace(from_svg=lambda svg: object()),
        Canvas=FakeSkiaCanvas,
    )

    canvas_mod = types.ModuleType("talon.canvas")
    canvas_mod.Canvas = FakeCanvas
    canvas_mod.MouseEvent = object

    screen_mod = types.ModuleType("talon.screen")
    screen_mod.Screen = FakeScreen

    skia_mod = types.ModuleType("talon.skia")
    skia_mod.Canvas = FakeSkiaCanvas
    skia_mod.Paint = FakePaint

    skia_canvas_mod = types.ModuleType("talon.skia.canvas")
    skia_canvas_mod.Canvas = FakeSkiaCanvas

    ui_mod = types.ModuleType("talon.ui")
    ui_mod.Rect = FakeRect
    ui_mod.Window = FakeWindow

    sys.modules["talon"] = talon
    sys.modules["talon.canvas"] = canvas_mod
    sys.modules["talon.screen"] = screen_mod
    sys.modules["talon.skia"] = skia_mod
    sys.modules["talon.skia.canvas"] = skia_canvas_mod
    sys.modules["talon.ui"] = ui_mod
    return cron


# ── Package import helper ─────────────────────────────────────────────

PKG_NAME = "recall_under_test"


def _import_package():
    """Import the repo's recall modules as a package from the worktree."""
    if PKG_NAME in sys.modules:
        return importlib.import_module(PKG_NAME + ".recall_overlay_draw")
    pkg = types.ModuleType(PKG_NAME)
    pkg.__path__ = [REPO_ROOT]
    sys.modules[PKG_NAME] = pkg
    for mod in (
        "recall_state",
        "recall_commands",
        "recall_overlay_shared",
        "recall_pill_colors",
        "recall_overlay_draw",
        "recall_overlay_labels",
        "recall_overlay_status",
        "recall_overlay_persistent",
    ):
        importlib.import_module(f"{PKG_NAME}.{mod}")
    return importlib.import_module(PKG_NAME + ".recall_overlay_draw")


_INSTALLED = {}


def _ensure_installed():
    """Install fakes + import recall modules exactly once per session.

    The recall modules bind `from talon import ...` names at import time, so
    reinstalling fakes per test would detach the modules from the fixtures.
    Install once; each test resets mutable state below instead."""
    if _INSTALLED:
        return _INSTALLED["cron"]
    counters = {"apps_calls": 0, "windows_calls": 0}
    ui = FakeUI(counters)
    cron = _install_fake_talon(counters, ui)
    _import_package()
    _INSTALLED.update(counters=counters, ui=ui, cron=cron)
    return cron


@pytest.fixture
def env():
    """Fake-Talon environment + imported recall modules + window fixtures."""
    _ensure_installed()
    counters = _INSTALLED["counters"]
    ui = _INSTALLED["ui"]
    cron = _INSTALLED["cron"]
    counters["apps_calls"] = 0
    counters["windows_calls"] = 0
    cron.afters.clear()
    cron.cancelled.clear()
    mods = {m: sys.modules[f"{PKG_NAME}.{m}"] for m in (
        "recall_state", "recall_commands", "recall_overlay_shared",
        "recall_overlay_draw", "recall_overlay_labels",
        "recall_overlay_status", "recall_overlay_persistent",
    )}

    rs = mods["recall_state"]
    rs.saved_windows.clear()
    rs.archived_windows.clear()
    mods["recall_commands"]._invalidate_window_id_cache()

    # Window fixtures: 2 apps x 3 windows.
    #   alpha   -> live window id 101
    #   bravo   -> stale id 999 (window gone)
    #   charlie -> id None (detached/closed entry)
    #   zero    -> live id 102 but zero-size rect (minimized)
    #   archived entry "oldie" lives in archived_windows, never drawn.
    w101 = FakeWindow(101, "alpha-term", FakeRect(100, 100, 800, 600))
    w102 = FakeWindow(102, "zero-term", FakeRect(0, 0, 0, 0))
    w103 = FakeWindow(103, "other", FakeRect(1100, 100, 700, 500))
    w201 = FakeWindow(201, "browser", FakeRect(100, 700, 900, 300))
    w202 = FakeWindow(202, "mail", FakeRect(1100, 700, 700, 300))
    w203 = FakeWindow(203, "music", FakeRect(500, 400, 400, 300))
    ui.set_apps([
        FakeApp("WezTerm", [w101, w102, w103], counters),
        FakeApp("Safari", [w201, w202, w203], counters),
    ])
    ui._active = w101

    rs.saved_windows.update({
        "alpha": {"id": 101, "app": "WezTerm", "title": "alpha-term",
                  "path": "/tmp", "aliases": []},
        "bravo": {"id": 999, "app": "WezTerm", "title": "gone",
                  "path": "/tmp", "aliases": []},
        "charlie": {"id": None, "app": "WezTerm", "title": "closed",
                    "path": "/tmp", "aliases": []},
        "zero": {"id": 102, "app": "WezTerm", "title": "zero-term",
                 "path": "/tmp", "aliases": []},
    })
    rs.archived_windows.update({
        "oldie": {"id": 555, "app": "WezTerm", "title": "old",
                  "path": "/tmp", "aliases": [], "forgotten_at": 1.0},
    })

    # Reset persistent-module globals between tests.
    rop = mods["recall_overlay_persistent"]
    rop._persistent_canvas = None
    rop._persistent_window = None
    rop._persistent_name = ""
    rop._redraw_job = None
    rop._previous_pill_rects = None
    rop._last_scheduled_rect = None
    rop._pill_hit_rects = []
    rop._click_canvases = []
    rs.save_to_disk = lambda: None  # never touch the real JSON in tests

    yield types.SimpleNamespace(
        counters=counters, ui=ui, cron=cron, mods=mods,
        windows={"w101": w101, "w102": w102},
        apps=list(ui._apps),
    )


def _reset_counters(env):
    env.counters["apps_calls"] = 0
    env.counters["windows_calls"] = 0


def _snapshot(env):
    """One scan of all live windows (oracle input); resets counters after."""
    snap = [w for a in env.ui.apps(background=False) for w in a.windows()]
    _reset_counters(env)
    return snap


def _oracle(wid, snapshot):
    """The OLD algorithm: linear scan per lookup, first match wins."""
    if wid is None:
        return None
    for w in snapshot:
        if w.id == wid:
            return w
    return None


# ── 1. Behavior parity ────────────────────────────────────────────────

def test_draw_persistent_hit_miss_archived_parity(env):
    draw = env.mods["recall_overlay_draw"]
    snapshot = _snapshot(env)

    c = FakeSkiaCanvas()
    hit_rects = draw.draw_persistent(c, active_window_id=101)

    # Oracle expectation: alpha (live) and only alpha. bravo (gone) and
    # charlie (None) are misses -> skipped; zero has a zero-size rect ->
    # skipped; archived "oldie" is never drawn.
    expected = set()
    for name, info in (("alpha", {"id": 101}), ("bravo", {"id": 999}),
                       ("charlie", {"id": None}), ("zero", {"id": 102})):
        w = _oracle(info["id"], snapshot)
        if w is None:
            continue
        if w.rect.width <= 0 or w.rect.height <= 0:
            continue
        expected.add(name)
    assert expected == {"alpha"}
    assert [n for n, _ in hit_rects] == ["alpha"]
    assert "oldie" not in [n for n, _ in hit_rects]


def test_draw_persistent_missing_everything_returns_no_pills(env):
    draw = env.mods["recall_overlay_draw"]
    rs = env.mods["recall_state"]
    rs.saved_windows.clear()
    rs.saved_windows.update({
        "gone1": {"id": 111, "app": "X", "title": "x", "path": None, "aliases": []},
        "gone2": {"id": None, "app": "X", "title": "y", "path": None, "aliases": []},
    })
    _reset_counters(env)
    assert draw.draw_persistent(FakeSkiaCanvas(), None) == []


def test_labels_missing_entries_render_not_found(env):
    labels = env.mods["recall_overlay_labels"]
    _snapshot(env)  # warm; counters reset inside
    c = FakeSkiaCanvas()
    labels.on_draw(c)
    texts = [t for t, _, _, _ in c.texts]
    assert "alpha" in texts                      # live hit renders its name
    assert "bravo (not found)" in texts          # gone id renders missing pill
    assert "charlie (not found)" in texts        # None id renders missing pill
    assert "zero" not in texts                   # zero-rect is skipped entirely
    assert not any("oldie" in t for t in texts)  # archived never drawn


def test_status_lists_present_before_missing(env):
    status = env.mods["recall_overlay_status"]
    _snapshot(env)
    c = FakeSkiaCanvas()
    status.on_draw_status(c)
    # Row order: present windows first (alpha, zero), then missing (bravo,
    # charlie), alphabetical within each group. Row text starts with the name.
    row_texts = [t for t, _, _, _ in c.texts if t.startswith(
        ("alpha", "zero", "bravo", "charlie"))]
    names = [t.split(" ")[0] for t in row_texts]
    assert names == ["alpha", "zero", "bravo", "charlie"]
    # Status dots: green for present, red for missing.
    dot_colors = [color for color, _, _, _ in c.circles]
    assert dot_colors == ["44cc44", "44cc44", "cc4444", "cc4444"]


class ClosingWindow(FakeWindow):
    """A window whose proxy raises AttributeError on .rect (closed mid-draw)."""

    def __init__(self, wid):
        self.id = wid
        self.title = "closing"
        self.app = None
        self.focused = False

    @property
    def rect(self):
        raise AttributeError("window closed mid-draw")


def test_closing_window_skipped_not_fatal(env):
    draw = env.mods["recall_overlay_draw"]
    labels = env.mods["recall_overlay_labels"]
    rs = env.mods["recall_state"]
    closing = ClosingWindow(104)
    closing.app = env.apps[0]
    env.apps[0]._windows.append(closing)
    rs.saved_windows["dying"] = {"id": 104, "app": "WezTerm",
                                    "title": "closing", "path": None,
                                    "aliases": []}
    env.mods["recall_commands"]._invalidate_window_id_cache()
    _reset_counters(env)
    # Map build reads .id only, so the closing window resolves ...
    hit_rects = draw.draw_persistent(FakeSkiaCanvas(), active_window_id=101)
    # ... but its unreadable rect skips just that pill, like a miss.
    assert [n for n, _ in hit_rects] == ["alpha"]
    # Labels must degrade the same way, not abort the whole overlay.
    c = FakeSkiaCanvas()
    labels.on_draw(c)
    texts = [t for t, _, _, _ in c.texts]
    assert "alpha" in texts
    assert "dying (not found)" not in texts  # skipped, never a missing pill
    assert len([t for t in texts if t == "dying"]) == 0


def test_alias_never_shadows_canonical(env):
    """An alias matching a canonical name must not hijack it.

    Regression test for a guard the refactor dropped: with canonical
    'bravo' present and 'alpha' carrying alias 'bravo', 'recall bravo'
    must resolve to bravo, not alpha."""
    import talon
    rs = env.mods["recall_state"]
    seen = {}

    def _recorder(name_map, **kwargs):
        seen.update(name_map)
        return {}

    user = talon.actions.user
    user.create_spoken_forms_from_map = _recorder
    try:
        rs.saved_windows.clear()
        rs.saved_windows.update({
            "bravo": {"id": 201, "app": "Safari", "title": "b",
                        "path": None, "aliases": []},
            "alpha": {"id": 101, "app": "WezTerm", "title": "a",
                        "path": None, "aliases": ["bravo"]},
        })
        rs.update_window_list()
    finally:
        del user.create_spoken_forms_from_map
    assert seen["bravo"] == "bravo"
    assert seen["alpha"] == "alpha"


# ── 2. Scan bound: ONE scan when cold, ZERO while cached ─────────────
# The window map persists across draw passes and is invalidated only by
# win_open / win_close, so sustained redraws cost no OS scans at all.

def test_draw_persistent_cached_across_passes(env):
    draw = env.mods["recall_overlay_draw"]
    _snapshot(env)
    draw.draw_persistent(FakeSkiaCanvas(), active_window_id=101)
    # 4 saved entries (hits + misses) but a single scan of the 2 apps.
    assert env.counters["apps_calls"] == 1
    assert env.counters["windows_calls"] == 2
    # Second pass with no window churn: served from cache, zero scans.
    _reset_counters(env)
    draw.draw_persistent(FakeSkiaCanvas(), active_window_id=101)
    assert env.counters["apps_calls"] == 0
    assert env.counters["windows_calls"] == 0


def test_cache_invalidated_on_window_events(env):
    draw = env.mods["recall_overlay_draw"]
    cmds = env.mods["recall_commands"]
    _snapshot(env)
    draw.draw_persistent(FakeSkiaCanvas(), active_window_id=101)
    _reset_counters(env)
    draw.draw_persistent(FakeSkiaCanvas(), active_window_id=101)
    assert env.counters["apps_calls"] == 0
    # A window opens: next pass rescans exactly once ...
    env.ui.fire("win_open", object())
    draw.draw_persistent(FakeSkiaCanvas(), active_window_id=101)
    assert env.counters["apps_calls"] == 1
    assert env.counters["windows_calls"] == 2
    # ... and caches again until a window closes.
    _reset_counters(env)
    draw.draw_persistent(FakeSkiaCanvas(), active_window_id=101)
    assert env.counters["apps_calls"] == 0
    env.ui.fire("win_close", object())
    draw.draw_persistent(FakeSkiaCanvas(), active_window_id=101)
    assert env.counters["apps_calls"] == 1
    assert cmds.get_windows_by_id() is not None


def test_labels_single_scan(env):
    labels = env.mods["recall_overlay_labels"]
    _snapshot(env)
    labels.on_draw(FakeSkiaCanvas())
    assert env.counters["apps_calls"] == 1
    assert env.counters["windows_calls"] == 2
    _reset_counters(env)
    labels.on_draw(FakeSkiaCanvas())
    assert env.counters["apps_calls"] == 0


def test_status_single_scan(env):
    status = env.mods["recall_overlay_status"]
    _snapshot(env)
    status.on_draw_status(FakeSkiaCanvas())
    # Old code scanned per entry in the sort key AND per row (2N scans);
    # now the sort and all rows share one map.
    assert env.counters["apps_calls"] == 1
    assert env.counters["windows_calls"] == 2
    _reset_counters(env)
    status.on_draw_status(FakeSkiaCanvas())
    assert env.counters["apps_calls"] == 0


def test_find_window_by_id_unchanged(env):
    cmds = env.mods["recall_commands"]
    _reset_counters(env)
    w = cmds.find_window_by_id(201)
    assert w is not None and w.title == "browser"
    assert cmds.find_window_by_id(999) is None
    assert cmds.find_window_by_id(None) is None
    # Single-lookup helper keeps its early-exit linear behavior.
    assert env.counters["windows_calls"] >= 1


# ── 3. Redraw skipping ────────────────────────────────────────────────

def _redraws(env):
    return [s for s, _ in env.cron.afters if s == "50ms"]


def test_show_same_window_skips_redraw(env):
    rop = env.mods["recall_overlay_persistent"]
    w101 = env.windows["w101"]
    rop.show_persistent_highlight(w101, "alpha")
    assert len(_redraws(env)) == 1
    # Spurious refocus of the already-tracked, unmoved window: no new redraw.
    rop.show_persistent_highlight(w101, "alpha")
    assert len(_redraws(env)) == 1


def test_show_moved_window_redraws(env):
    rop = env.mods["recall_overlay_persistent"]
    w101 = env.windows["w101"]
    rop.show_persistent_highlight(w101, "alpha")
    assert len(_redraws(env)) == 1
    w101.rect = FakeRect(300, 300, 800, 600)  # user dragged the window
    rop.show_persistent_highlight(w101, "alpha")
    assert len(_redraws(env)) == 2


def test_show_different_window_redraws(env):
    rop = env.mods["recall_overlay_persistent"]
    w101 = env.windows["w101"]
    rop.show_persistent_highlight(w101, "alpha")
    other = FakeWindow(103, "other", FakeRect(1100, 100, 700, 500))
    rop.show_persistent_highlight(other, "other")
    assert len(_redraws(env)) == 2


def test_clear_already_clear_schedules_nothing(env):
    rop = env.mods["recall_overlay_persistent"]
    rop.clear_persistent_highlight()
    assert _redraws(env) == []
    rop.show_persistent_highlight(env.windows["w101"], "alpha")
    assert len(_redraws(env)) == 1
    rop.clear_persistent_highlight()
    assert len(_redraws(env)) == 2
    # Focus bouncing among unsaved windows: already clear, no more redraws.
    rop.clear_persistent_highlight()
    rop.clear_persistent_highlight()
    assert len(_redraws(env)) == 2
