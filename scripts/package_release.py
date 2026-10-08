"""Package tested cores, dependency notices, source trees, and SHA-256 hashes."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

from version import ROOT, read_version

TARGETS = {
    "windows-x64": ("windows-x64", "xemu_libretro.dll"),
    "linux-x86_64-ubuntu26.04": ("", "xemu_libretro.so"),
    "linux-arm64-debian13": ("linux-arm64", "xemu_libretro.so"),
    "linux-riscv64-debian13": ("linux-riscv64", "xemu_libretro.so"),
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def license_name(path):
    return path.name.lower().startswith(("license", "licence", "copying", "copyright", "notice")) or "LICENSES" in path.parts


def collect_notices(source, destination):
    for path in source.rglob("*"):
        if license_name(path) and ".git" not in path.parts and path.is_file() and not path.is_symlink():
            if path.stat().st_size > 2_000_000:
                continue
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def mxe_notices(archive, destination):
    """Read notices from MXE's downloaded source archives without extracting code."""
    with tarfile.open(archive) as outer:
        for member in outer:
            name = Path(member.name)
            if not member.isfile() or "pkg" not in name.parts:
                continue
            if not (".tar" in name.name or name.suffix in (".tgz", ".zip")):
                continue
            data = io.BytesIO(outer.extractfile(member).read())
            if name.suffix == ".zip":
                with zipfile.ZipFile(data) as inner:
                    entries = [(entry.filename, entry.file_size, lambda e=entry: inner.read(e))
                               for entry in inner.infolist() if not entry.is_dir()]
                    save_archive_notices(entries, destination / name.name)
            else:
                with tarfile.open(fileobj=data) as inner:
                    entries = [(entry.name, entry.size, lambda e=entry: inner.extractfile(e).read())
                               for entry in inner if entry.isfile()]
                    save_archive_notices(entries, destination / name.name)


def save_archive_notices(entries, destination):
    for name, size, read in entries:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe source archive member: {name}")
        if license_name(path) and size <= 2_000_000:
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(read())


def source_filter(member):
    path = Path(member.name)
    if any(part in (".git", "__pycache__", ".ccache") for part in path.parts):
        return None
    if path.name == ".xemu-retro-overlay.json":
        return None
    # QEMU's unrelated prebuilt PC firmware is not part of the Xbox core.
    if path.parts[:2] == ("xemu", "pc-bios") and member.isfile():
        original = ROOT / "upstream" / path
        with original.open("rb") as stream:
            if b"\0" in stream.read(8192):
                return None
    asset = path.name in ("mcpx_1.0.bin", "bios.bin", "eeprom.bin", "xbox_hdd.qcow2") or path.suffix in (".iso", ".xiso", ".qcow2")
    # Unrelated upstream QEMU test disks are not source for the linked core.
    if asset and path.parts[:2] == ("xemu", "tests"):
        return None
    if asset:
        raise ValueError(f"Unexpected user asset in source tree: {member.name}")
    member.uid = member.gid = 0
    member.uname = member.gname = ""
    return member


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsp-source", type=Path, required=True)
    parser.add_argument("--dsp-vendor", type=Path, required=True)
    parser.add_argument("--mxe-sources", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    version = read_version()
    output = (args.output or ROOT / "build/packages" / version).resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Use an empty output directory to avoid mixing releases")
    output.mkdir(parents=True, exist_ok=True)
    tree = subprocess.check_output(["git", "write-tree"], cwd=ROOT, text=True).strip()
    archive = subprocess.check_output(["git", "archive", "--format=tar", tree], cwd=ROOT)
    upstream = ROOT / "upstream/xemu"
    with tempfile.TemporaryDirectory(prefix="xemu-release-") as temporary:
        scratch = Path(temporary)
        project = scratch / "project"
        project.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            source.extractall(project, filter="data")
        if (project / "VERSION").read_text().strip() != version:
            parser.error("Stage VERSION before packaging")
        if subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT).strip():
            parser.error("Stage all tracked changes before packaging")
        pins = json.loads((project / "upstream.json").read_text())
        for source, expected in ((upstream, pins["xemu"]["revision"]),
                                 (args.dsp_source, pins["dsp56300"]["revision"])):
            actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
            if actual != expected:
                raise ValueError(f"Source revision mismatch: {source}")
        notices = scratch / "third-party-notices"
        print("Collecting dependency notices", flush=True)
        collect_notices(upstream, notices / "xemu")
        collect_notices(args.dsp_source, notices / "dsp56300")
        collect_notices(args.dsp_vendor, notices / "rust")
        mxe_notices(args.mxe_sources, notices / "mxe")
        provenance = {"version": version, "git_tree": tree, "upstream": pins, "cores": {}}
        for target, (directory, library) in TARGETS.items():
            built = ROOT / "build/native-dist" / directory
            if (built / "VERSION").read_text().strip() != version:
                raise ValueError(f"Stale core build: {target}")
            package_name = f"xemu-libretro-{version}-{target}"
            package = scratch / package_name
            package.mkdir()
            for name in (library, "xemu_libretro.info", "VERSION", "COPYING", "COPYING.LIB"):
                shutil.copy2(built / name, package / name)
            shutil.copy2(upstream / "LICENSE", package / "XEMU-LICENSE")
            for name in ("README.md", "NOTICE.md", "LICENSE", "upstream.json"):
                shutil.copy2(project / name, package / name)
            for name in ("docs", "LICENSES"):
                shutil.copytree(project / name, package / name)
            shutil.copytree(notices, package / "third-party-notices")
            provenance["cores"][target] = {"file": library, "sha256": digest(package / library)}
            if target == "windows-x64":
                with zipfile.ZipFile(output / (package_name + ".zip"), "w", zipfile.ZIP_DEFLATED,
                                     compresslevel=6, strict_timestamps=False) as bundle:
                    for path in sorted(package.rglob("*")):
                        if path.is_file():
                            bundle.write(path, path.relative_to(package))
            else:
                with tarfile.open(output / (package_name + ".tar.gz"), "w:gz") as bundle:
                    bundle.add(package, arcname=package_name)
            print("Packaged", target, flush=True)
        provenance_path = output / "BUILD-INFO.json"
        provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")
        cargo_config = scratch / "cargo-config.toml"
        cargo_config.write_text('[source.crates-io]\nreplace-with = "vendored-sources"\n\n[source.vendored-sources]\ndirectory = "vendor"\n')
        print("Packaging companion source trees", flush=True)
        with tarfile.open(output / f"xemu-libretro-{version}-sources.tar.gz", "w:gz") as bundle:
            bundle.add(project, arcname="project", filter=source_filter)
            bundle.add(upstream, arcname="xemu", filter=source_filter)
            bundle.add(args.dsp_source, arcname="dsp56300", filter=source_filter)
            bundle.add(args.dsp_vendor, arcname="dsp56300/vendor", filter=source_filter)
            bundle.add(cargo_config, arcname="dsp56300/.cargo/config.toml")
            bundle.add(provenance_path, arcname="BUILD-INFO.json")
        shutil.copy2(args.mxe_sources, output / f"xemu-libretro-{version}-windows-dependency-sources.tar.gz")
        sums = [f"{digest(path)}  {path.name}" for path in sorted(output.iterdir()) if path.is_file()]
        (output / "SHA256SUMS").write_text("\n".join(sums) + "\n")
        print("Release files:", output, flush=True)


if __name__ == "__main__":
    main()
