from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field

from napalm_101.core.exceptions import InventoryError


class GroupSchema(BaseModel):
    """Schema representing a group of devices."""
    driver: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    port: Optional[int] = None
    optional_args: Dict[str, Any] = Field(default_factory=dict)
    vars: Dict[str, Any] = Field(default_factory=dict)


class HostSchema(BaseModel):
    """Raw schema of a host from inventory file."""
    hostname: str
    driver: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    port: Optional[int] = None
    groups: List[str] = Field(default_factory=list)
    optional_args: Dict[str, Any] = Field(default_factory=dict)
    vars: Dict[str, Any] = Field(default_factory=dict)


class Host(BaseModel):
    """Fully resolved host object with inherited values."""
    name: str
    hostname: str
    driver: str
    username: str
    password: str
    port: Optional[int] = None
    groups: List[str] = Field(default_factory=list)
    optional_args: Dict[str, Any] = Field(default_factory=dict)
    vars: Dict[str, Any] = Field(default_factory=dict)


class InventorySchema(BaseModel):
    """Full inventory file schema."""
    groups: Dict[str, GroupSchema] = Field(default_factory=dict)
    hosts: Dict[str, HostSchema] = Field(default_factory=dict)


class Inventory:
    """Class to load, parse, and query network device inventory."""

    def __init__(self, raw_data: Dict[str, Any]):
        try:
            self._schema = InventorySchema(**raw_data)
        except Exception as e:
            raise InventoryError(f"Failed to validate inventory schema: {e}")

        self.hosts: Dict[str, Host] = {}
        self._resolve_inventory()

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Inventory":
        """Load inventory from a YAML file."""
        file_path = Path(path)
        if not file_path.exists():
            raise InventoryError(f"Inventory file not found: {path}")

        try:
            with open(file_path, "r") as f:
                data = yaml.safe_load(f) or {}
            return cls(data)
        except Exception as e:
            raise InventoryError(f"Error reading YAML file {path}: {e}")

    def _resolve_inventory(self):
        """Resolve host inheritance from group properties."""
        for name, raw_host in self._schema.hosts.items():
            # Defaults for inheritance
            resolved_driver = raw_host.driver
            resolved_username = raw_host.username
            resolved_password = raw_host.password
            resolved_port = raw_host.port
            
            # Merged dictionaries (host values override group values)
            resolved_optional_args = {}
            resolved_vars = {}

            # Process groups in order (later groups override earlier groups if keys conflict)
            for group_name in raw_host.groups:
                if group_name not in self._schema.groups:
                    raise InventoryError(
                        f"Host '{name}' references undefined group '{group_name}'"
                    )
                group = self._schema.groups[group_name]

                if resolved_driver is None:
                    resolved_driver = group.driver
                if resolved_username is None:
                    resolved_username = group.username
                if resolved_password is None:
                    resolved_password = group.password
                if resolved_port is None:
                    resolved_port = group.port

                # Merge dicts: group values first
                resolved_optional_args = {**group.optional_args, **resolved_optional_args}
                resolved_vars = {**group.vars, **resolved_vars}

            # Overlay host-specific values
            resolved_optional_args.update(raw_host.optional_args)
            resolved_vars.update(raw_host.vars)

            # Ensure mandatory fields are present
            missing_fields = []
            if resolved_driver is None:
                missing_fields.append("driver")
            if resolved_username is None:
                missing_fields.append("username")
            if resolved_password is None:
                missing_fields.append("password")

            if missing_fields:
                raise InventoryError(
                    f"Host '{name}' is missing mandatory configuration fields "
                    f"({', '.join(missing_fields)}) and they were not inherited from any group."
                )

            # Build fully resolved Host
            self.hosts[name] = Host(
                name=name,
                hostname=raw_host.hostname,
                driver=resolved_driver,  # type: ignore (validated not None)
                username=resolved_username,  # type: ignore (validated not None)
                password=resolved_password,  # type: ignore (validated not None)
                port=resolved_port,
                groups=raw_host.groups,
                optional_args=resolved_optional_args,
                vars=resolved_vars,
            )

    def get_host(self, name: str) -> Host:
        """Retrieve a resolved host by its name."""
        if name not in self.hosts:
            raise InventoryError(f"Host '{name}' not found in inventory.")
        return self.hosts[name]

    def list_hosts(
        self, group: Optional[str] = None, filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Host]:
        """List and filter hosts from the inventory."""
        results = list(self.hosts.values())

        if group:
            results = [h for h in results if group in h.groups]

        if filter_dict:
            for key, val in filter_dict.items():
                # Supports filtering on Host attributes and vars dict
                results = [
                    h
                    for h in results
                    if getattr(h, key, None) == val or h.vars.get(key) == val
                ]

        return results
