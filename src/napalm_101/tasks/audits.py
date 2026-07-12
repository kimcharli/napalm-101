from typing import Any, Dict, List, Optional
from napalm_101.tasks.base import BaseTask
from napalm_101.core.exceptions import TaskExecutionError


class StateAuditTask(BaseTask):
    """Task to safely gather comprehensive network operational states from a device."""

    @property
    def name(self) -> str:
        return "StateAuditTask"

    def run(self, device: Any, **kwargs) -> Dict[str, Any]:
        """Safely executes multiple getters to capture BGP, interfaces, routes, MAC, and ARP.
        
        Args:
            device: The connected NAPALM device.
            route_destination: Optional IP/prefix to query routing table for (default '8.8.8.8').
        """
        route_destination = kwargs.get("route_destination", "8.8.8.8")
        
        # Getters to run that take no parameters
        standard_getters = {
            "interfaces": "get_interfaces",
            "interfaces_ip": "get_interfaces_ip",
            "bgp_neighbors": "get_bgp_neighbors",
            "mac_address_table": "get_mac_address_table",
            "arp_table": "get_arp_table",
        }

        audit_results = {}

        # 1. Run standard getters with try/except to handle device incompatibilities
        for key, getter_name in standard_getters.items():
            if not hasattr(device, getter_name):
                audit_results[key] = {"error": f"Getter '{getter_name}' not supported by driver."}
                continue

            try:
                getter_fn = getattr(device, getter_name)
                audit_results[key] = getter_fn()
            except Exception as e:
                audit_results[key] = {"error": str(e)}

        # 2. Run route lookup (requires destination parameter)
        if route_destination:
            if hasattr(device, "get_route_to"):
                try:
                    audit_results["route_lookup"] = {
                        "destination": route_destination,
                        "result": device.get_route_to(destination=route_destination),
                    }
                except Exception as e:
                    audit_results["route_lookup"] = {
                        "destination": route_destination,
                        "error": str(e),
                    }
            else:
                audit_results["route_lookup"] = {"error": "get_route_to not supported by driver."}

        return audit_results
