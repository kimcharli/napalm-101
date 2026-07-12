from typing import Any, Dict, List, Optional
from napalm_101.tasks.base import BaseTask
from napalm_101.core.exceptions import TaskExecutionError


class StateAuditTask(BaseTask):
    """Task to safely gather comprehensive network operational states from a device dynamically."""

    @property
    def name(self) -> str:
        return "StateAuditTask"

    def _get_junos_evpn_data(self, device: Any) -> Dict[str, Any]:
        """Custom helper to safely extract EVPN database and instance information from Junos over NETCONF/CLI."""
        evpn_data = {}
        try:
            pyez_dev = device.device  # Get underlying PyEZ device

            # 1. Fetch EVPN Database (Try JSON encoding first, fall back to CLI)
            try:
                db_resp = pyez_dev.rpc.get_evpn_database_information({"format": "json"})
                if isinstance(db_resp, dict) and "evpn-database-information" in db_resp:
                    evpn_data["evpn-database-information"] = db_resp["evpn-database-information"]
                else:
                    evpn_data["evpn-database-information"] = db_resp
            except Exception:
                try:
                    evpn_data["evpn-database-information"] = device.cli(["show evpn database"])["show evpn database"]
                except Exception as e:
                    evpn_data["evpn-database-information"] = {"error": f"Failed to retrieve EVPN database: {e}"}

            # 2. Fetch EVPN Instance (Try JSON encoding first, fall back to CLI)
            try:
                inst_resp = pyez_dev.rpc.get_evpn_instance_information({"format": "json"})
                if isinstance(inst_resp, dict) and "evpn-instance-information" in inst_resp:
                    evpn_data["evpn-instance-information"] = inst_resp["evpn-instance-information"]
                else:
                    evpn_data["evpn-instance-information"] = inst_resp
            except Exception:
                try:
                    evpn_data["evpn-instance-information"] = device.cli(["show evpn instance"])["show evpn instance"]
                except Exception as e:
                    evpn_data["evpn-instance-information"] = {"error": f"Failed to retrieve EVPN instances: {e}"}

            return evpn_data
        except Exception as e:
            return {"error": f"Junos EVPN Netconf RPC failed: {e}"}

    def run(self, device: Any, **kwargs) -> Dict[str, Any]:
        """Safely executes multiple getters to capture network states dynamically.
        
        Args:
            device: The connected NAPALM device.
            getters: List of getters to execute (e.g., ['interfaces', 'bgp_neighbors', 'evpn']).
            route_destination: Optional IP/prefix to query routing table for.
        """
        route_destination = kwargs.get("route_destination")
        
        # Load getters from arguments or fallback to default
        getters_list = kwargs.get("getters")
        if not getters_list:
            getters_list = [
                "interfaces",
                "interfaces_ip",
                "bgp_neighbors",
                "mac_address_table",
                "arp_table",
            ]

        audit_results = {}

        # 1. Run getters with try/except to handle device incompatibilities
        for getter in getters_list:
            clean_key = getter.replace("get_", "")
            
            # Handle custom EVPN getter
            if clean_key == "evpn":
                is_junos = "junos" in device.__class__.__name__.lower() or (
                    hasattr(device, "platform") and device.platform == "junos"
                )
                if is_junos:
                    audit_results["evpn"] = self._get_junos_evpn_data(device)
                else:
                    audit_results["evpn"] = {"error": "EVPN auditing is only supported on Junos driver devices."}
                continue

            # Handle standard getters
            getter_name = getter if getter.startswith("get_") else f"get_{getter}"

            if not hasattr(device, getter_name):
                audit_results[clean_key] = {"error": f"Getter '{getter_name}' not supported by driver."}
                continue

            try:
                getter_fn = getattr(device, getter_name)
                audit_results[clean_key] = getter_fn()
            except Exception as e:
                audit_results[clean_key] = {"error": str(e)}

        # 2. Run route lookup if a target is requested (requires destination parameter)
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
