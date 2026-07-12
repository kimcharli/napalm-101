from typing import Generator, Any
from contextlib import contextmanager
from napalm import get_network_driver
from napalm.base.exceptions import ConnectionException, NapalmException

from napalm_101.core.exceptions import ConnectionError
from napalm_101.core.inventory import Host


class DeviceConnection:
    """Manages the connection lifecycle to a network device using NAPALM."""

    def __init__(self, host: Host):
        self.host = host
        self.device = None

    def connect(self):
        """Open connection to the network device."""
        try:
            # Get the correct driver for the host
            driver_fn = get_network_driver(self.host.driver)
            
            # Map parameters. Port is optional in NAPALM. To maintain cross-vendor compatibility,
            # we inject the port into optional_args. Most drivers (like Junos, Cisco IOS, NX-OS)
            # expect port in optional_args, whereas some drivers may accept it at the top level.
            opt_args = dict(self.host.optional_args)
            if self.host.port is not None:
                opt_args["port"] = self.host.port

            conn_args = {
                "hostname": self.host.hostname,
                "username": self.host.username,
                "password": self.host.password,
                "optional_args": opt_args,
            }

            # Initialize device object
            self.device = driver_fn(**conn_args)
            self.device.open()
        except ConnectionException as ce:
            raise ConnectionError(
                f"Connection failed to {self.host.name} ({self.host.hostname}): {ce}"
            ) from ce
        except Exception as e:
            raise ConnectionError(
                f"Unexpected error when connecting to {self.host.name}: {e}"
            ) from e

    def disconnect(self):
        """Close connection to the network device."""
        if self.device is not None:
            try:
                self.device.close()
            except Exception:
                pass  # Ignore exceptions during close
            finally:
                self.device = None


@contextmanager
def device_session(host: Host) -> Generator[Any, None, None]:
    """Context manager for managing device connections cleanly.
    
    Usage:
        with device_session(host) as device:
            facts = device.get_facts()
    """
    connection = DeviceConnection(host)
    connection.connect()
    try:
        yield connection.device
    finally:
        connection.disconnect()
