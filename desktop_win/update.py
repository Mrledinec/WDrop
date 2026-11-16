"""Locate and verify Windows installers published through GitHub Releases."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

VERSION = "0.1.3"
MAX_INSTALLER_SIZE = 512 * 1024 * 1024


@dataclass(frozen=True)
class Release:
    version: str
    filename: str
    url: str
    digest: str
    size: int


def validate_repository(value):
    repository = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Введите репозиторий GitHub в формате владелец/проект.")
    if repository.split("/")[1] in {".", ".."}:
        raise ValueError("Введите имя проекта GitHub.")
    return repository


def check_release(repository):
    repository = validate_repository(repository)
    url = f"https://api.github.com/repos/{repository}/releases/latest"
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"LocalTransfer/{VERSION}",
    })
    try:
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            raise ValueError("Репозиторий недоступен или в нём ещё нет опубликованных выпусков.") from error
        raise
    return parse_release(repository, data)


def parse_release(repository, data):
    tag = data.get("tag_name", "")
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", tag)
    if not match:
        raise ValueError("Тег выпуска должен иметь формат vX.Y.Z.")
    target = tuple(map(int, match.groups()))
    if target <= tuple(map(int, VERSION.split("."))):
        return None

    version = ".".join(map(str, target))
    filename = f"LocalTransfer-Setup-{version}.exe"
    url = f"https://github.com/{repository}/releases/download/{tag}/{filename}"
    asset = next((item for item in data.get("assets", []) if item.get("name") == filename), None)
    if asset is None or asset.get("browser_download_url", "").lower() != url.lower():
        raise ValueError(f"В выпуске отсутствует установщик {filename}.")
    digest = asset.get("digest") or ""
    size = asset.get("size")
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise ValueError("GitHub не предоставил SHA-256 установщика.")
    if not isinstance(size, int) or not 0 < size <= MAX_INSTALLER_SIZE:
        raise ValueError("Недопустимый размер установщика.")
    return Release(version, filename, url, digest[7:].lower(), size)


def download_installer(release, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / release.filename
    digest = hashlib.sha256()
    received = 0
    temporary = None
    try:
        request = Request(release.url, headers={"User-Agent": f"LocalTransfer/{VERSION}"})
        with urlopen(request, timeout=30) as response, NamedTemporaryFile(
            dir=destination, prefix="installer-", suffix=".part", delete=False,
        ) as file:
            temporary = Path(file.name)
            while chunk := response.read(256 * 1024):
                received += len(chunk)
                if received > release.size:
                    raise ValueError("Скачанный файл больше размера, указанного в выпуске.")
                digest.update(chunk)
                file.write(chunk)
        if received != release.size or digest.hexdigest() != release.digest:
            raise ValueError("Размер или контрольная сумма установщика не совпали.")
        os.replace(temporary, output)
        return output
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

