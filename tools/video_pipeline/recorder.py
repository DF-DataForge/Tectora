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
            # A free display number, so several recordings can run at once.
            number = next(n for n in range(97, 160)
                          if not os.path.exists(f"/tmp/.X{n}-lock")
                          and not os.path.exists(f"/tmp/.X11-unix/X{n}"))
            self.display = f":{number}"
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

    def __init__(self, page, base_url, db=None):
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.db = db
        self.phone = None  # FrameLocator of the phone frame while it is shown

    @property
    def scope(self):
        return self.phone or self.page

    # -- helpers
    def ready(self, settle=0.6):
        page = self.page
        if self.phone:
            # A click may start a page load in the frame: let it begin, then
            # wait until the new page is loaded.
            page.wait_for_timeout(300)
            frame = page.locator("#tv-phone iframe").element_handle().content_frame()
            if frame:
                frame.wait_for_load_state("load", timeout=30000)
            self.phone.locator("#wrapwrap").wait_for(timeout=30000)
            page.wait_for_timeout(int(settle * 1000))
            return
        # Backend (navbar) or a portal/website page (#wrapwrap).
        page.wait_for_selector(".o_main_navbar, #wrapwrap", timeout=30000)
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
        page = scope or self.scope
        if isinstance(spec, dict) and "in" in spec:
            page = self.scope.locator(spec["in"]).first
            spec = {k: v for k, v in spec.items() if k != "in"}
        if isinstance(spec, str):
            spec = {"text": spec}
        if "selector" in spec:
            loc = page.locator(spec["selector"])
        elif "field" in spec:
            loc = page.locator(f".o_form_view .o_field_widget[name='{spec['field']}'], "
                               f".modal .o_field_widget[name='{spec['field']}']")
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
        if self.phone:
            # The phone screen is small: scroll the target into it first.
            if loc.evaluate("e => { const r = e.getBoundingClientRect(); const out = r.top < 0 "
                            "|| r.bottom > innerHeight; if (out) e.scrollIntoView("
                            "{behavior: 'smooth', block: 'center'}); return out; }"):
                self.page.wait_for_timeout(900)
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
        editor = widget.locator("[contenteditable='true']")
        if editor.count():
            # HTML field (Notities …): click into the editor and type.
            self._click(editor.first)
            self.step_type({"text": spec["value"], "delay": spec.get("delay", 35)})
            return
        field = widget.locator("input, textarea").filter(visible=True).first
        self._click(field)
        if spec.get("clear", True):
            field.fill("")
        field.press_sequentially(str(spec["value"]), delay=spec.get("delay", 65))
        # Many2one, many2many tags …: anything with an autocomplete dropdown.
        if "o-autocomplete--input" in (field.get_attribute("class") or "") or spec.get("pick"):
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

    def step_type(self, spec):
        """Type into whatever has the focus: "text" or {text, delay}."""
        if isinstance(spec, str):
            spec = {"text": spec}
        for n, line in enumerate(str(spec["text"]).split("\n")):
            if n:
                self.page.keyboard.press(spec.get("newline", "Enter"))
            self.page.keyboard.type(line, delay=spec.get("delay", 45))
        self.page.wait_for_timeout(300)

    def step_drag(self, spec):
        """{from: target, to: target}: press, glide, release."""
        start = self.move_to(self.target(spec["from"]))
        self.page.mouse.down()
        end_box = self.target(spec["to"]).bounding_box()
        x = end_box["x"] + end_box["width"] / 2 + spec.get("dx", 0)
        y = end_box["y"] + end_box["height"] / 2 + spec.get("dy", 0)
        # A small first move so the drag library notices the drag.
        self.page.mouse.move(start[0] + 8, start[1] + 8, steps=4)
        self.page.mouse.move(x, y, steps=spec.get("steps", 40))
        self.page.wait_for_timeout(250)
        self.page.mouse.up()
        self.ready(settle=0.6)

    def step_edit_cell(self, spec):
        """{row: text in the row, column: field name, value: …} in a list."""
        scope = self.scope.locator(spec.get("in", ".o_list_renderer")).first
        row = scope.locator("tr.o_data_row").filter(has_text=spec["row"]).first
        cell = row.locator(f"td[name='{spec['column']}']")
        self._click(cell)
        self.page.wait_for_timeout(300)
        field = row.locator(f"td[name='{spec['column']}'] input").first
        field.wait_for(timeout=5000)
        field.select_text()
        field.press_sequentially(str(spec["value"]), delay=spec.get("delay", 90))
        if spec.get("confirm", True):
            self.page.keyboard.press(spec.get("confirm_key", "Tab"))
        self.ready(settle=0.5)

    def step_scroll(self, spec):
        """{target…, dy: 400}: wheel-scroll over an element (default: page)."""
        spec = dict(spec)
        dy = spec.pop("dy", 400)
        if spec:
            self.move_to(self.target(spec), steps=15)
        for _ in range(8):
            self.page.mouse.wheel(0, dy / 8)
            self.page.wait_for_timeout(45)
        self.page.wait_for_timeout(400)

    def step_card(self, spec):
        """A card in the middle of a shot, e.g. to cover a user switch."""
        options = dict(spec or {})
        options.setdefault("light", bool(options.get("html")))
        self.page.evaluate("o => window.__tv.card(o)", options)
        self.page.wait_for_timeout(500)

    def step_hide_card(self, _=None):
        self.page.evaluate("() => window.__tv.hideCard()")
        self.page.wait_for_timeout(500)

    def step_login(self, spec):
        """{login, password, path}: switch user (cover it with a card).

        The log-out and log-in go over HTTP with the browser's cookies, so
        the page itself only loads `path`: a card on screen stays on screen
        (Odoo's log-out would clear the overlay's sessionStorage)."""
        import re

        page = self.page
        request = page.context.request
        request.get(self.base_url + "/web/session/logout")
        form = request.get(self.base_url + "/web/login" + (f"?db={self.db}" if self.db else "")).text()
        token = re.search(r'name="csrf_token"\s+value="([^"]+)"', form)
        response = request.post(self.base_url + "/web/login", form={
            "login": spec["login"], "password": spec.get("password", spec["login"]),
            "csrf_token": token.group(1) if token else "", "redirect": spec.get("path", "/my"),
        })
        if "/web/login" in response.url:
            raise StepError(f"log-in as {spec['login']} failed")
        page.goto(self.base_url + spec.get("path", "/my"))
        self.ready()

    def step_phone(self, spec):
        """Show a page in a smartphone frame: "/my/werven" or {path}."""
        path = spec if isinstance(spec, str) else spec["path"]
        self.page.evaluate("src => window.__tv.phone(src)", self.base_url + path)
        self.phone = self.page.frame_locator("#tv-phone iframe")
        self.ready(settle=1.0)
        # After a page load the drawn cursor has no position yet: put it on the phone.
        self.page.mouse.move(WIDTH / 2 + 60, HEIGHT / 2 + 160, steps=4)

    def step_phone_close(self, _=None):
        self.page.evaluate("() => window.__tv.hidePhone()")
        self.phone = None
        self.page.wait_for_timeout(500)

    def step_show_pdf(self, spec):
        """{url, pages: [1, 2], title}: a printed report, page by page."""
        import base64
        import tempfile

        response = self.page.request.get(self.base_url + spec["url"])
        if not response.ok:
            raise StepError(f"report {spec['url']}: HTTP {response.status}")
        pages = spec.get("pages", [1])
        with tempfile.TemporaryDirectory() as tmp:
            pdf = os.path.join(tmp, "report.pdf")
            with open(pdf, "wb") as handle:
                handle.write(response.body())
            images = []
            for number in pages:
                out = os.path.join(tmp, f"p{number}")
                subprocess.run(["pdftoppm", "-png", "-r", "110", "-f", str(number), "-l", str(number),
                                "-singlefile", pdf, out], check=True)
                with open(out + ".png", "rb") as handle:
                    images.append(base64.b64encode(handle.read()).decode())
        height = spec.get("height", 960)
        tags = "".join(
            f'<img src="data:image/png;base64,{img}" style="height:{height}px;box-shadow:0 12px 40px '
            f'rgba(0,0,0,.25);border-radius:4px;background:#fff"/>' for img in images)
        self.step_card({"html": f'<div style="display:flex;gap:36px;align-items:center">{tags}</div>',
                        "light": True})
        if spec.get("seconds"):
            self.page.wait_for_timeout(int(spec["seconds"] * 1000))

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
           capture="x11", display=None, chromium=None, slow_mo=0, db=None):
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
            state = _login(browser, base_url, login, password, db)
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
            director = Director(page, base_url, db)

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


def _login(browser, base_url, login, password, db=None):
    """Log in outside the recording; the session is handed to the recording."""
    context = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT})
    page = context.new_page()
    page.goto(base_url.rstrip("/") + "/web/login" + (f"?db={db}" if db else ""))
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
