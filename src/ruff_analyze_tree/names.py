import posixpath
from itertools import chain

from ruff_analyze_tree.tools import unique
from ruff_analyze_tree.types import ImportPath, ImportPathOrRoot, RootPath, RuffRawData


def find_root_path(data: RuffRawData) -> RootPath:
    files = sorted(unique(chain(data, chain.from_iterable(data.values()))))
    return posixpath.commonpath(files[:1] + files[-1:]) if len(files) >= 2 else ""


def convert_module_filepath_to_package_name(root: str, filepath: str) -> ImportPath:
    path, _ = posixpath.splitext(filepath)
    return path.removeprefix(root).lstrip("/").replace("/", ".").lower()


def join_package(package: ImportPathOrRoot, name: str) -> str:
    assert name, name
    if package:
        return f"{package}.{name}"

    return name


def split_package(module: ImportPath) -> tuple[ImportPathOrRoot, str, bool]:
    return _split_package(module)


def _split_package(
    module: str, is_init_module: bool = False
) -> tuple[ImportPath, str, bool]:
    chunks = module.rsplit(".", 1)
    if len(chunks) == 1:
        return "", chunks[0], is_init_module

    if chunks[-1] == "__init__":
        return _split_package(chunks[0], True)

    return chunks[0], chunks[1], is_init_module
