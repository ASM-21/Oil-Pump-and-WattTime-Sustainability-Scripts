# Findings from a correctness pass over this folder

No OpenLCA desktop or `olca_ipc`/`olca_schema` packages are available in
this environment, so nothing here could be run end to end. What follows is
static verification: syntax checks (`py_compile`), an AST-based check for
stdlib module attributes used without a matching import, and a manual read
of all four scripts, cross-checking numeric constants against each other.

## Fixed

**`update_static.py` — missing `import os` (real crash, fixed).**
The config block calls `os.getenv(...)` three times at module level but
`os` was never imported (only `from olca_ipc import Client` and
`import olca_schema as o`). Every sibling script in this folder (`update_gui.py`,
`OpenLCA_gui_tester_V8.py`, `OpenLCA tester Updater.py`) does `import os`;
this one didn't. Confirmed by executing the file's source with `olca_ipc`/
`olca_schema` stubbed out: raised `NameError: name 'os' is not defined`
before the fix, ran past that point cleanly after. This means the script
could never have run, ever, as committed -- it would fail on the first
non-import line before connecting to anything.

**`OpenLCA tester Updater.py` — DriveGear energy value ~100x too high (fixed).**
`printed_parts['DriveGear']` was `(42.1, 0.080957)`, next to a comment
showing an even older value `0.224604`. Every other value in the same dict
is in the 0.05-0.42 range, and both current canonical scripts
(`update_static.py`, `update_gui.py`) agree on `0.421000` for Drive Gear.
`42.1` looks like the digits of `0.421` typed past the decimal point.
Corrected to `0.421000` to match the canonical value; the older commented
value was not restored since it disagrees with the current scripts and
there's no way to tell here which was actually measured. This script is
already superseded by `update_static.py`/`update_gui.py` per the folder
README, so the practical risk was low, but if anyone still runs it for
comparison the number should not be 100x wrong.

## Flagged, not fixed

**`OpenLCA tester Updater.py` — internal contradiction about units.**
`update_exchange()` computes `mean_mj = mean_kwh * 1` (literally times one,
no conversion) but its own print statements assume the *old* value read
back from the exchange is in MJ (`f"{old_value/3.6:.6f} kWh"`, using the
correct 1 kWh = 3.6 MJ factor). Both can't be right: either the exchange
unit isn't MJ (so the read-side conversion is spurious) or the write is
silently missing a `* 3.6` and every push through this file would land
~3.6x low. The current canonical scripts (`update_static.py`, `update_gui.py`)
write `mean_kwh` directly with no MJ arithmetic anywhere, which is simpler
and doesn't have this contradiction. Left as a code comment in the file
rather than "fixed" since there's no way to confirm the true exchange unit
without a live OpenLCA connection -- don't use this file as a reference for
units; use the canonical scripts.

**GUI scripts update Tkinter widgets from background threads.**
`update_gui.py`'s `_do_connect_and_refresh`, `_do_refresh`, `_do_calc`, and
`_push_row`'s inner `do_push` all run via `threading.Thread(...).start()`
and then call `.config()`/`.set()` on Tkinter widgets/variables (and, in
`_push_row`, `messagebox.showerror`) directly from that background thread,
not marshaled back to the main loop via `self.after(...)`. This is a known
Tkinter anti-pattern -- it often appears to work because of the GIL, but
`Tcl/Tk` itself is not thread-safe and creating dialogs (`messagebox`) from
a non-main thread is a documented source of crashes/hangs on some platforms.
Not fixed here: this needs a live display and a real IPC connection to
trigger and verify, neither of which is available in this environment, and
a speculative refactor of the threading model without being able to run the
GUI risks introducing a worse, unverified bug. If this GUI is put in front
of real users, route the background-thread callbacks through
`self.after(0, lambda: ...)` and confirm interactively.

## Not found

- No hardcoded private IPs, filesystem paths, or UUIDs in any of the four
  scripts (checked via grep for IP patterns, `C:\`, `/Users/`, `/home/<user>/`,
  and canonical UUID shape) -- the README's safety-note concern about this
  appears to already be addressed, consistent with `config.py`-style
  environment-variable defaults (`os.getenv(..., "PLACEHOLDER")`) used
  throughout.
- AST-based check for stdlib-module attribute use without a matching
  `import` (the same class of bug as the `update_static.py` fix) came back
  clean on all four files after the fix.
