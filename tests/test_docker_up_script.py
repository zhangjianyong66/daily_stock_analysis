import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "docker-up.sh"


def _write_fake_docker(bin_dir: Path, log_file: Path) -> None:
    docker = bin_dir / "docker"
    docker.write_text(
        f"""#!/usr/bin/env bash
set -Eeuo pipefail
printf 'docker %s\\n' "$*" >> {str(log_file)!r}
if [[ "${{1:-}}" == "ps" ]]; then
  exit 0
fi
if [[ "${{1:-}}" == "compose" && "${{2:-}}" == "version" ]]; then
  exit 0
fi
exit 0
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)


def _run_script(
    tmp_path: Path,
    *args: str,
    env_content: str | None = None,
) -> list[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_file = tmp_path / "docker.log"
    _write_fake_docker(bin_dir, log_file)

    env_file = tmp_path / ".env"
    if env_content is not None:
        env_file.write_text(env_content, encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["ENV_FILE"] = str(env_file)

    subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return log_file.read_text(encoding="utf-8").splitlines()


def test_default_action_builds_and_starts_server(tmp_path: Path) -> None:
    lines = _run_script(tmp_path)

    assert any(
        "compose -f " in line and "docker/docker-compose.yml" in line and "build server" in line
        for line in lines
    )
    assert any(
        "compose -f " in line and "docker/docker-compose.yml" in line and "up -d server" in line
        for line in lines
    )
    assert any(
        "compose -f " in line and "docker/docker-compose.yml" in line and line.endswith(" ps")
        for line in lines
    )


def test_restart_rebuilds_and_recreates_selected_service(tmp_path: Path) -> None:
    lines = _run_script(tmp_path, "restart", "analyzer")

    assert any("docker/docker-compose.yml" in line and "build analyzer" in line for line in lines)
    assert any(
        "docker/docker-compose.yml" in line and "up -d --force-recreate analyzer" in line
        for line in lines
    )


def test_restart_starts_private_searxng_when_tiered_routing_is_enabled(
    tmp_path: Path,
) -> None:
    lines = _run_script(
        tmp_path,
        "restart",
        env_content=(
            'SEARCH_ROUTING_MODE="searxng_first_cn"\n'
            "SEARXNG_BASE_URLS=http://searxng:8080\n"
        ),
    )

    assert any(
        "--profile searxng" in line
        and "build server" in line
        and "build server searxng" not in line
        for line in lines
    )
    assert any(
        "--profile searxng up -d --force-recreate server searxng" in line
        for line in lines
    )


def test_restart_keeps_legacy_server_only_behavior(tmp_path: Path) -> None:
    lines = _run_script(
        tmp_path,
        "restart",
        env_content="SEARCH_ROUTING_MODE=legacy\n",
    )

    assert any("up -d --force-recreate server" in line for line in lines)
    assert all("--profile searxng" not in line for line in lines)


def test_down_without_service_stops_compose_stack(tmp_path: Path) -> None:
    lines = _run_script(tmp_path, "down")

    assert any("docker/docker-compose.yml" in line and line.endswith(" down") for line in lines)
