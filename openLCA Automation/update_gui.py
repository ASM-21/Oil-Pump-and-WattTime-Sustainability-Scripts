"""
update_gui.py
-------------
Tkinter GUI for inspecting and updating oil pump energy values in OpenLCA.

Layout:
  - Table: Component | Current (live from server) | New Value | Status | Push
  - "Refresh from Server" button reloads current values
  - "Run Calculation" button triggers LCIA and shows total kg CO2eq

To use:
  1. Fill in PRODUCT_SYSTEM_ID and LCIA_METHOD_ID once you have the UUIDs.
  2. Run: python update_gui.py
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox
import threading

from olca_ipc import Client
import olca_schema as o


# ============================================================================
# CONFIGURATION
# ============================================================================

SERVER_URL        = os.getenv("OPENLCA_SERVER_URL", "http://localhost:8080")
PROCESS_ID        = os.getenv("OPENLCA_PROCESS_ID", "PLACEHOLDER")
PRODUCT_SYSTEM_ID = os.getenv("OPENLCA_PRODUCT_SYSTEM_ID", "PLACEHOLDER")
LCIA_METHOD_ID    = os.getenv("OPENLCA_LCIA_METHOD_ID", "PLACEHOLDER")

# Default energy values (mean_kWh, std_kWh)
# Edit these to change what populates the "New Value" column on startup
DEFAULT_VALUES: dict[str, tuple[float, float]] = {
    "Body P1":    (0.343995, 0.088048),
    "Body P2":    (0.084313, 0.084543),
    "Body P3":    (0.005297, 0.001486),
    "Body P4":    (0.065401, 0.061080),
    "Lid P1":     (0.127831, 0.003187),
    "Lid P2":     (0.173929, 0.013351),
    "Drive Gear": (0.421000, 0.080957),
    "Drive Shaft":(0.092925, 0.000015),
    "Idle Gear":  (0.219209, 0.006082),
    "Idle Shaft": (0.058885, 0.004750),
}

# Colors
COLOR_OK      = "#2ecc71"
COLOR_ERROR   = "#e74c3c"
COLOR_WARN    = "#f39c12"
COLOR_NEUTRAL = "#95a5a6"
COLOR_BG      = "#1e1e2e"
COLOR_SURFACE = "#2a2a3e"
COLOR_TEXT    = "#cdd6f4"
COLOR_MUTED   = "#6c7086"
COLOR_ACCENT  = "#89b4fa"


# ============================================================================
# IPC HELPERS (no GUI dependencies)
# ============================================================================

def make_client() -> Client:
    return Client(SERVER_URL)


def fetch_process(client: Client) -> o.Process:
    process = client.get(o.Process, PROCESS_ID)
    if not process:
        raise ValueError(f"Process not found: {PROCESS_ID}")
    return process


def find_exchange(process: o.Process, description: str) -> o.Exchange | None:
    for ex in process.exchanges:
        if not ex.is_input or not ex.flow:
            continue
        if "electricity" not in ex.flow.name.lower():
            continue
        if description.lower() in (ex.description or "").lower():
            return ex
    return None


def push_exchange(client: Client, description: str, mean_kwh: float, std_kwh: float):
    """Fetch process, update one exchange, save back to server."""
    process = fetch_process(client)
    ex = find_exchange(process, description)
    if ex is None:
        raise ValueError(f"Exchange not found for description: '{description}'")
    old = ex.amount
    ex.amount = mean_kwh
    ex.uncertainty = o.Uncertainty(
        distribution_type=o.UncertaintyType.NORMAL_DISTRIBUTION,
        mean=mean_kwh,
        sd=std_kwh,
    )
    client.put(process)
    return old


def get_current_values(client: Client) -> dict[str, float]:
    """Return {description: current_amount} for all electricity exchanges."""
    process = fetch_process(client)
    values = {}
    for ex in process.exchanges:
        if not ex.is_input or not ex.flow:
            continue
        if "electricity" not in ex.flow.name.lower():
            continue
        desc = (ex.description or "").strip()
        if desc:
            values[desc] = ex.amount
    return values


def run_lcia(client: Client) -> list[tuple[str, float, str]]:
    """Returns list of (category_name, amount, unit) for all impact categories."""
    if PRODUCT_SYSTEM_ID == "PLACEHOLDER" or LCIA_METHOD_ID == "PLACEHOLDER":
        raise ValueError("Fill in PRODUCT_SYSTEM_ID and LCIA_METHOD_ID in the config.")
    setup = o.CalculationSetup(
        target=o.Ref(ref_type=o.RefType.ProductSystem, id=PRODUCT_SYSTEM_ID),
        impact_method=o.Ref(ref_type=o.RefType.ImpactMethod, id=LCIA_METHOD_ID),
        amount=1.0,
    )
    result = client.calculate(setup)
    impacts = result.get_total_impacts()
    out = [(i.impact_category.name, i.amount, i.impact_category.ref_unit)
           for i in impacts]
    result.dispose()
    return out


# ============================================================================
# GUI
# ============================================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OpenLCA Energy Updater — Oil Pump")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)

        # State
        self.client: Client | None = None
        self.row_widgets: list[dict] = []  # one dict per component row

        self._build_ui()
        self._connect_and_refresh()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ---- Header bar ----
        header = tk.Frame(self, bg=COLOR_BG, pady=8)
        header.pack(fill="x", padx=16)

        tk.Label(header, text="OpenLCA Energy Updater",
                 font=("Helvetica", 16, "bold"),
                 bg=COLOR_BG, fg=COLOR_ACCENT).pack(side="left")

        self.status_label = tk.Label(header, text="Connecting...",
                                     font=("Helvetica", 10),
                                     bg=COLOR_BG, fg=COLOR_MUTED)
        self.status_label.pack(side="right")

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=8)

        # ---- Table ----
        table_frame = tk.Frame(self, bg=COLOR_BG)
        table_frame.pack(fill="both", expand=True, padx=16, pady=(12, 4))

        headers = ["Component", "Current (kWh)", "New Value (kWh)", "Std Dev (kWh)", "Status", ""]
        col_widths = [12, 14, 14, 13, 10, 8]

        for col, (h, w) in enumerate(zip(headers, col_widths)):
            tk.Label(table_frame, text=h, width=w, anchor="w",
                     font=("Helvetica", 10, "bold"),
                     bg=COLOR_BG, fg=COLOR_MUTED).grid(
                row=0, column=col, padx=4, pady=(0, 6), sticky="w")

        for row_idx, (desc, (mean, std)) in enumerate(DEFAULT_VALUES.items(), start=1):
            row = {}

            # Component name
            tk.Label(table_frame, text=desc, width=12, anchor="w",
                     bg=COLOR_BG, fg=COLOR_TEXT,
                     font=("Helvetica", 10)).grid(
                row=row_idx, column=0, padx=4, pady=3, sticky="w")

            # Current value (populated after refresh)
            current_var = tk.StringVar(value="—")
            tk.Label(table_frame, textvariable=current_var, width=14, anchor="w",
                     bg=COLOR_BG, fg=COLOR_MUTED,
                     font=("Courier", 10)).grid(
                row=row_idx, column=1, padx=4, pady=3, sticky="w")

            # New value (editable)
            new_var = tk.StringVar(value=f"{mean:.6f}")
            entry = tk.Entry(table_frame, textvariable=new_var, width=14,
                             bg=COLOR_SURFACE, fg=COLOR_TEXT,
                             insertbackground=COLOR_TEXT,
                             relief="flat", font=("Courier", 10))
            entry.grid(row=row_idx, column=2, padx=4, pady=3, sticky="w")

            # Std dev (editable)
            std_var = tk.StringVar(value=f"{std:.6f}")
            std_entry = tk.Entry(table_frame, textvariable=std_var, width=13,
                                 bg=COLOR_SURFACE, fg=COLOR_TEXT,
                                 insertbackground=COLOR_TEXT,
                                 relief="flat", font=("Courier", 10))
            std_entry.grid(row=row_idx, column=3, padx=4, pady=3, sticky="w")

            # Status
            status_var = tk.StringVar(value="")
            status_lbl = tk.Label(table_frame, textvariable=status_var, width=10,
                                  anchor="w", bg=COLOR_BG, fg=COLOR_NEUTRAL,
                                  font=("Helvetica", 9))
            status_lbl.grid(row=row_idx, column=4, padx=4, pady=3, sticky="w")

            # Push button
            btn = tk.Button(table_frame, text="Push",
                            bg=COLOR_ACCENT, fg=COLOR_BG,
                            font=("Helvetica", 9, "bold"),
                            relief="flat", padx=8, pady=2,
                            command=lambda d=desc, nv=new_var, sv=std_var,
                                           sl=status_lbl, svv=status_var:
                                self._push_row(d, nv, sv, sl, svv))
            btn.grid(row=row_idx, column=5, padx=4, pady=3)

            row.update({
                "desc": desc,
                "current_var": current_var,
                "new_var": new_var,
                "std_var": std_var,
                "status_var": status_var,
                "status_lbl": status_lbl,
            })
            self.row_widgets.append(row)

        # ---- Bottom buttons ----
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=8, pady=(8, 0))

        bottom = tk.Frame(self, bg=COLOR_BG, pady=10)
        bottom.pack(fill="x", padx=16)

        tk.Button(bottom, text="Refresh from Server",
                  bg=COLOR_SURFACE, fg=COLOR_TEXT,
                  font=("Helvetica", 10), relief="flat", padx=12, pady=4,
                  command=self._refresh_in_thread).pack(side="left", padx=(0, 8))

        tk.Button(bottom, text="Run Calculation",
                  bg=COLOR_SURFACE, fg=COLOR_ACCENT,
                  font=("Helvetica", 10, "bold"), relief="flat", padx=12, pady=4,
                  command=self._calc_in_thread).pack(side="left")

        self.result_label = tk.Label(bottom, text="",
                                     font=("Helvetica", 11, "bold"),
                                     bg=COLOR_BG, fg=COLOR_OK)
        self.result_label.pack(side="right")

    # ------------------------------------------------------------------
    # Threading wrappers (keep UI responsive)
    # ------------------------------------------------------------------

    def _connect_and_refresh(self):
        threading.Thread(target=self._do_connect_and_refresh, daemon=True).start()

    def _do_connect_and_refresh(self):
        self._set_status("Connecting...", COLOR_WARN)
        try:
            self.client = make_client()
            self._set_status(f"Connected — {SERVER_URL}", COLOR_OK)
            self._do_refresh()
        except Exception as e:
            self._set_status(f"Connection failed: {e}", COLOR_ERROR)
            self.client = None

    def _refresh_in_thread(self):
        if not self.client:
            messagebox.showerror("Not connected", "No active connection to server.")
            return
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        self._set_status("Fetching current values...", COLOR_WARN)
        try:
            live = get_current_values(self.client)
            for row in self.row_widgets:
                desc = row["desc"]
                # Match against live keys (case-insensitive substring)
                match = next((v for k, v in live.items()
                              if desc.lower() in k.lower()), None)
                if match is not None:
                    row["current_var"].set(f"{match:.6f}")
                else:
                    row["current_var"].set("not found")
            self._set_status(f"Connected — {SERVER_URL}", COLOR_OK)
        except Exception as e:
            self._set_status(f"Refresh failed: {e}", COLOR_ERROR)

    def _calc_in_thread(self):
        if not self.client:
            messagebox.showerror("Not connected", "No active connection to server.")
            return
        threading.Thread(target=self._do_calc, daemon=True).start()

    def _do_calc(self):
        self.result_label.config(text="Calculating...", fg=COLOR_WARN)
        try:
            impacts = run_lcia(self.client)
            # Find GWP / climate change category
            gwp = next(
                ((name, amt, unit) for name, amt, unit in impacts
                 if any(k in name.lower() for k in ("climate", "gwp", "co2", "global warm"))),
                None
            )
            if gwp:
                name, amt, unit = gwp
                self.result_label.config(
                    text=f"Total: {amt:.4f} {unit}  ({name})",
                    fg=COLOR_OK)
            else:
                cats = ", ".join(n for n, _, _ in impacts[:4])
                self.result_label.config(
                    text=f"No GWP category found. Available: {cats}",
                    fg=COLOR_WARN)
        except ValueError as e:
            # Placeholder UUIDs
            self.result_label.config(text=str(e), fg=COLOR_WARN)
        except Exception as e:
            self.result_label.config(text=f"Calculation failed: {e}", fg=COLOR_ERROR)

    # ------------------------------------------------------------------
    # Per-row push
    # ------------------------------------------------------------------

    def _push_row(self, desc: str, new_var: tk.StringVar, std_var: tk.StringVar,
                  status_lbl: tk.Label, status_var: tk.StringVar):
        if not self.client:
            messagebox.showerror("Not connected", "No active connection to server.")
            return

        try:
            mean = float(new_var.get())
            std  = float(std_var.get())
        except ValueError:
            status_var.set("Bad input")
            status_lbl.config(fg=COLOR_ERROR)
            return

        status_var.set("Pushing...")
        status_lbl.config(fg=COLOR_WARN)

        def do_push():
            try:
                old = push_exchange(self.client, desc, mean, std)
                # Update current column to reflect what was just saved
                for row in self.row_widgets:
                    if row["desc"] == desc:
                        row["current_var"].set(f"{mean:.6f}")
                        break
                status_var.set(f"OK  ({old:.4f}→{mean:.4f})")
                status_lbl.config(fg=COLOR_OK)
            except Exception as e:
                status_var.set("Failed")
                status_lbl.config(fg=COLOR_ERROR)
                messagebox.showerror("Push failed", f"{desc}: {e}")

        threading.Thread(target=do_push, daemon=True).start()

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _set_status(self, text: str, color: str):
        self.status_label.config(text=text, fg=color)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    app = App()
    app.mainloop()
