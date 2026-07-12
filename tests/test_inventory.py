import pytest
from pathlib import Path
from napalm_101.core.exceptions import InventoryError
from napalm_101.core.inventory import Inventory


def test_inventory_loading_and_inheritance(tmp_path: Path):
    # Create a temporary inventory file
    yaml_content = """
    groups:
      ios_group:
        driver: ios
        username: group_admin
        password: group_password
        port: 22
        optional_args:
          global_delay_factor: 2
        vars:
          domain: example.com
      eos_group:
        driver: eos
        username: group_eos
        password: eos_password
        optional_args:
          use_ssl: true
          
    hosts:
      host-ios:
        hostname: 10.0.0.1
        groups: [ios_group]
        vars:
          role: leaf
      host-eos:
        hostname: 10.0.0.2
        groups: [eos_group]
        password: host_override_password
        optional_args:
          ssl_verify: false
      host-no-group:
        hostname: 10.0.0.3
        driver: nxos
        username: direct_user
        password: direct_password
    """
    
    inv_file = tmp_path / "test_inventory.yaml"
    inv_file.write_text(yaml_content)

    inventory = Inventory.from_yaml(inv_file)

    # 1. Test host-ios inherits properly from ios_group
    host_ios = inventory.get_host("host-ios")
    assert host_ios.hostname == "10.0.0.1"
    assert host_ios.driver == "ios"
    assert host_ios.username == "group_admin"
    assert host_ios.password == "group_password"
    assert host_ios.port == 22
    assert host_ios.optional_args == {"global_delay_factor": 2}
    assert host_ios.vars == {"domain": "example.com", "role": "leaf"}

    # 2. Test host-eos has group inheritance + host-level overrides
    host_eos = inventory.get_host("host-eos")
    assert host_eos.hostname == "10.0.0.2"
    assert host_eos.driver == "eos"
    assert host_eos.username == "group_eos"
    assert host_eos.password == "host_override_password"  # overridden!
    assert host_eos.optional_args == {"use_ssl": True, "ssl_verify": False}  # merged!

    # 3. Test host with no group
    host_ng = inventory.get_host("host-no-group")
    assert host_ng.hostname == "10.0.0.3"
    assert host_ng.driver == "nxos"
    assert host_ng.username == "direct_user"


def test_inventory_missing_required_fields(tmp_path: Path):
    # Host missing driver and not inherited from group
    yaml_content = """
    groups:
      my_group:
        username: admin
        password: pass
    hosts:
      host-bad:
        hostname: 10.0.0.1
        groups: [my_group]
    """
    inv_file = tmp_path / "bad_inventory.yaml"
    inv_file.write_text(yaml_content)

    with pytest.raises(InventoryError) as excinfo:
        Inventory.from_yaml(inv_file)
    assert "missing mandatory configuration fields" in str(excinfo.value)
    assert "driver" in str(excinfo.value)


def test_inventory_undefined_group(tmp_path: Path):
    yaml_content = """
    hosts:
      host-bad:
        hostname: 10.0.0.1
        groups: [nonexistent_group]
    """
    inv_file = tmp_path / "bad_inventory.yaml"
    inv_file.write_text(yaml_content)

    with pytest.raises(InventoryError) as excinfo:
        Inventory.from_yaml(inv_file)
    assert "references undefined group" in str(excinfo.value)


def test_inventory_list_and_filter(tmp_path: Path):
    yaml_content = """
    groups:
      group_a:
        driver: ios
        username: user
        password: pass
        vars:
          env: production
      group_b:
        driver: eos
        username: user
        password: pass
        vars:
          env: staging
    hosts:
      sw1:
        hostname: 10.1.1.1
        groups: [group_a]
      sw2:
        hostname: 10.1.1.2
        groups: [group_b]
      sw3:
        hostname: 10.1.1.3
        groups: [group_a]
        vars:
          env: staging  # host overrides group-level var
    """
    inv_file = tmp_path / "filter_inventory.yaml"
    inv_file.write_text(yaml_content)

    inventory = Inventory.from_yaml(inv_file)

    # Filter by group_a
    hosts_a = inventory.list_hosts(group="group_a")
    assert len(hosts_a) == 2
    assert {h.name for h in hosts_a} == {"sw1", "sw3"}

    # Filter by variable env=staging
    hosts_staging = inventory.list_hosts(filter_dict={"env": "staging"})
    assert len(hosts_staging) == 2
    assert {h.name for h in hosts_staging} == {"sw2", "sw3"}

    # Filter by driver=ios
    hosts_ios = inventory.list_hosts(filter_dict={"driver": "ios"})
    assert len(hosts_ios) == 2
    assert {h.name for h in hosts_ios} == {"sw1", "sw3"}
