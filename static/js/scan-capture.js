/* Counter-screen barcode capture, shared by Barcode Scanner and Returns.
 *
 * A USB/Bluetooth reader behaves like a keyboard: it types the code far
 * faster than a person can and usually sends Enter afterwards. Keystrokes are
 * read at the document level so the reader is heard even when nothing has
 * focus - the operator can scan the moment the page is up.
 *
 * Telling a reader from a person matters. Some readers are configured with no
 * Enter suffix, so the code has to be submitted once the keystrokes stop; but
 * applying that to someone typing by hand submits a half-written barcode the
 * moment they pause to think. So a burst is only submitted on its own if it
 * arrived at machine speed. Anything slower waits for Enter, however long the
 * person takes.
 *
 * Expects #scan-form and #scan-input, and optionally #scan-state.
 */
(function () {
    "use strict";

    var form = document.getElementById("scan-form");
    var input = document.getElementById("scan-input");
    var state = document.getElementById("scan-state");
    if (!form || !input) return;

    // A reader lands its keys within a few ms of each other. Human typing is
    // an order of magnitude slower, so this gap cleanly separates the two.
    var SCANNER_MAX_GAP_MS = 35;
    // Gap after which the next keystroke starts a fresh code.
    var BURST_GAP_MS = 500;
    // How long to wait after a scanner burst stops before submitting it.
    var IDLE_SUBMIT_MS = 120;
    // Shorter than this is a stray keypress, not a barcode.
    var MIN_CODE_LENGTH = 6;

    var buffer = "";
    var gaps = [];
    var lastKeyAt = 0;
    var idleTimer = null;
    var submitted = false;

    function looksLikeScanner() {
        // Need a few intervals before the speed means anything.
        if (gaps.length < MIN_CODE_LENGTH - 1) return false;
        var total = gaps.reduce(function (a, b) { return a + b; }, 0);
        return total / gaps.length < SCANNER_MAX_GAP_MS;
    }

    function submit(value) {
        if (submitted) return;
        var code = (value || "").trim();
        if (!code) return;
        submitted = true;
        clearTimeout(idleTimer);
        input.value = code;
        if (state) {
            state.textContent = "Looking up " + code;
            state.classList.add("is-busy");
        }
        form.submit();
    }

    function reset() {
        buffer = "";
        gaps = [];
        lastKeyAt = 0;
        clearTimeout(idleTimer);
    }

    document.addEventListener("keydown", function (e) {
        if (e.ctrlKey || e.metaKey || e.altKey) return;

        // Never swallow typing meant for another field - the quantity and
        // reason boxes on the Returns page, for instance.
        var active = document.activeElement;
        if (active && active !== input &&
            /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName)) {
            return;
        }

        if (e.key === "Enter") {
            // Enter always submits, whoever sent it: the reader's own
            // terminator, or the operator finishing a typed code.
            var typed = active === input ? input.value : buffer;
            if (typed && typed.trim()) {
                e.preventDefault();
                submit(typed);
            }
            return;
        }

        if (e.key.length !== 1) return;   // Shift, Tab, arrows, F-keys...

        var now = Date.now();
        if (!lastKeyAt || now - lastKeyAt > BURST_GAP_MS) {
            buffer = "";
            gaps = [];
        } else {
            gaps.push(now - lastKeyAt);
        }
        lastKeyAt = now;
        buffer += e.key;

        // Mirror keystrokes into the box when they landed outside it, so the
        // operator always sees what the reader sent.
        if (active !== input) {
            input.value = buffer;
        } else {
            buffer = input.value;
        }

        // Only a machine-speed burst submits itself. A person's typing sits
        // here untouched until they press Enter.
        clearTimeout(idleTimer);
        idleTimer = setTimeout(function () {
            if (input.value.trim().length >= MIN_CODE_LENGTH && looksLikeScanner()) {
                submit(input.value);
            }
        }, IDLE_SUBMIT_MS);
    });

    // A code already in the box means a lookup just happened; leave the caret
    // in it, selected, so the next scan overwrites rather than appends.
    input.focus();
    if (input.value) input.select();
    reset();

    // Keep the caret in the box so a reader's keystrokes are never lost.
    setInterval(function () {
        if (document.activeElement === document.body) input.focus();
    }, 1000);
})();
