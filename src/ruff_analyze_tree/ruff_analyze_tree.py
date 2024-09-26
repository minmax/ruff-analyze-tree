"""
```bash
ruff analyze graph src | python -m ruff_analyze_tree
```
"""

import json
import posixpath
import statistics
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import cache
from itertools import chain
from operator import attrgetter
from typing import (
    Collection,
    Self,
    TypeAlias,
)

from rich.console import Console
from rich.markup import escape
from rich.style import Style
from rich.tree import Tree

from ruff_analyze_tree.colors import get_color
from ruff_analyze_tree.names import (
    convert_module_filepath_to_package_name,
    find_root_path,
    split_package,
)
from ruff_analyze_tree.tools import unique
from ruff_analyze_tree.types import (
    ImportPath,
    ImportPathOrRoot,
    RuffPythonicData,
    RuffRawData,
)

USAGE = """
Add ruff output to script:
ruff analyze graph src | python -m ruff_analyze_tree

Options:
    "-q {percentile}" - Сommon boundary for dividing into good (green) / bad (red), e.g. "-q 99.9"
    "--hide-zero" - Don't show files without dependencies.
    "--hide-deps" - Don't show dependencies.
    "--deps" - Show only dependencies.
    "--hide-stats" - Don't show statistics.
""".strip()


CONSOLE = Console()

QUANTILE_FACTOR = 100

Modules: TypeAlias = dict[ImportPathOrRoot, "Module"]
Packages: TypeAlias = dict[ImportPathOrRoot, "Package"]


def main() -> None:
    if sys.stdin.isatty():
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    hide_zero = "--hide-zero" in sys.argv
    hide_deps = "--hide-deps" in sys.argv
    only_deps = "--deps" in sys.argv
    hide_stats = "--hide-stats" in sys.argv

    quantile_param = (
        float(sys.argv[sys.argv.index("-q") + 1]) if "-q" in sys.argv else 95
    )
    assert 0 <= quantile_param <= 100
    quantile = quantile_param * QUANTILE_FACTOR

    data, root_import = convert_file_path_to_import_strings(json.load(sys.stdin))

    duplicated_dependencies = tuple(chain.from_iterable(data.values()))
    counted_dependencies = Counter(duplicated_dependencies)

    root_package = get_finalized_tree(
        root_import,
        data,
        unique(duplicated_dependencies),
        counted_dependencies,
        int(quantile_param),
    )

    relations_counters = tuple(counted_dependencies.values())
    quantiles = statistics.quantiles(relations_counters, n=100 * QUANTILE_FACTOR + 1)
    dependencies_quantile = int(quantiles[max(int(quantile) - 1, 0)])

    draw_options = DrawOptions(
        quantile=quantile_param,
        dependencies_quantile=dependencies_quantile,
        skip_dependencies=hide_deps,
        only_deps=only_deps,
        skip_zero=hide_zero,
    )

    visible_first_level = [
        c for c in root_package.children if c.is_visible(draw_options)
    ]
    if len(visible_first_level) == 1:
        root_import = root_package.name
        root_package = visible_first_level[0]

    tree_root = Tree(f"✨✨✨ [b green]{root_import} modules ✨✨✨", highlight=True)

    draw_tree(tree_root, root_package, draw_options)

    CONSOLE.print(tree_root)

    if not hide_stats:
        CONSOLE.print()
        CONSOLE.print("Dependencies statistics:")
        CONSOLE.print(f"Arithmetic mean: {statistics.mean(relations_counters)}")
        CONSOLE.print(f"Median (middle value): {statistics.median(relations_counters)}")
        CONSOLE.print(f"Quantile ({quantile_param}%): {dependencies_quantile}")


@dataclass(slots=True, frozen=True)
class DrawOptions:
    quantile: float
    dependencies_quantile: int
    skip_dependencies: bool = False
    only_deps: bool = False
    skip_zero: bool = False

    @property
    def colorize(self) -> bool:
        return not self.only_deps


