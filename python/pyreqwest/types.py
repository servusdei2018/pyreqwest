"""Common types and interfaces used in the library."""

from collections.abc import AsyncIterable, Iterable, Mapping, Sequence
from typing import Any, TypeAlias

QueryPrimitive: TypeAlias = str | int | float | bool
QueryVal: TypeAlias = QueryPrimitive | Sequence[QueryPrimitive]

HeadersType: TypeAlias = Mapping[str, str] | Sequence[tuple[str, str]]
QueryParams: TypeAlias = Mapping[str, QueryVal] | Sequence[tuple[str, QueryVal]]
FormParams: TypeAlias = Mapping[str, QueryVal] | Sequence[tuple[str, QueryVal]]
ExtensionsType: TypeAlias = Mapping[str, Any] | Sequence[tuple[str, Any]]

SyncStream: TypeAlias = Iterable[bytes] | Iterable[bytearray] | Iterable[memoryview]
Stream: TypeAlias = AsyncIterable[bytes] | AsyncIterable[bytearray] | AsyncIterable[memoryview] | SyncStream
