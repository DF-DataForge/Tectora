/* Medewerkersportaal: the running timer ticks and the active tab is kept in
   the URL, so a refresh (after Start/Stop or a new report) lands on the same
   tab. Plain script: nothing here needs the web client. */
(function () {
    "use strict";

    function pad(value) {
        return value < 10 ? "0" + value : "" + value;
    }

    function tickElapsed() {
        var nodes = document.querySelectorAll(".o_tectora_elapsed[data-start]");
        if (!nodes.length) {
            return;
        }
        var now = Date.now();
        nodes.forEach(function (node) {
            var start = Date.parse(node.dataset.start);
            if (isNaN(start)) {
                return;
            }
            var seconds = Math.max(0, Math.floor((now - start) / 1000));
            var hours = Math.floor(seconds / 3600);
            var minutes = Math.floor((seconds % 3600) / 60);
            var secs = seconds % 60;
            node.textContent = hours + ":" + pad(minutes) + ":" + pad(secs);
        });
    }

    function rememberTab() {
        var links = document.querySelectorAll('.o_tectora_tabs [data-bs-toggle="tab"][data-tab]');
        links.forEach(function (link) {
            link.addEventListener("shown.bs.tab", function () {
                try {
                    var url = new URL(window.location.href);
                    url.searchParams.set("tab", link.dataset.tab);
                    url.searchParams.delete("message");
                    url.searchParams.delete("error");
                    window.history.replaceState({}, "", url.toString());
                } catch (error) {
                    /* the URL API is unavailable: the tab still switches */
                }
                document.querySelectorAll(".o_tectora_tab_input").forEach(function (input) {
                    input.value = link.dataset.tab;
                });
            });
        });
    }

    function confirmStop() {
        var form = document.querySelector(".o_tectora_stop_form");
        if (!form) {
            return;
        }
        form.addEventListener("submit", function (event) {
            var checked = form.querySelectorAll('input[name="employee_ids"]:checked');
            if (!checked.length) {
                event.preventDefault();
                var warning = form.querySelector(".o_tectora_stop_warning");
                if (warning) {
                    warning.classList.remove("d-none");
                }
            }
        });
    }

    function start() {
        if (!document.querySelector(".o_tectora_portal")) {
            return;
        }
        tickElapsed();
        window.setInterval(tickElapsed, 1000);
        rememberTab();
        confirmStop();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
