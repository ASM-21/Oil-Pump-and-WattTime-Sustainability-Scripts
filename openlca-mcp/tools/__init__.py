"""Tool registry. Importing from here keeps mcp_server.py clean."""

from tools.health import ping_server
from tools.systems import list_product_systems, get_product_system
from tools.lcia import (
    list_impact_methods,
    calculate_product_system,
    get_impact_contributions,
    get_grouped_impact_results,
)
from tools.inventory import list_processes, get_process_info, get_total_flows

ALL_TOOLS = (
    ping_server,
    list_product_systems,
    get_product_system,
    list_impact_methods,
    calculate_product_system,
    get_impact_contributions,
    get_grouped_impact_results,
    list_processes,
    get_process_info,
    get_total_flows,
)
