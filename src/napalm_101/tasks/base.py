import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from napalm_101.core.inventory import Host
from napalm_101.core.manager import device_session


class TaskResult(BaseModel):
    """Result of running a task against a single host."""
    host: str
    task_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    elapsed_seconds: float = 0.0


class BaseTask(ABC):
    """Abstract base class for all automation tasks."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the task."""
        pass

    @abstractmethod
    def run(self, device: Any, **kwargs) -> Any:
        """The core logic of the task.
        
        Args:
            device: The connected NAPALM device object.
            **kwargs: Dynamic arguments passed to the task.
        """
        pass

    def execute(self, host: Host, **kwargs) -> TaskResult:
        """Executes the task against a host. Handles connection and errors."""
        start_time = time.time()
        try:
            with device_session(host) as device:
                data = self.run(device, **kwargs)
                elapsed = time.time() - start_time
                return TaskResult(
                    host=host.name,
                    task_name=self.name,
                    success=True,
                    data=data,
                    elapsed_seconds=round(elapsed, 3),
                )
        except Exception as e:
            elapsed = time.time() - start_time
            return TaskResult(
                host=host.name,
                task_name=self.name,
                success=False,
                error=str(e),
                elapsed_seconds=round(elapsed, 3),
            )


class TaskRunner:
    """Executes tasks against multiple hosts, supporting sequential or parallel execution."""

    def __init__(self, inventory_path: str):
        from napalm_101.core.inventory import Inventory
        self.inventory = Inventory.from_yaml(inventory_path)

    def run_on_hosts(
        self,
        hosts: List[Host],
        task: BaseTask,
        parallel: bool = True,
        max_workers: int = 10,
        **task_kwargs,
    ) -> Dict[str, TaskResult]:
        """Run a task on a list of hosts."""
        results: Dict[str, TaskResult] = {}

        if not hosts:
            return results

        if parallel and len(hosts) > 1:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(hosts))) as executor:
                # Submit all tasks
                future_to_host = {
                    executor.submit(task.execute, host, **task_kwargs): host
                    for host in hosts
                }
                for future in as_completed(future_to_host):
                    host = future_to_host[future]
                    try:
                        results[host.name] = future.result()
                    except Exception as e:
                        results[host.name] = TaskResult(
                            host=host.name,
                            task_name=task.name,
                            success=False,
                            error=f"Uncaught thread exception: {e}",
                        )
        else:
            # Sequential execution
            for host in hosts:
                results[host.name] = task.execute(host, **task_kwargs)

        return results

    def run_on_group(
        self,
        group_name: str,
        task: BaseTask,
        parallel: bool = True,
        max_workers: int = 10,
        **task_kwargs,
    ) -> Dict[str, TaskResult]:
        """Run a task on all hosts belonging to a specific group."""
        hosts = self.inventory.list_hosts(group=group_name)
        return self.run_on_hosts(
            hosts, task, parallel=parallel, max_workers=max_workers, **task_kwargs
        )
