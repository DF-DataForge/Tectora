// Injected into every page of the recording (context.add_init_script).
// Draws everything that is not Odoo itself: cursor, click ripples, the
// "Tekst in beeld" caption, opening/end cards, highlights and zoom.
// The root hangs on <html>, outside <body>, so zooming the body (Odoo's
// web client) leaves the overlay untouched.
(() => {
    if (window.__tv) {
        return;
    }
    if (window.top !== window) {
        // Inside the phone frame: the cursor lives on the top page, so pass
        // the mouse up, converted to top-page coordinates.
        const toTop = (ev) => {
            const frame = window.frameElement;
            if (!frame || !window.top.__tv) {
                return null;
            }
            const r = frame.getBoundingClientRect();
            const scale = r.width / frame.clientWidth;
            return [r.left + ev.clientX * scale, r.top + ev.clientY * scale];
        };
        window.addEventListener("mousemove", (ev) => {
            const p = toTop(ev);
            if (p) {
                window.top.__tv.cursorAt(...p);
            }
        }, true);
        window.addEventListener("mousedown", (ev) => {
            const p = toTop(ev);
            if (p) {
                window.top.__tv.ripple(...p);
            }
        }, true);
        return;
    }
    const BRAND = "#2D8D8F";
    const FONT = "'Montserrat', 'Segoe UI', Arial, sans-serif";
    const LOGO_WHITE = "/tectora_report_layout/static/src/img/tectora_logo_white.svg";
    const CSS = `
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700&display=swap');
        #tv-root { position: fixed; inset: 0; pointer-events: none; z-index: 2147483000; font-family: ${FONT}; }
        #tv-cursor { position: fixed; left: 0; top: 0; width: 26px; height: 26px; transform: translate(-3px, -2px);
            transition: opacity .2s; filter: drop-shadow(0 2px 3px rgba(0,0,0,.35)); }
        .tv-ripple { position: fixed; width: 18px; height: 18px; margin: -9px 0 0 -9px; border-radius: 50%;
            border: 3px solid ${BRAND}; background: ${BRAND}33; animation: tv-ripple .6s ease-out forwards; }
        @keyframes tv-ripple { to { transform: scale(3.2); opacity: 0; } }
        #tv-caption { position: fixed; left: 48px; bottom: 56px; max-width: 70%; padding: 14px 26px 14px 22px;
            background: ${BRAND}; color: #fff; font-weight: 600; font-size: 30px; line-height: 1.25;
            border-left: 8px solid #fff; border-radius: 4px; box-shadow: 0 8px 24px rgba(0,0,0,.25);
            opacity: 0; transform: translateX(-40px); transition: opacity .35s, transform .35s; }
        #tv-caption.tv-on { opacity: 1; transform: none; }
        #tv-card { position: fixed; inset: 0; display: flex; flex-direction: column; align-items: center;
            justify-content: center; gap: 28px; background: ${BRAND}; color: #fff; text-align: center;
            opacity: 0; transition: opacity .45s; }
        #tv-card.tv-on { opacity: 1; }
        #tv-card img { height: 92px; }
        #tv-card .tv-title { font-size: 68px; font-weight: 700; max-width: 80%; }
        #tv-card .tv-subtitle { font-size: 30px; font-weight: 500; opacity: .85; }
        #tv-card.tv-light { background: #f4f7f7; color: #1d2b2b; }
        #tv-highlight { position: fixed; border: 4px solid ${BRAND}; border-radius: 10px;
            box-shadow: 0 0 0 9999px rgba(15, 30, 30, .35); opacity: 0; transition: all .35s ease; }
        #tv-highlight.tv-on { opacity: 1; }
        #tv-phone { position: fixed; inset: 0; pointer-events: auto; display: flex; align-items: center;
            justify-content: center; background: radial-gradient(circle at 30% 20%, #e9f4f4, #cfe5e5);
            opacity: 0; transition: opacity .45s; }
        #tv-phone.tv-on { opacity: 1; }
        #tv-phone .tv-device { width: 390px; height: 844px; padding: 14px; border-radius: 54px; background: #111;
            box-shadow: 0 30px 80px rgba(0,0,0,.35); transform: scale(1.12); }
        #tv-phone iframe { width: 390px; height: 844px; border: 0; border-radius: 42px; background: #fff; }
        body.tv-zoomable { transition: transform .8s cubic-bezier(.4, 0, .2, 1); }
    `;
    const CURSOR_SVG = `<svg viewBox="0 0 24 24" width="26" height="26"><path d="M4 2l16 10.5-7.2 1.4 4.3 7.6-3 1.6-4.3-7.7L4 20.5z"
        fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>`;

    let root, cursor, caption, card, highlight;

    function mount() {
        if (root && root.isConnected) {
            return;
        }
        root = document.createElement("div");
        root.id = "tv-root";
        root.innerHTML = `<style>${CSS}</style><div id="tv-card"></div><div id="tv-highlight"></div>
            <div id="tv-caption"></div><div id="tv-cursor">${CURSOR_SVG}</div>`;
        document.documentElement.appendChild(root);
        cursor = root.querySelector("#tv-cursor");
        caption = root.querySelector("#tv-caption");
        card = root.querySelector("#tv-card");
        highlight = root.querySelector("#tv-highlight");
        const last = window.__tvLastMouse;
        if (last) {
            cursor.style.left = `${last[0]}px`;
            cursor.style.top = `${last[1]}px`;
        }
        const state = loadState();
        if (state.card) {
            api.card({ ...state.card, instant: true });
        }
        if (state.caption) {
            api.caption(state.caption, true);
        }
    }

    // Survives full page loads (page.goto), so a card or caption that is
    // on screen stays on screen while Odoo reloads underneath it.
    function loadState() {
        try {
            return JSON.parse(sessionStorage.getItem("__tvState") || "{}");
        } catch {
            return {};
        }
    }
    function saveState(patch) {
        try {
            sessionStorage.setItem("__tvState", JSON.stringify({ ...loadState(), ...patch }));
        } catch {
            // Recording without overlay persistence is still a recording.
        }
    }

    function cursorAt(x, y) {
        window.__tvLastMouse = [x, y];
        if (cursor) {
            cursor.style.left = `${x}px`;
            cursor.style.top = `${y}px`;
        }
    }
    function ripple(x, y) {
        mount();
        const dot = document.createElement("div");
        dot.className = "tv-ripple";
        dot.style.left = `${x}px`;
        dot.style.top = `${y}px`;
        root.appendChild(dot);
        setTimeout(() => dot.remove(), 700);
    }
    window.addEventListener("mousemove", (ev) => cursorAt(ev.clientX, ev.clientY), true);
    window.addEventListener("mousedown", (ev) => ripple(ev.clientX, ev.clientY), true);

    const api = {
        mount,
        cursorAt,
        ripple,
        phone(src) {
            mount();
            let phone = root.querySelector("#tv-phone");
            if (!phone) {
                phone = document.createElement("div");
                phone.id = "tv-phone";
                phone.innerHTML = `<div class="tv-device"><iframe></iframe></div>`;
                root.insertBefore(phone, root.querySelector("#tv-highlight"));
            }
            phone.querySelector("iframe").src = src;
            requestAnimationFrame(() => phone.classList.add("tv-on"));
        },
        hidePhone() {
            const phone = root && root.querySelector("#tv-phone");
            if (phone) {
                phone.remove();
            }
        },
        caption(text, instant) {
            mount();
            saveState({ caption: text });
            caption.textContent = text;
            if (instant) {
                caption.style.transition = "none";
                caption.classList.add("tv-on");
                void caption.offsetWidth;
                caption.style.transition = "";
            } else {
                requestAnimationFrame(() => caption.classList.add("tv-on"));
            }
        },
        hideCaption() {
            mount();
            saveState({ caption: null });
            caption.classList.remove("tv-on");
        },
        card({ title = "", subtitle = "", html = "", light = false, instant = false } = {}) {
            mount();
            card.className = light ? "tv-light" : "";
            card.innerHTML = html || `<img src="${LOGO_WHITE}" alt=""/>
                <div class="tv-title"></div><div class="tv-subtitle"></div>`;
            if (!html) {
                card.querySelector(".tv-title").textContent = title;
                card.querySelector(".tv-subtitle").textContent = subtitle;
            }
            saveState({ card: { title, subtitle, html, light } });
            cursor.style.opacity = "0";
            if (instant) {
                card.style.transition = "none";
                card.classList.add("tv-on");
                void card.offsetWidth;
                card.style.transition = "";
            } else {
                requestAnimationFrame(() => card.classList.add("tv-on"));
            }
        },
        hideCard() {
            mount();
            saveState({ card: null });
            card.classList.remove("tv-on");
            cursor.style.opacity = "1";
        },
        highlight(rect, pad = 8) {
            mount();
            Object.assign(highlight.style, {
                left: `${rect.x - pad}px`, top: `${rect.y - pad}px`,
                width: `${rect.width + 2 * pad}px`, height: `${rect.height + 2 * pad}px`,
            });
            highlight.classList.add("tv-on");
        },
        hideHighlight() {
            mount();
            highlight.classList.remove("tv-on");
        },
        zoom(rect, scale) {
            const body = document.body;
            body.classList.add("tv-zoomable");
            const cx = rect.x + rect.width / 2;
            const cy = rect.y + rect.height / 2;
            // Keep the target centred but never pan past the page edges.
            const w = window.innerWidth, h = window.innerHeight;
            const tx = Math.min(0, Math.max(w - w * scale, w / 2 - cx * scale));
            const ty = Math.min(0, Math.max(h - h * scale, h / 2 - cy * scale));
            body.style.transformOrigin = "0 0";
            body.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
        },
        unzoom() {
            document.body.style.transform = "";
        },
    };
    window.__tv = api;
    // <html> exists before any content paints: mounting now means a card
    // covers the page from the very first frame of a reload.
    mount();
})();
