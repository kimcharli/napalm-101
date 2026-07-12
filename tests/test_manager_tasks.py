from unittest.mock import MagicMock, patch
import pytest

from napalm_101.core.exceptions import ConnectionError, TaskExecutionError
from napalm_101.core.inventory import Host
from napalm_101.core.manager import DeviceConnection, device_session
from napalm_101.tasks.base import TaskRunner
from napalm_101.tasks.getters import GettersTask
from napalm_101.tasks.configs import ConfigTask
from napalm_101.tasks.audits import StateAuditTask


@pytest.fixture
def sample_host():
    return Host(
        name="test-device",
        hostname="10.0.0.1",
        driver="eos",
        username="admin",
        password="password",
        port=443,
        optional_args={"ssl_verify": False},
    )


@patch("napalm_101.core.manager.get_network_driver")
def test_device_connection_lifecycle(mock_get_driver, sample_host):
    # Mock the driver function and driver class instance
    mock_driver_instance = MagicMock()
    mock_get_driver.return_value = MagicMock(return_value=mock_driver_instance)

    # Instantiate connection
    conn = DeviceConnection(sample_host)
    conn.connect()

    # Assert get_network_driver was called with the driver name
    mock_get_driver.assert_called_once_with("eos")
    # Assert driver instantiation received correct arguments
    mock_get_driver.return_value.assert_called_once_with(
        hostname="10.0.0.1",
        username="admin",
        password="password",
        optional_args={"ssl_verify": False, "port": 443},
    )
    # Assert device.open() was called
    mock_driver_instance.open.assert_called_once()

    conn.disconnect()
    # Assert device.close() was called
    mock_driver_instance.close.assert_called_once()


@patch("napalm_101.core.manager.get_network_driver")
def test_device_connection_failure(mock_get_driver, sample_host):
    from napalm.base.exceptions import ConnectionException

    # Simulate a connection exception
    mock_driver_instance = MagicMock()
    mock_driver_instance.open.side_effect = ConnectionException("Unable to connect to port 443")
    mock_get_driver.return_value = MagicMock(return_value=mock_driver_instance)

    conn = DeviceConnection(sample_host)
    with pytest.raises(ConnectionError) as excinfo:
        conn.connect()
    assert "Connection failed to test-device" in str(excinfo.value)


@patch("napalm_101.core.manager.get_network_driver")
def test_device_session_context_manager(mock_get_driver, sample_host):
    mock_driver_instance = MagicMock()
    mock_get_driver.return_value = MagicMock(return_value=mock_driver_instance)

    with device_session(sample_host) as device:
        assert device == mock_driver_instance
        mock_driver_instance.open.assert_called_once()
        mock_driver_instance.close.assert_not_called()

    mock_driver_instance.close.assert_called_once()


def test_getters_task_success():
    mock_device = MagicMock()
    mock_device.get_facts.return_value = {"hostname": "mocked-switch", "vendor": "Arista"}
    mock_device.get_interfaces_ip.return_value = {"Management1": {"ipv4": {"10.0.0.1": {"prefix_length": 24}}}}

    task = GettersTask()
    
    # 1. Test single getter as string
    res_single = task.run(mock_device, getters="get_facts")
    assert res_single == {"hostname": "mocked-switch", "vendor": "Arista"}

    # 2. Test multiple getters as list (should standardize name to get_...)
    res_multi = task.run(mock_device, getters=["facts", "get_interfaces_ip"])
    assert "get_facts" in res_multi
    assert "get_interfaces_ip" in res_multi
    assert res_multi["get_facts"]["hostname"] == "mocked-switch"


def test_getters_task_unsupported_getter():
    mock_device = MagicMock(spec=[])  # Device with zero attributes/methods
    task = GettersTask()

    with pytest.raises(TaskExecutionError) as excinfo:
        task.run(mock_device, getters="get_facts")
    assert "does not support getter" in str(excinfo.value)


def test_config_task_dry_run_success():
    mock_device = MagicMock()
    mock_device.compare_config.return_value = "+interface Ethernet1\n+ description Conf"

    task = ConfigTask()
    res = task.run(
        mock_device,
        config_str="interface Ethernet1\n description Conf",
        method="merge",
        dry_run=True,
    )

    # In dry-run, we should load, compare, discard, but NOT commit
    mock_device.load_merge_candidate.assert_called_once_with(
        config="interface Ethernet1\n description Conf"
    )
    mock_device.compare_config.assert_called_once()
    mock_device.discard_config.assert_called_once()
    mock_device.commit_config.assert_not_called()

    assert res["diff"] == "+interface Ethernet1\n+ description Conf"
    assert res["committed"] is False


def test_config_task_commit_success():
    mock_device = MagicMock()
    mock_device.compare_config.return_value = "+interface Ethernet1\n+ description Conf"

    task = ConfigTask()
    res = task.run(
        mock_device,
        config_str="interface Ethernet1\n description Conf",
        method="merge",
        dry_run=False,
        commit_comment="My change",
    )

    # In commit run with non-empty diff, we should commit
    mock_device.load_merge_candidate.assert_called_once()
    mock_device.compare_config.assert_called_once()
    mock_device.commit_config.assert_called_once_with(message="My change")
    mock_device.discard_config.assert_not_called()

    assert res["committed"] is True


def test_state_audit_task_success():
    mock_device = MagicMock()
    mock_device.get_interfaces.return_value = {"ge-0/0/0": {"is_up": True}}
    mock_device.get_interfaces_ip.return_value = {"ge-0/0/0": {"ipv4": {"10.0.0.1": {}}}}
    mock_device.get_bgp_neighbors.return_value = {"global": {"peers": {}}}
    mock_device.get_mac_address_table.return_value = [{"mac": "00:11:22:33:44:55"}]
    mock_device.get_arp_table.return_value = [{"ip": "10.0.0.1"}]
    mock_device.get_route_to.return_value = {"8.8.8.8": [{"protocol": "bgp"}]}

    task = StateAuditTask()
    res = task.run(mock_device, route_destination="8.8.8.8")

    assert "interfaces" in res
    assert "interfaces_ip" in res
    assert "bgp_neighbors" in res
    assert "mac_address_table" in res
    assert "arp_table" in res
    assert "route_lookup" in res

    assert res["interfaces"] == {"ge-0/0/0": {"is_up": True}}
    assert res["route_lookup"]["destination"] == "8.8.8.8"
    assert res["route_lookup"]["result"] == {"8.8.8.8": [{"protocol": "bgp"}]}


def test_state_audit_task_evpn_junos():
    mock_device = MagicMock()
    mock_device.__class__.__name__ = "JunOSDriver"
    mock_device.platform = "junos"
    
    mock_pyez = mock_device.device
    # Mock real-world nested Junos JSON rpc structures
    mock_pyez.rpc.get_evpn_database_information.return_value = {
        "evpn-database-information": [{"instance-name": "evpn-1"}]
    }
    mock_pyez.rpc.get_evpn_instance_information.return_value = {
        "evpn-instance-information": [{"instance-name": "evpn-1"}]
    }

    task = StateAuditTask()
    res = task.run(mock_device, getters=["evpn"])

    mock_pyez.rpc.get_evpn_database_information.assert_called_once_with({"format": "json"})
    mock_pyez.rpc.get_evpn_instance_information.assert_called_once_with({"format": "json"})

    assert "evpn" in res
    # Verify that the nested keys are successfully flattened!
    assert res["evpn"]["evpn-database-information"] == [{"instance-name": "evpn-1"}]
    assert res["evpn"]["evpn-instance-information"] == [{"instance-name": "evpn-1"}]


