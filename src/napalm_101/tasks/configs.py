from pathlib import Path
from typing import Any, Dict, Optional
from napalm_101.tasks.base import BaseTask
from napalm_101.core.exceptions import TaskExecutionError


class ConfigTask(BaseTask):
    """Task to load, compare, commit, or discard configuration changes on a device."""

    @property
    def name(self) -> str:
        return "ConfigTask"

    def run(self, device: Any, **kwargs) -> Dict[str, Any]:
        """Loads configuration onto the device.
        
        Args:
            device: The connected NAPALM device.
            config_str: Configuration content as a string.
            config_file: Path to a file containing configuration.
            method: "merge" or "replace" (default "merge").
            dry_run: If True, returns the diff and discards changes without committing (default True).
            commit_comment: Optional description for the commit (supported on some platforms).
        """
        config_str: Optional[str] = kwargs.get("config_str")
        config_file: Optional[str] = kwargs.get("config_file")
        method: str = kwargs.get("method", "merge").lower()
        dry_run: bool = kwargs.get("dry_run", True)
        commit_comment: str = kwargs.get("commit_comment", "Configured via napalm-101")

        if not config_str and not config_file:
            raise TaskExecutionError("Must provide either 'config_str' or 'config_file'.")

        if method not in ("merge", "replace"):
            raise TaskExecutionError(
                f"Invalid config load method '{method}'. Must be 'merge' or 'replace'."
            )

        # Resolve configuration content
        content = ""
        if config_file:
            file_path = Path(config_file)
            if not file_path.exists():
                raise TaskExecutionError(f"Configuration file not found: {config_file}")
            try:
                content = file_path.read_text()
            except Exception as e:
                raise TaskExecutionError(f"Error reading configuration file {config_file}: {e}")
        else:
            content = config_str or ""

        try:
            # 1. Load candidate config
            if method == "merge":
                device.load_merge_candidate(config=content)
            else:
                device.load_replace_candidate(config=content)

            # 2. Compare candidate with running config
            diff = device.compare_config()

            # 3. Commit or discard
            committed = False
            if dry_run:
                device.discard_config()
            else:
                if diff:
                    device.commit_config(message=commit_comment)
                    committed = True
                else:
                    device.discard_config()

            return {
                "method": method,
                "dry_run": dry_run,
                "diff": diff,
                "committed": committed,
            }

        except Exception as e:
            # Ensure we discard any partial candidates if error occurs
            try:
                device.discard_config()
            except Exception:
                pass
            raise TaskExecutionError(f"Configuration change failed: {e}") from e
