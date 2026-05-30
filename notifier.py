"""Cross-platform desktop notifications.

Linux:  notify-send (primary, works in VMs) → plyer fallback
Windows: winotify (toast) → plyer fallback
"""

import sys
import subprocess
import logging

logger = logging.getLogger(__name__)


def send_notification(title: str, message: str) -> None:
    if sys.platform == "win32":
        _notify_windows(title, message)
    else:
        _notify_linux(title, message)


def _notify_linux(title: str, message: str) -> None:
    # Primary: notify-send — reliable in VMs and all desktop environments
    try:
        subprocess.run(
            ["notify-send", "--app-name=Watt", "--icon=battery",
             "--urgency=normal", title, message],
            timeout=5, check=False,
        )
        return
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"notify-send failed: {e}")

    # Fallback: plyer
    try:
        from plyer import notification  # type: ignore
        notification.notify(title=title, message=message, app_name="Watt", timeout=5)
    except Exception as e:
        logger.debug(f"plyer notification failed: {e}")


def _notify_windows(title: str, message: str) -> None:
    # Primary: winotify (Windows 10/11 toast)
    try:
        from winotify import Notification  # type: ignore
        toast = Notification(app_id="Watt Battery Monitor", title=title, msg=message)
        toast.show()
        return
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"winotify failed: {e}")

    # Fallback: plyer
    try:
        from plyer import notification  # type: ignore
        notification.notify(title=title, message=message, app_name="Watt", timeout=5)
    except Exception as e:
        logger.debug(f"plyer notification failed: {e}")
