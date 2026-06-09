"""
update_static.py
----------------
Pushes hardcoded energy values to an OpenLCA process over IPC, then runs
an LCIA calculation and prints the total kg CO2eq for the oil pump product system.

To use:
  1. Edit the ENERGY_VALUES dict below with your measured kWh values.
  2. Fill in PRODUCT_SYSTEM_ID and LCIA_METHOD_ID once you have the UUIDs.
  3. Run: python update_static.py
"""

from olca_ipc import Client
import olca_schema as o


# ============================================================================
# CONFIGURATION — edit these values freely
# ============================================================================

SERVER_URL        = os.getenv("OPENLCA_SERVER_URL", "http://localhost:8080")
PROCESS_ID        = os.getenv("OPENLCA_PROCESS_ID", "PLACEHOLDER")
PRODUCT_SYSTEM_ID = os.getenv("OPENLCA_PRODUCT_SYSTEM_ID", "PLACEHOLDER")
LCIA_METHOD_ID    = os.getenv("OPENLCA_LCIA_METHOD_ID", "PLACEHOLDER")

# Energy values (mean_kWh, std_kWh)
# Description keys must match exactly what is in the OpenLCA process
ENERGY_VALUES: dict[str, tuple[float, float]] = {
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


# ============================================================================
# HELPERS
# ============================================================================

def connect(url: str) -> Client | None:
    print(f"Connecting to {url} ...")
    try:
        client = Client(url)
        print("  Connected.\n")
        return client
    except Exception as e:
        print(f"  Connection failed: {e}")
        print("  Confirm the IPC server is running: Tools > Developer Tools > IPC Server")
        return None


def get_process(client: Client, process_id: str) -> o.Process | None:
    try:
        process = client.get(o.Process, process_id)
        if not process:
            print(f"Process not found: {process_id}")
            return None
        print(f"Process: {process.name}  (id: {process.id})")
        return process
    except Exception as e:
        print(f"Error fetching process: {e}")
        return None


def find_exchange(process: o.Process, description: str) -> o.Exchange | None:
    """Return the first input electricity exchange whose description contains
    the given string (case-insensitive)."""
    for ex in process.exchanges:
        if not ex.is_input or not ex.flow:
            continue
        if "electricity" not in ex.flow.name.lower():
            continue
        if description.lower() in (ex.description or "").lower():
            return ex
    return None


def apply_value(ex: o.Exchange, mean_kwh: float, std_kwh: float):
    """Write amount and normal uncertainty onto an exchange (units: kWh)."""
    ex.amount = mean_kwh
    ex.uncertainty = o.Uncertainty(
        distribution_type=o.UncertaintyType.NORMAL_DISTRIBUTION,
        mean=mean_kwh,
        sd=std_kwh,
    )


def update_all(process: o.Process) -> dict:
    results = {"updated": [], "not_found": []}

    print(f"{'Component':<14} {'Old (kWh)':>12} {'New (kWh)':>12}  Status")
    print("-" * 56)

    for desc, (mean, std) in ENERGY_VALUES.items():
        ex = find_exchange(process, desc)
        if ex is None:
            print(f"  {desc:<14} {'—':>12} {mean:>12.6f}  NOT FOUND")
            results["not_found"].append(desc)
        else:
            old = ex.amount
            apply_value(ex, mean, std)
            cv = std / mean * 100 if mean > 0 else 0
            print(f"  {desc:<14} {old:>12.6f} {mean:>12.6f}  OK  (CV={cv:.1f}%)")
            results["updated"].append(desc)

    return results


def run_calculation(client: Client) -> float | None:
    """Run LCIA and return total kg CO2eq (or None on failure)."""
    if PRODUCT_SYSTEM_ID == "PLACEHOLDER" or LCIA_METHOD_ID == "PLACEHOLDER":
        print("\nSkipping calculation — fill in PRODUCT_SYSTEM_ID and LCIA_METHOD_ID first.")
        return None

    print("\nRunning LCIA calculation ...")
    try:
        setup = o.CalculationSetup(
            target=o.Ref(ref_type=o.RefType.ProductSystem, id=PRODUCT_SYSTEM_ID),
            impact_method=o.Ref(ref_type=o.RefType.ImpactMethod, id=LCIA_METHOD_ID),
            amount=1.0,
        )
        result = client.calculate(setup)
        impacts = result.get_total_impacts()

        # Find the climate-change / GWP category
        for impact in impacts:
            name = (impact.impact_category.name or "").lower()
            if "climate" in name or "gwp" in name or "co2" in name:
                print(f"  Total impact ({impact.impact_category.name}): "
                      f"{impact.amount:.4f} {impact.impact_category.ref_unit}")
                result.dispose()
                return impact.amount

        print("  Could not find a GWP/climate-change impact category in results.")
        print("  Available categories:")
        for impact in impacts:
            print(f"    - {impact.impact_category.name}")
        result.dispose()
        return None

    except Exception as e:
        print(f"  Calculation failed: {e}")
        return None


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 60)
    print("  update_static.py — OpenLCA Energy Update")
    print("=" * 60 + "\n")

    client = connect(SERVER_URL)
    if not client:
        return

    process = get_process(client, PROCESS_ID)
    if not process:
        return

    print()
    results = update_all(process)

    print(f"\nSaving to server ...")
    try:
        client.put(process)
        print("  Saved.\n")
    except Exception as e:
        print(f"  Save failed: {e}")
        return

    print(f"Summary: {len(results['updated'])} updated, "
          f"{len(results['not_found'])} not found")
    if results["not_found"]:
        print("  Not found (check description strings):")
        for d in results["not_found"]:
            print(f"    - {d}")

    run_calculation(client)

    print("\nDone. Refresh OpenLCA navigation to see changes.")


if __name__ == "__main__":
    main()
