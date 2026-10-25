"""Drive Odoo with Playwright and record the screen.

Every shot starts by showing its caption (or card), runs its storyboard
steps while the voice-over plays, and then holds until the voice-over is
done. The wall-clock start of every shot is kept, so assemble.py can lay the
voice-over under exactly the right frames.

Capture modes:

* ``x11`` (default on Linux): a real Chromium window in kiosk mode on an
  Xvfb display, grabbed by ffmpeg — sharp text, 30 fps, frames stamped with
  wall-clock time.
* ``playwright``: Playwright's built-in recorder. Works everywhere (also on
  macOS/Windows) but is softer and its timing is approximate.
"""

import glob
import json
import os
import shutil
import subprocess
import time

from playwright.sync_api import sync_playwright

WIDTH, HEIGHT = 1920, 1080
OVERLAY_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "overlay.js")

VOICE_LEAD = 0.4   # caption/card first, voice a beat later
VOICE_TAIL = 0.6   # breathing room after the last word of a shot
CARD_MIN = 3.0     # a card without voice-over stays at least this long

READY_JS = """() => !document.querySelector(
    '.o_loading_indicator, .o_blockUI, .o-autocomplete--spinner')"""


class StepError(RuntimeError):
    pass


# --------------------------------------------------------------- capture
class X11Capture:
    def __init__(self, out_dir, display=None):
        self.path = os.path.join(out_dir, "raw.mkv")
        self.display = display
        self.xvfb = None
        self.ffmpeg = None

    def browser_args(self):
        return [f"--window-size={WIDTH},{HEIGHT}", "--window-position=0,0",
                "--force-device-scale-factor=1", "--hide-scrollbars"]

    def launch_env(self):
        if not self.display:
            self.display = ":97"
            self.xvfb = subprocess.Popen(
                ["Xvfb", self.display, "-screen", "0", f"{WIDTH}x{HEIGHT}x24", "-nolisten", "tcp"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(1.0)
        return {**os.environ, "DISPLAY": self.display}

    def start(self):
        # -copyts keeps x11grab's wall-clock timestamps in the file, which is
        # what lets the voice-over line up with the shots frame-exactly.
        self.ffmpeg = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "x11grab", "-draw_mouse", "0",
             "-framerate", "30", "-video_size", f"{WIDTH}x{HEIGHT}", "-i", self.display,
             "-copyts", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12", self.path],
            stdin=subprocess.PIPE,
        )
        time.sleep(0.5)

    def stop(self):
        if self.ffmpeg and self.ffmpeg.poll() is None:
            self.ffmpeg.communicate(b"q", timeout=60)

    def close(self):
        """After the browser is gone: the display it was drawing on."""
        self.stop()
        if self.xvfb and self.xvfb.poll() is None:
            self.xvfb.terminate()

    def video_start_epoch(self):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=start_time",
             "-of", "csv=p=0", self.path], capture_output=True, text=True, check=True,
        ).stdout.strip()
        return float(out)


class PlaywrightCapture:
    def __init__(self, out_dir):
        self.dir = os.path.join(out_dir, "pw_video")
        self.path = None
        self.epoch = None

    def browser_args(self):
        return []

    def launch_env(self):
        return None

    def context_options(self):
        return {"record_video_dir": self.dir, "record_video_size": {"width": WIDTH, "height": HEIGHT}}

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        """Playwright writes the video when the context closes."""
        files = sorted(glob.glob(os.path.join(self.dir, "*.webm")), key=os.path.getmtime)
        self.path = files[-1] if files else None

    def video_start_epoch(self):
        return self.epoch


class NoCapture:
    """Rehearsal: run the storyboard headless, no recording, no holds."""

    path = None
    epoch = None

    def browser_args(self):
        return []

    def launch_env(self):
        return None

    def context_options(self):
        return {}

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass

    def video_start_epoch(self):
        return None


