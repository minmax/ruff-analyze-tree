from collections.abc import Mapping
from typing import Collection, Literal, TypeAlias

ImportPath: TypeAlias = str

RootImportPath = Literal[""]

RootPath: TypeAlias = str | RootImportPath

ImportPathOrRoot: TypeAlias = ImportPath | RootImportPath

RuffRawData: TypeAlias = Mapping[str, Collection[str]]
RuffPythonicData: TypeAlias = dict[ImportPath, list[ImportPath]]