@dataclass(slots=True)
class PyImported:
    import_path: ImportPath
    name: str
    is_dependency: bool
    direct_relations: int

    @property
    def total_relations(self) -> int:
        return self.direct_relations

    def is_visible(self, options: DrawOptions) -> bool:
        if self.is_dependency:
            if options.skip_dependencies:
                return False
        elif options.only_deps:
            return False

        if options.skip_zero and self.total_relations == 0:
            return False

        return True


@dataclass(slots=True)
class Module(PyImported):
    parent: "Package"

    def apply_counters(self) -> int:
        return self.direct_relations

    __eq__ = object.__eq__  # pyright: ignore[reportAssignmentType]
    __hash__ = object.__hash__  # pyright: ignore[reportAssignmentType]


@dataclass(slots=True, eq=False)
class Package(PyImported):
    parent: "Self | None" = None
    children: list[Module | Self] = field(default_factory=list)
    sub_packages: list[Self] = field(default_factory=list)
    children_relations: int = 0
    children_quantile: int = 0
    is_init_module: bool = False

    def add_module(self, module: Module) -> None:
        self.children.append(module)

    def add_package(self, package: Self) -> None:
        self.children.append(package)
        self.sub_packages.append(package)

    def sort(self) -> None:
        self.children.sort(key=attrgetter("name"))
        for obj in self.sub_packages:
            obj.sort()

    def apply_counters(self) -> int:
        self.children_relations = summary = sum(
            obj.apply_counters() for obj in self.children
        )
        return summary + self.direct_relations

    def apply_quantiles(self, quantile: int) -> None:
        if len(self.children) < 2:
            self.children_quantile = 0
            return

        quantiles = statistics.quantiles(
            [obj.total_relations for obj in self.children], n=100 + 1
        )
        self.children_quantile = int(quantiles[max(quantile - 1, 0)])

        for obj in self.sub_packages:
            obj.apply_quantiles(quantile)

    @property
    def total_relations(self) -> int:
        return self.direct_relations + self.children_relations

    @cache
    def is_visible(self, options: DrawOptions) -> bool:
        for c in self.children:
            if c.is_visible(options):
                return True

        if self.is_dependency:
            if options.skip_dependencies:
                return False
        elif options.only_deps:
            return False

        if options.skip_zero and self.total_relations == 0:
            return False

        return True

    __eq__ = object.__eq__  # pyright: ignore[reportAssignmentType]
    __hash__ = object.__hash__  # pyright: ignore[reportAssignmentType]


@dataclass(frozen=True, slots=True)
class PyFactory:
    counters: Mapping[ImportPath, int]
    modules: Modules
    packages: Packages
    is_dependency: bool = False

    def module(self, parent: Package, import_path: ImportPath, name: str) -> Module:
        module = Module(
            import_path,
            name,
            is_dependency=self.is_dependency,
            direct_relations=self.counters.get(import_path, 0),
            parent=parent,
        )
        return self.modules.setdefault(import_path, module)

    def get_module(self, import_path: ImportPathOrRoot) -> Module | None:
        return self.modules.get(import_path)

    def get_package(self, import_path: ImportPathOrRoot) -> Package | None:
        return self.packages.get(import_path)

    def package(
        self, parent: Package, import_path: ImportPath, name: str, is_init_module: bool
    ) -> Package:
        package = Package(
            import_path,
            name,
            is_dependency=self.is_dependency,
            direct_relations=self.counters.get(import_path, 0),
            is_init_module=is_init_module,
            parent=parent,
        )
        return self.packages.setdefault(import_path, package)


def draw_tree(
    parent: Tree, package_or_module: Package | Module, options: DrawOptions
) -> None:
    match package_or_module:
        case Package():
            draw_package(parent, package_or_module, options)
        case Module():
            draw_module(parent, package_or_module, options)


def draw_package(parent: Tree, package: Package, options: DrawOptions) -> None:
    if not package.is_visible(options):
        return

    # guide_style = (
    #     get_color(p.total_relations, pp.children_quantile)
    #     if ((p := package.parent) and (pp := p.parent))
    #     else None
    # )
    star = "*" if package.is_dependency else ""
    new_node = parent.add(
        escape(
            f"{package.name}{star} ({package.direct_relations}) {{{package.children_relations}}}"
        ),
        style=get_style(package, options),
    )

    for obj in package.children:
        draw_tree(new_node, obj, options)


