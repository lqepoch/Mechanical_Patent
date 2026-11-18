"""Bring a pinned, licensed upstream source snapshot into vendor/ for local modification.

This script is opt-in. Git submodules remain the default for untouched upstream
code. Never use this to copy unlicensed repositories or bypass API data rights.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from urllib.request import Request, urlopen
from zipfile import ZipFile

SOURCES = {
    "patent-client": {
        "repo": "parkerhancock/patent-client-agents",
        "sha": "dadfeb3b36092549290a384acf8aefcc76493bc5",
        "license": "Apache-2.0",
    },
    "patentkit": {
        "repo": "j-hedtke/patentkit",
        "sha": "47cfa6f7d7fc42e944c76f76b60463d63a086ea3",
        "license": "Apache-2.0",
    },
    "chinese-patent": {
        "repo": "handsomestWei/patent-disclosure-skill",
        "sha": "91e3b43a3e6b568c627bc83ffcb73ff453bf0304",
        "license": "MIT",
    },
    "figure": {
        "repo": "PisenAILab/china-patent-figure-skill",
        "sha": "6ced175436a557f0e27c0f12eaff42844f76d7fc",
        "license": "MIT",
    },
    "template": {
        "repo": "lianghugjil/patent-template",
        "sha": "7176fdb97b3c53d65ebee1035bd7d947dd9d02d8",
        "license": "MIT",
    },
    "ideaforge": {
        "repo": "joyboseroy/ideaforge",
        "sha": "b091fff145965c533eab4f3f9e822ba5cb385197",
        "license": "Apache-2.0",
    },
    "trinno": {
        "repo": "open1s/trinno",
        "sha": "f35f322898a92a525a2a87ce4b48a7052dc531d0",
        "license": "MIT",
    },
}
MAX_DOWNLOAD = 120_000_000
MAX_UNCOMPRESSED = 260_000_000
MAX_ENTRIES = 6000


def safe_member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or len(path.parts) < 2:
        raise ValueError("Unexpected source archive entry.")
    relative = PurePosixPath(*path.parts[1:])
    if ".." in path.parts or str(relative) in {".", ""}:
        raise ValueError("Unsafe source archive path.")
    return relative


def vendor(name: str, output_dir: Path) -> str:
    if name not in SOURCES:
        raise ValueError("Unknown or unaudited source.")
    source = SOURCES[name]
    url = "https://codeload.github.com/" + source["repo"] + "/zip/" + source["sha"]
    req = Request(url, headers={"User-Agent": "MechanicalPatent-VendorMaintainer/0.1"})
    with urlopen(req, timeout=120) as response:
        raw = response.read(MAX_DOWNLOAD + 1)
    if len(raw) > MAX_DOWNLOAD:
        raise ValueError("Source archive exceeds download limit.")
    dest = output_dir / name
    if dest.exists():
        raise FileExistsError("Vendor directory already exists; review or rename it explicitly.")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_dir) as temporary:
        stage = Path(temporary) / "tree"
        stage.mkdir()
        with ZipFile(BytesIO(raw)) as archive:
            info = archive.infolist()
            if len(info) > MAX_ENTRIES or sum(x.file_size for x in info) > MAX_UNCOMPRESSED:
                raise ValueError("Source archive exceeds extraction limits.")
            for item in info:
                if item.is_dir():
                    continue
                relative = safe_member_path(item.filename)
                # ZIP external attribute Unix symlink bit: do not follow vendor symlinks.
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Symlinks are not accepted in vendored ZIPs.")
                target = stage.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        license_file = stage / "LICENSE"
        if not license_file.is_file():
            raise ValueError("Upstream license file missing; refusing vendor import.")
        content = license_file.read_text(encoding="utf-8", errors="replace").lower()
        if source["license"] == "MIT" and "mit license" not in content:
            raise ValueError("MIT license verification failed.")
        if source["license"] == "Apache-2.0" and "apache license" not in content:
            raise ValueError("Apache-2.0 license verification failed.")
        metadata = {
            "source": source["repo"], "git_commit": source["sha"], "license": source["license"],
            "archive_sha256": sha256(raw).hexdigest(),
            "note": "Modified code needs marked changes and original license attribution.",
        }
        (stage / "VENDOR_METADATA.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        stage.rename(dest)
    return str(dest)


def main():
    parser = argparse.ArgumentParser(description="Vendor auditable, pinned upstream source code")
    parser.add_argument("name", nargs="?", choices=list(SOURCES) + ["all"], default="chinese-patent")
    parser.add_argument("--output", type=Path, default=Path("vendor"))
    args = parser.parse_args()
    selected = list(SOURCES) if args.name == "all" else [args.name]
    for entry in selected:
        print(vendor(entry, args.output))


if __name__ == "__main__":
    main()