# ----------------------------------------------------------------- steps
class Director:
    """Runs storyboard steps on an Odoo page, with a visible cursor."""

    def __init__(self, page, base_url):
        self.page = page
        self.base_url = base_url.rstrip("/")

    # -- helpers
    def ready(self, settle=0.6):
        page = self.page
        page.wait_for_selector(".o_main_navbar", timeout=30000)
        try:
            page.wait_for_function(READY_JS, timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(int(settle * 1000))

    def target(self, spec, scope=None):
        """Storyboard target → Playwright locator.

        A plain string is the visible text of a button, link, menu or tab.
        A dict picks the kind: {field: name}, {selector: css}, {text: …},
        {button: …}; ``in`` scopes it to a CSS container.
        """
        page = scope or self.page
        if isinstance(spec, dict) and "in" in spec:
            page = self.page.locator(spec["in"]).first
            spec = {k: v for k, v in spec.items() if k != "in"}
        if isinstance(spec, str):
            spec = {"text": spec}
        if "selector" in spec:
            loc = page.locator(spec["selector"])
        elif "field" in spec:
            loc = page.locator(f".o_form_view .o_field_widget[name='{spec['field']}']")
        elif "button" in spec:
            loc = page.get_by_role("button", name=spec["button"], exact=True)
        else:
            text = spec["text"]
            loc = (
                page.get_by_role("button", name=text, exact=True)
                .or_(page.get_by_role("link", name=text, exact=True))
                .or_(page.get_by_role("menuitem", name=text, exact=True))
                .or_(page.get_by_role("tab", name=text, exact=True))
                .or_(page.get_by_text(text, exact=True))
            )
        loc = loc.filter(visible=True).first
        try:
            loc.wait_for(state="visible", timeout=15000)
        except Exception as exc:
            raise StepError(f"not found on screen: {spec}") from exc
        return loc

    def move_to(self, loc, steps=28):
        box = loc.bounding_box()
        if not box:
            raise StepError("target has no position on screen")
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        self.page.mouse.move(x, y, steps=steps)
        self.page.wait_for_timeout(180)
        return x, y

    def _click(self, loc):
        x, y = self.move_to(loc)
        self.page.mouse.click(x, y)

    # -- step implementations
    def step_goto(self, path):
        self.page.goto(self.base_url + path)
        self.ready()

    def step_app(self, name):
        self._click(self.target({"selector": ".o_navbar_apps_menu button"}))
        self.page.wait_for_timeout(400)
        self._click(self.target({"selector": f".o_app:text-is('{name}')"}))
        self.ready()

    def step_menu(self, name):
        self._click(self.target({"text": name, "in": ".o_main_navbar"}))
        self.page.wait_for_timeout(300)
        self.ready()

    def step_click(self, spec):
        self._click(self.target(spec))
        self.ready(settle=0.5)

    def step_save(self, _=None):
        self._click(self.target({"selector": ".o_form_button_save"}))
        self.ready(settle=0.8)

    def step_fill(self, spec):
        """{field: partner_id, value: "Peeters", pick: "Familie Peeters"}.

        Many2one fields type `value` and choose `pick` (default: `value`)
        from the autocomplete; selection fields choose the option labelled
        `value`; other fields are typed.
        """
        widget = self.target({"field": spec["field"]})
        select = widget.locator("select")
        if select.count():
            self.move_to(select.first)
            select.first.select_option(label=spec["value"])
            self.page.wait_for_timeout(300)
            return
        field = widget.locator("input, textarea").filter(visible=True).first
        self._click(field)
        if spec.get("clear", True):
            field.fill("")
        field.press_sequentially(str(spec["value"]), delay=spec.get("delay", 65))
        classes = widget.get_attribute("class") or ""
        if "o_field_many2one" in classes or "o_field_many2one" in (widget.inner_html() or ""):
            menu = self.page.locator(".o-autocomplete--dropdown-menu").filter(visible=True).first
            menu.wait_for(timeout=10000)
            self.page.wait_for_timeout(500)
            option = menu.get_by_text(spec.get("pick", spec["value"]), exact=spec.get("exact", True))
            self._click(option.first)
        self.page.wait_for_timeout(400)

    def step_highlight(self, spec):
        seconds = spec.pop("seconds", 1.8) if isinstance(spec, dict) else 1.8
        box = self.target(spec).bounding_box()
        self.page.evaluate("r => window.__tv.highlight(r)", box)
        self.page.wait_for_timeout(int(seconds * 1000))
        self.page.evaluate("() => window.__tv.hideHighlight()")
        self.page.wait_for_timeout(350)

    def step_zoom(self, spec):
        spec = dict(spec)
        scale = spec.pop("scale", 1.8)
        seconds = spec.pop("seconds", None)
        box = self.target(spec).bounding_box()
        self.page.evaluate("([r, s]) => window.__tv.zoom(r, s)", [box, scale])
        self.page.wait_for_timeout(900)
        if seconds:
            self.page.wait_for_timeout(int(seconds * 1000))
            self.step_unzoom()

    def step_unzoom(self, _=None):
        self.page.evaluate("() => window.__tv.unzoom()")
        self.page.wait_for_timeout(900)

    def step_hover(self, spec):
        self.move_to(self.target(spec))

    def step_wait(self, seconds):
        self.page.wait_for_timeout(int(float(seconds) * 1000))

    def step_key(self, key):
        self.page.keyboard.press(key)
        self.ready(settle=0.3)

    def run(self, steps):
        for step in steps or []:
            if not isinstance(step, dict) or len(step) != 1:
                raise StepError(f"a step is one `action: argument` pair, got {step!r}")
            (action, arg), = step.items()
            handler = getattr(self, f"step_{action}", None)
            if not handler:
                raise StepError(f"unknown step '{action}'")
            handler(dict(arg) if isinstance(arg, dict) else arg)


# ---------------------------------------------------------------- record
def record(script, storyboard, voice_clips, out_dir, base_url, login, password,
           capture="x11", display=None, chromium=None, slow_mo=0):
    """Record all shots; returns the timeline (one dict per shot)."""
    os.makedirs(out_dir, exist_ok=True)
    for stale in ("error.png", "timeline.json"):
        if os.path.exists(os.path.join(out_dir, stale)):
            os.remove(os.path.join(out_dir, stale))
    cap = {"x11": lambda: X11Capture(out_dir, display),
           "playwright": lambda: PlaywrightCapture(out_dir),
           "none": NoCapture}[capture]()
    if capture == "x11" and not shutil.which("Xvfb") and not display:
        raise SystemExit("x11 capture needs Xvfb (or --display); use --capture playwright")
    boards = storyboard.get("shots", {})
    series = storyboard.get("series", "")
    timeline = []

    try:
        with sync_playwright() as pw:
            browser = _launch(pw, cap, capture, chromium, slow_mo)
            state = _login(browser, base_url, login, password)
            ctx_opts = {"storage_state": state, "locale": "nl-BE", "no_viewport": capture == "x11"}
            if capture != "x11":
                ctx_opts["viewport"] = {"width": WIDTH, "height": HEIGHT}
                ctx_opts.update(cap.context_options())
            context = browser.new_context(**ctx_opts)
            context.add_init_script(path=OVERLAY_JS)
            cap.epoch = time.time()
            page = context.new_page()
            if capture == "x11":
                _fullscreen(context, page)
            director = Director(page, base_url)

            # Starting screen, under the opening card, before the tape runs.
            first = script.shots[0]
            first_board = boards.get(first.number) or {}
            page.goto(base_url.rstrip("/") + storyboard.get("start", "/odoo"))
            director.ready()
            page.mouse.move(WIDTH * 0.62, HEIGHT * 0.55)
            if first_board.get("card"):
                page.evaluate("o => window.__tv.card(o)",
                              card_options(first, first_board, script, series, instant=True))
            cap.start()
            try:
                _play(page, director, script, boards, voice_clips, series, timeline,
                      rehearse=capture == "none")
            except Exception:
                png = os.path.join(out_dir, "error.png")
                page.screenshot(path=png)
                print(f"  failed; screen at that moment: {png}")
                raise
            page.wait_for_timeout(300)
            cap.stop()
            context.close()
            browser.close()
    finally:
        cap.close()

    meta = {"video": cap.path, "video_start": cap.video_start_epoch(), "shots": timeline}
    with open(os.path.join(out_dir, "timeline.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2, ensure_ascii=False)
    return meta


def _launch(pw, cap, capture, chromium, slow_mo):
    launch = {"headless": capture != "x11", "args": cap.browser_args(), "slow_mo": slow_mo}
    if chromium:
        launch["executable_path"] = chromium
    env = cap.launch_env()
    if env:
        launch["env"] = env
    return pw.chromium.launch(**launch)


def _fullscreen(context, page):
    """Hide tabs and address bar: Playwright opens its own window, so the
    --kiosk flag does not reach it; the DevTools protocol does."""
    cdp = context.new_cdp_session(page)
    window = cdp.send("Browser.getWindowForTarget")["windowId"]
    cdp.send("Browser.setWindowBounds", {"windowId": window, "bounds": {"windowState": "fullscreen"}})
    page.wait_for_timeout(500)


def _login(browser, base_url, login, password):
    """Log in outside the recording; the session is handed to the recording."""
    context = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT})
    page = context.new_page()
    page.goto(base_url.rstrip("/") + "/web/login")
    page.fill("input[name=login]", login)
    page.fill("input[name=password]", password)
    page.click("button[type=submit]")
    page.wait_for_selector(".o_main_navbar", timeout=60000)
    state = context.storage_state()
    context.close()
    return state


def _play(page, director, script, boards, voice_clips, series, timeline, rehearse=False):
    """Play every shot in front of the running capture."""
    page.wait_for_timeout(600)
    for index, shot in enumerate(script.shots):
        board = boards.get(shot.number) or {}
        clip = voice_clips.get(shot.number)
        start = time.time()
        if board.get("card"):
            page.evaluate("() => window.__tv.hideCaption()")
            page.evaluate("o => window.__tv.card(o)", card_options(shot, board, script, series))
        else:
            page.evaluate("() => window.__tv.hideCard()")
            if shot.caption and board.get("caption", True):
                page.evaluate("t => window.__tv.caption(t)", board.get("caption_text", shot.caption))
            else:
                page.evaluate("() => window.__tv.hideCaption()")
        print(f"  shot {shot.number}: {shot.caption or shot.picture[:50]}")
        director.run(board.get("steps"))

        # Prepare the next shot's screen while this one is still on
        # (typically behind a card), so the next shot opens on it.
        if index + 1 < len(script.shots):
            director.run((boards.get(script.shots[index + 1].number) or {}).get("setup"))

        if clip:
            wanted = VOICE_LEAD + clip["duration"] + VOICE_TAIL
        elif board.get("card"):
            wanted = max(shot.scripted_duration, CARD_MIN)
        else:
            wanted = 1.0
        wanted = max(wanted, float(board.get("min_seconds", 0)))
        remaining = wanted - (time.time() - start)
        if remaining > 0 and not rehearse:
            page.wait_for_timeout(int(remaining * 1000))
        page.evaluate("() => window.__tv.unzoom()")
        timeline.append({
            "shot": shot.number, "start": start, "end": time.time(),
            "voice": clip["path"] if clip else None,
            "voice_start": start + VOICE_LEAD if clip else None,
            "voice_duration": clip["duration"] if clip else 0.0,
            "voice_over": shot.voice_over, "caption": shot.caption,
        })


def card_options(shot, board, script, series, instant=False):
    card = board["card"]
    if isinstance(card, str):
        card = {"kind": card}
    kind = card.get("kind", "title")
    options = {"instant": instant, "light": bool(card.get("light"))}
    if kind == "html":
        options["html"] = card["html"]
        options["light"] = card.get("light", True)
    else:
        options["title"] = card.get("title") or shot.caption or script.title
        options["subtitle"] = card.get("subtitle", series)
    return options