def draw_module(parent: Tree, module: Module, options: DrawOptions) -> None:
    if not module.is_visible(options):
        return

    # guide_style = (
    #     get_color(p.total_relations, pp.children_quantile)
    #     if ((p := module.parent) and (pp := p.parent))
    #     else None
    # )
    star = "*" if module.is_dependency else ""
    parent.add(
        f"{module.name}{star} ({module.direct_relations})",
        style=get_style(module, options),
    )


def get_style(module: Package | Module, options: DrawOptions) -> Style | None:
    if options.only_deps:
        return None

    return get_color(module.direct_relations, options.dependencies_quantile)


def get_finalized_tree(
    root_name: ImportPathOrRoot,
    imports: Collection[ImportPath],
    dependencies: Iterable[ImportPath],
    counted_dependencies: Mapping[ImportPath, int],
    quantile: int,
) -> Package:
    root_package = build_modules_tree(
        root_name, imports, dependencies, counted_dependencies
    )

    root_package.sort()
    root_package.apply_counters()
    root_package.apply_quantiles(quantile)

    return root_package


def build_modules_tree(
    root_name: ImportPathOrRoot,
    imports: Collection[ImportPath],
    dependencies: Iterable[ImportPath],
    counted_dependencies: Mapping[ImportPath, int],
) -> Package:
    root_package = Package(
        import_path="", name=root_name, is_dependency=False, direct_relations=0
    )
    packages: Packages = {"": root_package}
    modules: Modules = {}

    append_imports_to_tree(imports, PyFactory(counted_dependencies, modules, packages))
    append_imports_to_tree(
        unique(dependencies, visited=set(imports) | set(packages)),
        PyFactory(counted_dependencies, modules, packages, is_dependency=True),
    )

    return root_package


def append_imports_to_tree(imports: Iterable[ImportPath], factory: PyFactory) -> None:
    for import_path in imports:
        append_module_or_package_to_tree(import_path, factory)


def append_module_or_package_to_tree(
    import_path: ImportPath, factory: PyFactory
) -> None:
    module_package, module_name, is_init_module = split_package(import_path)
    parent_package = get_or_make_package(module_package, factory)

    if is_init_module:
        package_import = (
            f"{module_package}.{module_name}" if module_package else module_name
        )
        if (package := factory.get_package(package_import)) is not None:
            return

        package = factory.package(
            parent_package,
            import_path=package_import,
            name=module_name,
            is_init_module=is_init_module,
        )
        parent_package.add_package(package)
    else:
        if (module := factory.get_module(import_path)) is not None:
            return

        module = factory.module(
            parent_package, import_path=import_path, name=module_name
        )
        parent_package.add_module(module)


def get_or_make_package(import_path: ImportPathOrRoot, factory: PyFactory) -> Package:
    parent_import, name, is_init_module = split_package(import_path)

    package_import = f"{parent_import}.{name}" if parent_import else name
    if (package := factory.get_package(package_import)) is not None:
        return package

    assert not is_init_module
    parent_package = get_or_make_package(parent_import, factory)
    package = factory.package(
        parent_package,
        import_path=package_import,
        name=name,
        is_init_module=is_init_module,
    )
    parent_package.add_package(package)
    return package


def convert_file_path_to_import_strings(
    data: RuffRawData,
) -> tuple[RuffPythonicData, ImportPathOrRoot]:
    root_path = find_root_path(data)

    modules_map = {
        convert_module_filepath_to_package_name(root_path, name): [
            convert_module_filepath_to_package_name(root_path, dep)
            for dep in dependencies
        ]
        for name, dependencies in data.items()
    }
    root_module = convert_module_filepath_to_package_name(
        "", posixpath.split(root_path)[1] or root_path
    )
    return modules_map, root_module


if __name__ == "__main__":
    main()
