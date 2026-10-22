"""Build the submission ZIP from runtime sources and the Bot facts file only."""

from pathlib import Path
import shutil
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
SUBMISSION = ROOT / "submission" / "group_04_midproject"
ARCHIVE = SUBMISSION.with_suffix(".zip")


def main() -> None:
    sources = sorted(
        path
        for package in ("bot", "common", "server")
        for path in (ROOT / package).rglob("*.py")
        if "__pycache__" not in path.parts
    )
    sources.append(ROOT / "bot" / "data" / "facts.txt")
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    temporary = ARCHIVE.with_suffix(".zip.tmp")
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            for source in sources:
                relative = source.relative_to(ROOT)
                archive.write(source, relative.as_posix())
                mirror = SUBMISSION / "code" / relative
                mirror.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, mirror)
        with ZipFile(temporary) as archive:
            expected = {source.relative_to(ROOT).as_posix() for source in sources}
            if set(archive.namelist()) != expected or len(archive.namelist()) != len(sources):
                raise RuntimeError("Unexpected or duplicate archive entries")
            if archive.testzip() is not None:
                raise RuntimeError("ZIP CRC check failed")
            for source in sources:
                relative = source.relative_to(ROOT)
                payload = source.read_bytes()
                if archive.read(relative.as_posix()) != payload:
                    raise RuntimeError(f"Archive content mismatch: {relative}")
                if (SUBMISSION / "code" / relative).read_bytes() != payload:
                    raise RuntimeError(f"Source mirror mismatch: {relative}")
        temporary.replace(ARCHIVE)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Code-only ZIP: {ARCHIVE} ({len(sources)} files; content and CRC verified)")


if __name__ == "__main__":
    main()
