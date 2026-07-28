#!/usr/bin/env python3

import json
import re
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
EXTERNAL_DIR = APP_DIR / ".external"
RUNTIME_DIR = EXTERNAL_DIR / "runtime"

PARSER_REPO = "https://github.com/GabrielaFort/LLMPathReportParser.git"
ONCOTREE_REPO = "https://github.com/HuntsmanCancerInstitute/OncoTree.git"

PARSER_DIR = EXTERNAL_DIR / "LLMPathReportParser"
ONCOTREE_DIR = EXTERNAL_DIR / "OncoTree"


def clone_or_update(repo_url, destination):
    if destination.exists():
        print(f"Updating {destination.name}")
        subprocess.run(["git", "-C", str(destination), "pull", "--ff-only"], check=True)
    else:
        print(f"Cloning {destination.name}")
        subprocess.run(["git", "clone", repo_url, str(destination)], check=True)


def latest_release(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def latest_asset_url(owner, repo, asset_pattern):
    release = latest_release(owner, repo)
    pattern = re.compile(asset_pattern)

    for asset in release.get("assets", []):
        if pattern.search(asset["name"]):
            return release["tag_name"], asset["name"], asset["browser_download_url"]

    available = [asset["name"] for asset in release.get("assets", [])]
    raise RuntimeError(
        f"No {owner}/{repo} latest-release asset matched {asset_pattern!r}. "
        f"Available assets: {available}"
    )


def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {destination.name}")
    urllib.request.urlretrieve(url, destination)


def extract_archive(archive_path, extract_dir):
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True)

    if archive_path.name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extract_dir)
    elif archive_path.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive_path) as archive:
            archive.extractall(extract_dir)
    else:
        raise RuntimeError(f"Unsupported archive type: {archive_path}")


def find_one(root, pattern):
    matches = list(root.rglob(pattern))
    if not matches:
        raise RuntimeError(f"Could not find {pattern} under {root}")
    return matches[0]


def find_app(root, app_name):
    matches = [path for path in root.rglob(f"Apps/{app_name}") if path.is_file()]
    if not matches:
        raise RuntimeError(f"Could not find Apps/{app_name} under {root}")
    return matches[0]


def replace_file(source, destination):
    if destination.exists():
        destination.unlink()
    shutil.copy2(source, destination)


def remove_if_exists(path):
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def main():
    EXTERNAL_DIR.mkdir(exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    clone_or_update(PARSER_REPO, PARSER_DIR)
    clone_or_update(ONCOTREE_REPO, ONCOTREE_DIR)

    resources_dir = ONCOTREE_DIR / "Resources"
    if not resources_dir.exists():
        raise RuntimeError(f"Missing OncoTree resources directory: {resources_dir}")

    resources_archive = resources_dir / "OTResources13July2026.zip"
    resources_runtime_dir = RUNTIME_DIR / "OTResources"
    if not resources_archive.exists():
        raise RuntimeError(f"Missing OncoTree resources archive: {resources_archive}")
    extract_archive(resources_archive, resources_runtime_dir)

    _, oncotree_jar_name, oncotree_jar_url = latest_asset_url(
        "HuntsmanCancerInstitute",
        "OncoTree",
        r"OT.*\.jar$",
    )
    oncotree_jar_download = EXTERNAL_DIR / "downloads" / oncotree_jar_name
    download(oncotree_jar_url, oncotree_jar_download)
    replace_file(oncotree_jar_download, RUNTIME_DIR / "OT.jar")

    ####################################################################
    #### TEMPORARILY REMOVING THIS UNTIL USEQ RELEASE IS UPDATED #######
    ####################################################################
    # _, useq_asset_name, useq_asset_url = latest_asset_url(
    #     "HuntsmanCancerInstitute",
    #     "USeq",
    #     r"USeq.*\.(zip|tar\.gz|tgz)$",
    # )
    # useq_archive = EXTERNAL_DIR / "downloads" / useq_asset_name
    # useq_extract_dir = EXTERNAL_DIR / "USeq"
    # download(useq_asset_url, useq_archive)
    # extract_archive(useq_archive, useq_extract_dir)
    # tempus_patho_printer = find_app(useq_extract_dir, "TempusPathoPrinter")
    # useq_runtime_dir = RUNTIME_DIR / "USeq"
    # remove_if_exists(useq_runtime_dir)
    # (useq_runtime_dir / "Apps").mkdir(parents=True)
    # (useq_runtime_dir / "LibraryJars").mkdir()
    # replace_file(tempus_patho_printer, useq_runtime_dir / "Apps" / "TempusPathoPrinter")
    # replace_file(
    #     tempus_patho_printer.parent.parent / "LibraryJars" / "bioToolsCodeLibrary.jar",
    #     useq_runtime_dir / "LibraryJars" / "bioToolsCodeLibrary.jar",
    # )
    # remove_if_exists(RUNTIME_DIR / "TempusPathoPrinter")

    remove_if_exists(ONCOTREE_DIR)
    # remove_if_exists(useq_extract_dir)
    remove_if_exists(EXTERNAL_DIR / "downloads")

    print("External dependencies ready:")
    print(f"  Parser: {PARSER_DIR}")
    print(f"  OncoTree resources: {resources_runtime_dir}")
    print(f"  OncoTree jar: {RUNTIME_DIR / 'OT.jar'}")
    print(f"  TempusPathoPrinter: {RUNTIME_DIR / 'USeq' / 'Apps' / 'TempusPathoPrinter'}")


if __name__ == "__main__":
    main()
