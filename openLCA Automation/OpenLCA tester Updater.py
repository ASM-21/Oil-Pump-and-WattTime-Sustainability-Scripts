"""
openLCA Batch Energy Update - Multiple Exchanges
Updates all electricity inputs in a process based on description matching
"""

import os

from olca_ipc import Client
import olca_schema as o
from typing import Dict, Tuple


# ============================================================================
# CONFIGURATION
# ============================================================================

OPENLCA_PORT = 8081
PROCESS_ID = os.getenv("OPENLCA_PROCESS_ID", "PLACEHOLDER")  # UUID is more reliable than name

# Define component energy data (mean_kWh, std_kWh)
printed_parts = {
    'DriveGear': (42.1, 0.080957), # 'DriveGear': (0.224604, 0.080957),
    'DriveShaft': (0.092925, 0.000015),
    'IdleGear': (0.219209, 0.006082),
    'IdleShaft': (0.058885, 0.004750)
}

body_programs = {
    'Body_P1': (0.343995, 0.088048),
    'Body_P2': (0.084313, 0.084543),
    'Body_P3': (0.005297, 0.001486),
    'Body_P4': (0.065401, 0.061080)
}

lid_programs = {
    'Lid_P1': (0.127831, 0.003187),
    'Lid_P2': (0.173929, 0.013351)
}

# Mapping description text in openLCA
DESCRIPTION_MAPPING = {
    # Printed parts
    'DriveGear': 'Drive Gear Electri',
    'DriveShaft': 'Drive Shaft Elec',
    'IdleGear': 'Idle Gear Electri',
    'IdleShaft': 'Idle Shaft Elec',

    # Body programs
    'Body_P1': 'Body Program 1',
    'Body_P2': 'Body Program 2',
    'Body_P3': 'Body Program 3',
    'Body_P4': 'Body Program 4',

    # Lid programs
    'Lid_P1': 'Lid Program 1',
    'Lid_P2': 'Lid Program 2'
}


# ============================================================================
# FUNCTIONS
# ============================================================================

def find_exchange_by_description(process: o.Process, description_text: str) -> o.Exchange:
    """Find an exchange by matching description field."""
    for exchange in process.exchanges:
        if not exchange.flow or not exchange.is_input:
            continue

        # Check if description contains the search text
        exch_desc = exchange.description or ""
        if description_text.lower() in exch_desc.lower():
            return exchange

    return None


def update_exchange(exchange: o.Exchange, mean_kwh: float, std_kwh: float, name: str):
    """Update exchange value and uncertainty."""
    mean_mj = mean_kwh * 1
    std_mj = std_kwh * 1

    old_value = exchange.amount
    exchange.amount = mean_mj

    # Add normal uncertainty
    exchange.uncertainty = o.Uncertainty(
        distribution_type=o.UncertaintyType.NORMAL_DISTRIBUTION,
        mean=mean_mj,
        sd=std_mj
    )

    cv = (std_kwh / mean_kwh * 100) if mean_kwh > 0 else 0

    print(f"  ✓ {name}")
    print(f"    Old: {old_value:.6f} MJ ({old_value/3.6:.6f} kWh)")
    print(f"    New: {mean_mj:.6f} MJ ({mean_kwh:.6f} kWh)")
    print(f"    Uncertainty: μ={mean_kwh:.6f}, σ={std_kwh:.6f} kWh (CV={cv:.2f}%)")


def batch_update_all(client: Client, process: o.Process):
    """Update all energy exchanges in the process."""

    # Combine all energy data
    all_energy_data = {
        **printed_parts,
        **body_programs,
        **lid_programs
    }

    results = {
        'updated': [],
        'not_found': [],
        'errors': []
    }

    print("\n" + "="*80)
    print("UPDATING EXCHANGES")
    print("="*80)

    for key, (mean_kwh, std_kwh) in all_energy_data.items():
        description_search = DESCRIPTION_MAPPING.get(key)

        if not description_search:
            print(f"  ⚠️  {key}: No description mapping defined")
            results['not_found'].append(key)
            continue

        try:
            exchange = find_exchange_by_description(process, description_search)

            if exchange:
                update_exchange(exchange, mean_kwh, std_kwh, key)
                results['updated'].append(key)
            else:
                print(f"  ❌ {key}: Exchange not found (searched for '{description_search}')")
                results['not_found'].append(key)

        except Exception as e:
            print(f"  ❌ {key}: Error - {e}")
            results['errors'].append((key, str(e)))

    return results


def list_all_exchanges(process: o.Process):
    """List all exchanges to help with debugging."""
    print("\n" + "="*80)
    print(f"ALL ELECTRICITY EXCHANGES IN '{process.name}'")
    print("="*80)

    electricity_count = 0
    for i, exchange in enumerate(process.exchanges):
        if not exchange.flow or not exchange.is_input:
            continue

        if 'electricity' in exchange.flow.name.lower():
            electricity_count += 1
            desc = exchange.description or "(no description)"
            print(f"\n{electricity_count}. Flow: {exchange.flow.name}")
            print(f"   Amount: {exchange.amount:.6f} MJ ({exchange.amount/3.6:.6f} kWh)")
            print(f"   Description: {desc}")
            if exchange.uncertainty:
                print(f"   Current uncertainty: {exchange.uncertainty.distribution_type}")


def main():
    print("="*80)
    print("openLCA Batch Energy Update")
    print("="*80)

    # Connect
    print(f"\n[1/5] Connecting to openLCA on port {OPENLCA_PORT}...")
    try:
        client = Client(OPENLCA_PORT)
        print("✓ Connected")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("Start IPC server: Tools > Developer tools > IPC Server")
        return

    # Get process
    print(f"\n[2/5] Locating process by UUID...")
    try:
        process = client.get(o.Process, PROCESS_ID)
        if not process:
            print(f"❌ Process not found with UUID: {PROCESS_ID}")
            return

        print(f"✓ Found: {process.name}")
        print(f"  ID: {process.id}")
    except Exception as e:
        print(f"❌ Error: {e}")
        return

    # Show current exchanges
    print(f"\n[3/5] Current exchanges:")
    list_all_exchanges(process)

    # Update exchanges
    print(f"\n[4/5] Updating energy values...")
    results = batch_update_all(client, process)

    # Save
    print(f"\n[5/5] Saving to openLCA...")
    try:
        client.put(process)
        print("✓ Process updated successfully")
    except Exception as e:
        print(f"❌ Save failed: {e}")
        return

    # Summary
    print("\n" + "="*80)
    print("UPDATE SUMMARY")
    print("="*80)
    print(f"✓ Successfully updated: {len(results['updated'])}")
    print(f"❌ Not found: {len(results['not_found'])}")
    print(f"⚠️  Errors: {len(results['errors'])}")

    if results['updated']:
        print("\nUpdated exchanges:")
        for key in results['updated']:
            print(f"  ✓ {key}")

    if results['not_found']:
        print("\nNot found (check DESCRIPTION_MAPPING):")
        for key in results['not_found']:
            print(f"  ❌ {key}")

    if results['errors']:
        print("\nErrors:")
        for key, error in results['errors']:
            print(f"  ⚠️  {key}: {error}")

    print("\n" + "="*80)
    print("Refresh openLCA navigation to see changes")
    print("="*80)


if __name__ == "__main__":
    main()
