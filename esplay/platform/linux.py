"""LinuxPlatform — PlatformProvider implementation for Linux.

Supports the four most common package manager families:
  - Debian/Ubuntu  → apt-get
  - Fedora/RHEL/CentOS/Rocky → dnf  (falls back to yum on older systems)
  - Arch/Manjaro   → pacman
  - openSUSE       → zypper

Distro is detected via /etc/os-release (standard on all modern Linux distros).
"""

from __future__ import annotations

import shutil
import subprocess
import webbrowser
from pathlib import Path


from esplay.platform.base import PlatformProvider


# ── Distro detection ─────────────────────────────────────────────────────────

def _read_os_release() -> dict[str, str]:
    """Parse /etc/os-release into a key→value dict."""
    release: dict[str, str] = {}
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        os_release = Path("/usr/lib/os-release")
    if not os_release.exists():
        return release
    for line in os_release.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            release[key.strip()] = value.strip().strip('"')
    return release


def _detect_distro_family() -> str:
    """Return one of: 'debian', 'fedora', 'arch', 'suse', 'unknown'."""
    info = _read_os_release()
    id_val = info.get("ID", "").lower()
    id_like = info.get("ID_LIKE", "").lower()

    combined = f"{id_val} {id_like}"

    if any(k in combined for k in ("debian", "ubuntu", "mint", "pop", "elementary", "kali", "raspbian")):
        return "debian"
    if any(k in combined for k in ("fedora", "rhel", "centos", "rocky", "alma", "ol", "amzn")):
        return "fedora"
    if any(k in combined for k in ("arch", "manjaro", "endeavour", "garuda")):
        return "arch"
    if any(k in combined for k in ("suse", "opensuse", "sles")):
        return "suse"
    return "unknown"


# ── Install recipes per distro family ────────────────────────────────────────

_INSTALL_STEPS: dict[str, list[str]] = {
    "debian": [
        "sudo apt-get update",
        "sudo apt-get install -y ca-certificates curl gnupg",
        "sudo install -m 0755 -d /etc/apt/keyrings",
        "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg",
        "sudo chmod a+r /etc/apt/keyrings/docker.gpg",
        'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] '
        'https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" '
        '| sudo tee /etc/apt/sources.list.d/docker.list > /dev/null',
        "sudo apt-get update",
        "sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin",
        "sudo systemctl enable --now docker",
        "sudo usermod -aG docker $USER   # log out and back in after this",
    ],
    "fedora": [
        "sudo dnf -y install dnf-plugins-core",
        "sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo",
        "sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin",
        "sudo systemctl enable --now docker",
        "sudo usermod -aG docker $USER   # log out and back in after this",
    ],
    "arch": [
        "sudo pacman -Sy --noconfirm docker",
        "sudo systemctl enable --now docker",
        "sudo usermod -aG docker $USER   # log out and back in after this",
    ],
    "suse": [
        "sudo zypper install -y docker",
        "sudo systemctl enable --now docker",
        "sudo usermod -aG docker $USER   # log out and back in after this",
    ],
    "unknown": [
        "Visit https://docs.docker.com/engine/install/ and follow the guide for your distro.",
    ],
}

# Auto-install commands (non-interactive, run by offer_docker_install).
_AUTO_INSTALL_CMDS: dict[str, list[list[str]]] = {
    "debian": [
        ["sudo", "apt-get", "update", "-y"],
        ["sudo", "apt-get", "install", "-y", "docker.io"],
        ["sudo", "systemctl", "enable", "--now", "docker"],
    ],
    "fedora": [
        ["sudo", "dnf", "install", "-y", "docker"],
        ["sudo", "systemctl", "enable", "--now", "docker"],
    ],
    "arch": [
        ["sudo", "pacman", "-Sy", "--noconfirm", "docker"],
        ["sudo", "systemctl", "enable", "--now", "docker"],
    ],
    "suse": [
        ["sudo", "zypper", "install", "-y", "docker"],
        ["sudo", "systemctl", "enable", "--now", "docker"],
    ],
}


class LinuxPlatform(PlatformProvider):
    """Linux PlatformProvider — works across Debian, Fedora, Arch, and openSUSE families."""

    def __init__(self) -> None:
        self._distro_family = _detect_distro_family()
        self._os_release = _read_os_release()

    def name(self) -> str:
        pretty = self._os_release.get("PRETTY_NAME", "")
        return f"Linux ({pretty})" if pretty else "Linux"

    def is_docker_installed(self) -> bool:
        return shutil.which("docker") is not None

    def install_docker_instructions(self) -> str:
        steps = _INSTALL_STEPS.get(self._distro_family, _INSTALL_STEPS["unknown"])
        lines = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(steps))
        return (
            f"Install Docker Engine on {self.name()}:\n\n"
            f"{lines}\n\n"
            "Full docs: https://docs.docker.com/engine/install/"
        )

    def offer_docker_install(self) -> bool:
        """Attempt automated Docker install using the distro's package manager.

        Returns True on success, False if the distro is unknown or install fails.
        Requires sudo access (the user will be prompted for their password).
        """
        import questionary  # noqa: PLC0415

        cmds = _AUTO_INSTALL_CMDS.get(self._distro_family)
        if not cmds:
            return False

        pkg_mgr = {"debian": "apt-get", "fedora": "dnf", "arch": "pacman", "suse": "zypper"}.get(
            self._distro_family, "package manager"
        )
        confirmed = questionary.confirm(
            f"Docker is not installed. Install it now via {pkg_mgr} (requires sudo)?",
            default=True,
        ).ask()
        if not confirmed:
            return False

        for cmd in cmds:
            result = subprocess.run(cmd, check=False)
            if result.returncode != 0:
                return False

        # Add current user to the docker group so they don't need sudo for docker.
        import os  # noqa: PLC0415
        user = os.environ.get("USER") or os.environ.get("LOGNAME", "")
        if user:
            subprocess.run(["sudo", "usermod", "-aG", "docker", user], check=False)

        return self.is_docker_installed()

    def open_url(self, url: str) -> None:
        # Try xdg-open first (works on most desktop Linux).
        if shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", url])
        else:
            webbrowser.open(url)
