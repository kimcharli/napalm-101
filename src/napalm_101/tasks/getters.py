from typing import Any, Dict, List, Union
from napalm_101.tasks.base import BaseTask
from napalm_101.core.exceptions import TaskExecutionError


class GettersTask(BaseTask):
    """Task to dynamically retrieve state data (getters) from a device."""

    @property
    def name(self) -> str:
        return "GettersTask"

    def run(self, device: Any, **kwargs) -> Dict[str, Any]:
        """Runs one or more getters on the device.
        
        Args:
            device: The NAPALM device.
            getters: A string (single getter) or list of strings representing the getters 
                     to run. Defaults to "get_facts".
                     Examples: "get_facts", ["get_facts", "get_interfaces_ip"]
        """
        getters_arg = kwargs.get("getters", "get_facts")
        
        if isinstance(getters_arg, str):
            getters = [getters_arg]
        elif isinstance(getters_arg, list):
            getters = getters_arg
        else:
            raise TaskExecutionError(
                f"Invalid 'getters' argument type: {type(getters_arg)}. Expected str or list."
            )

        results = {}
        for getter in getters:
            # Standardize names (e.g. if someone passes 'facts' instead of 'get_facts')
            clean_getter = getter if getter.startswith("get_") else f"get_{getter}"

            if not hasattr(device, clean_getter):
                raise TaskExecutionError(
                    f"Device driver '{device.__class__.__name__}' does not support getter '{clean_getter}'"
                )

            try:
                getter_fn = getattr(device, clean_getter)
                results[clean_getter] = getter_fn()
            except Exception as e:
                # We can either raise or capture the error for this specific getter
                results[clean_getter] = {"error": f"Failed to retrieve: {e}"}

        # If only one getter was requested and it's a string argument, simplify the output structure
        if isinstance(getters_arg, str) and len(results) == 1:
            return list(results.values())[0]

        return results
