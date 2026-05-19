# author: yannik fontana, creation date: 06.05.2026
"""
Serialize and restore experiment object trees to HDF5 (type-tagged groups, max depth).

Writes every public instance attribute (name not starting with ``_``) from ``vars(obj)``.
Loads with ``object.__new__(cls)`` — no ``__init__`` / ``__post_init__``.
"""
from __future__ import annotations

import datetime
import importlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np

DEFAULT_MAX_DEPTH = 32

_INVALID_H5_NAME = re.compile(r"[^\w.\-]")

METADATA_ATTRS = frozenset({"pyctrl_exp_class", "pyctrl_exp_format_version"})


class HDF5TreeError(ValueError):
    """Raised when serialization or deserialization hits limits or unsupported values."""


def sanitize_h5_name(name: str) -> str:
    """Make a string safe as a single HDF5 path component (no ``/``)."""
    if not name:
        return "_empty"
    s = str(name).replace("/", "_slash_")
    s = _INVALID_H5_NAME.sub("_", s)
    if s[0].isdigit():
        s = f"_{s}"
    return s


def _check_depth(depth: int, max_depth: int) -> None:
    if depth > max_depth:
        raise HDF5TreeError(
            f"HDF5 tree depth {depth} exceeds max_depth={max_depth}. "
            "Increase max_depth or simplify nested structures."
        )


def _dataclass_fullname(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def resolve_class(fullname: str) -> type:
    """Import and return a class from ``module.qualname`` (supports nested qualnames)."""
    if isinstance(fullname, bytes):
        fullname = fullname.decode("utf-8")
    module_name, _, qualname = str(fullname).rpartition(".")
    if not module_name or not qualname:
        raise HDF5TreeError(f"invalid pyctrl class name {fullname!r}")
    mod = importlib.import_module(module_name)
    cur: Any = mod
    for part in qualname.split("."):
        cur = getattr(cur, part)
    if not isinstance(cur, type):
        raise HDF5TreeError(f"resolved {fullname!r} is not a type")
    return cur


def write_instance_to_h5(
    h5: h5py.File,
    obj: Any,
    *,
    group_name: str = "run",
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> h5py.Group:
    """
    Write all instance attributes whose names do not start with ``_``.

    Sets ``pyctrl_exp_class`` and ``pyctrl_exp_format_version`` on the root group.
    """
    root = h5.create_group(sanitize_h5_name(group_name))
    root.attrs["pyctrl_exp_class"] = _dataclass_fullname(type(obj))
    root.attrs["pyctrl_exp_format_version"] = np.uint32(1)

    for name in sorted(vars(obj).keys()):
        if name.startswith("_"):
            continue
        write_h5_value(
            root,
            name,
            getattr(obj, name),
            depth=0,
            max_depth=max_depth,
        )
    return root


def _tag_h5_member(member: h5py.Dataset | h5py.Group, original_name: str) -> None:
    member.attrs["pyctrl_field"] = original_name


def _write_scalar_attr(parent: h5py.Group, key: str, name: str, value: Any) -> None:
    parent.attrs[key] = value
    parent.attrs[f"{key}__pyctrl_orig"] = name


def write_h5_value(
    parent: h5py.Group,
    name: str,
    value: Any,
    *,
    depth: int,
    max_depth: int,
) -> None:
    """
    Attach ``value`` under ``parent`` using ``name`` (sanitized for groups/datasets).

    ``depth`` is the current nesting level (0 = top-level attributes under ``run``).
    """
    _check_depth(depth, max_depth)
    key = sanitize_h5_name(name)

    if value is None:
        parent.attrs[f"{key}__isnull"] = np.uint8(1)
        parent.attrs[f"{key}__pyctrl_orig"] = name
        return

    if isinstance(value, np.ndarray):
        ds = parent.create_dataset(key, data=value, compression="gzip")
        _tag_h5_member(ds, name)
        return

    if isinstance(value, np.generic):
        _write_scalar_attr(parent, key, name, value.item())
        return

    if isinstance(value, bool):
        _write_scalar_attr(parent, key, name, value)
        return

    if isinstance(value, int) and not isinstance(value, bool):
        _write_scalar_attr(parent, key, name, value)
        return

    if isinstance(value, float):
        _write_scalar_attr(parent, key, name, value)
        return

    if isinstance(value, str):
        if len(value) > 32000:
            dt = h5py.string_dtype(encoding="utf-8")
            ds = parent.create_dataset(key, (), dtype=dt)
            ds[()] = value
            _tag_h5_member(ds, name)
        else:
            _write_scalar_attr(parent, key, name, value)
        return

    if isinstance(value, datetime.datetime):
        _write_scalar_attr(parent, key, name, value.isoformat())
        return

    if isinstance(value, bytes):
        _write_scalar_attr(parent, key, name, np.void(value))
        return

    if is_dataclass(value):
        grp = parent.create_group(key)
        _tag_h5_member(grp, name)
        grp.attrs["pyctrl_dataclass"] = _dataclass_fullname(type(value))
        for f in fields(value):
            write_h5_value(
                grp,
                f.name,
                getattr(value, f.name),
                depth=depth + 1,
                max_depth=max_depth,
            )
        return

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        _write_sequence(parent, key, name, value, depth=depth, max_depth=max_depth)
        return

    if isinstance(value, Mapping):
        grp = parent.create_group(key)
        _tag_h5_member(grp, name)
        grp.attrs["pyctrl_kind"] = "mapping"
        for k, v in sorted(value.items(), key=lambda kv: str(kv[0])):
            write_h5_value(
                grp,
                str(k),
                v,
                depth=depth + 1,
                max_depth=max_depth,
            )
        return

    raise HDF5TreeError(
        f"Unsupported type for HDF5 field {name!r}: {type(value)!r}. "
        "Extend dataparsing.write_h5_value or convert to supported types."
    )


def _write_sequence(
    parent: h5py.Group,
    key: str,
    original_name: str,
    value: Sequence[Any],
    *,
    depth: int,
    max_depth: int,
) -> None:
    _check_depth(depth, max_depth)
    dt_utf8 = h5py.string_dtype(encoding="utf-8")

    if len(value) == 0:
        ds = parent.create_dataset(key, (0,), dtype=dt_utf8)
        _tag_h5_member(ds, original_name)
        ds.attrs["sequence_kind"] = "str_list"
        ds.attrs["empty_sequence"] = np.uint8(1)
        return

    if all(isinstance(x, str) for x in value):
        ds = parent.create_dataset(key, (len(value),), dtype=dt_utf8, data=list(value))
        _tag_h5_member(ds, original_name)
        ds.attrs["sequence_kind"] = "str_list"
        return

    if all(isinstance(x, (bool, int, float, np.integer, np.floating)) for x in value):
        ds = parent.create_dataset(key, data=np.asarray(value))
        _tag_h5_member(ds, original_name)
        ds.attrs["sequence_kind"] = "numeric_list"
        return

    raise HDF5TreeError(
        f"Unsupported mixed or non-primitive sequence for field {key!r}; "
        "use list[str], numeric list, or nested dataclass/dict."
    )


# --- Load -----------------------------------------------------------------


def read_instance_from_h5(
    path: str | Path,
    *,
    target_cls: type | None = None,
    group_name: str = "run",
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> Any:
    """
    Build an instance from an HDF5 file without calling ``__init__``.

    Uses ``pyctrl_exp_class`` on the root group unless ``target_cls`` is given;
    if both are given, the file class must be a subclass of ``target_cls``.
    """
    path = Path(path)
    with h5py.File(path, "r") as h5:
        gname = sanitize_h5_name(group_name)
        if gname not in h5:
            raise HDF5TreeError(f"group {gname!r} not found in {path}")
        root = h5[gname]
        file_cls_name = root.attrs.get("pyctrl_exp_class")
        if file_cls_name is None:
            raise HDF5TreeError(
                f"missing pyctrl_exp_class on {gname!r}; cannot determine class to load"
            )
        if isinstance(file_cls_name, bytes):
            file_cls_name = file_cls_name.decode("utf-8")
        resolved = resolve_class(str(file_cls_name))
        if target_cls is not None and not issubclass(resolved, target_cls):
            raise HDF5TreeError(
                f"file class {resolved!r} is not a subclass of {target_cls!r}"
            )
        cls_to_use = resolved
        state = _read_group_state(root, depth=0, max_depth=max_depth)
        return _hydrate_instance(cls_to_use, state)


def _hydrate_instance(cls: type, state: dict[str, Any]) -> Any:
    obj = object.__new__(cls)
    for f in fields(cls):
        if f.default_factory is not MISSING:
            setattr(obj, f.name, f.default_factory())
        elif f.default is not MISSING:
            setattr(obj, f.name, f.default)
    for k, v in state.items():
        setattr(obj, k, v)
    return obj


def _read_group_state(
    grp: h5py.Group,
    *,
    depth: int,
    max_depth: int,
) -> dict[str, Any]:
    _check_depth(depth, max_depth)
    data: dict[str, Any] = {}

    for h5key in grp.keys():
        child = grp[h5key]
        orig = child.attrs.get("pyctrl_field")
        if isinstance(orig, bytes):
            orig = orig.decode("utf-8")
        if orig is None:
            orig = h5key
        else:
            orig = str(orig)
        data[orig] = read_h5_node(child, depth=depth + 1, max_depth=max_depth)

    _read_scalar_and_null_attrs(grp, data)
    return data


def _read_scalar_and_null_attrs(grp: h5py.Group, data: dict[str, Any]) -> None:
    attrs = dict(grp.attrs)
    for k, v in list(attrs.items()):
        if k in METADATA_ATTRS:
            continue
        if k.endswith("__pyctrl_orig"):
            continue
        if k.endswith("__isnull"):
            continue
        if f"{k}__pyctrl_orig" in attrs:
            orig = attrs[f"{k}__pyctrl_orig"]
            if isinstance(orig, bytes):
                orig = orig.decode("utf-8")
            orig = str(orig)
            data[orig] = _decode_stored_scalar(attrs[k])

    for k, v in list(attrs.items()):
        if not k.endswith("__isnull"):
            continue
        base = k[: -len("__isnull")]
        orig = attrs.get(f"{base}__pyctrl_orig", base)
        if isinstance(orig, bytes):
            orig = orig.decode("utf-8")
        data[str(orig)] = None


def _decode_stored_scalar(raw: Any) -> Any:
    if isinstance(raw, np.void):
        return bytes(raw)
    if isinstance(raw, bytes | np.bytes_):
        return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    if isinstance(raw, str):
        t = raw
        if len(t) >= 10 and t[4] == "-" and t[7] == "-":
            try:
                return datetime.datetime.fromisoformat(t)
            except ValueError:
                return raw
        return raw
    if isinstance(raw, np.generic):
        return raw.item()
    return raw


def read_h5_node(
    node: h5py.Dataset | h5py.Group,
    *,
    depth: int,
    max_depth: int,
) -> Any:
    if isinstance(node, h5py.Dataset):
        return _read_dataset(node)

    if isinstance(node, h5py.Group):
        kind = node.attrs.get("pyctrl_kind")
        if isinstance(kind, bytes):
            kind = kind.decode("utf-8")
        dc = node.attrs.get("pyctrl_dataclass")
        if isinstance(dc, bytes):
            dc = dc.decode("utf-8")

        if dc is not None:
            cls = resolve_class(str(dc))
            state = _read_group_state(node, depth=depth, max_depth=max_depth)
            return _hydrate_instance(cls, state)

        if kind == "mapping":
            return _read_mapping_group(node, depth=depth, max_depth=max_depth)

        raise HDF5TreeError(
            f"group {node.name!r} has neither pyctrl_dataclass nor pyctrl_kind=mapping; "
            "cannot deserialize this layout"
        )

    raise HDF5TreeError(f"unsupported HDF5 node {node!r}")


def _read_mapping_group(
    grp: h5py.Group,
    *,
    depth: int,
    max_depth: int,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for h5key in grp.keys():
        child = grp[h5key]
        orig = child.attrs.get("pyctrl_field", h5key)
        if isinstance(orig, bytes):
            orig = orig.decode("utf-8")
        orig = str(orig)
        out[orig] = read_h5_node(child, depth=depth + 1, max_depth=max_depth)
    _read_scalar_and_null_attrs(grp, out)
    return out


def _read_dataset(ds: h5py.Dataset) -> Any:
    sk = ds.attrs.get("sequence_kind")
    if isinstance(sk, bytes):
        sk = sk.decode("utf-8")

    if sk == "str_list":
        arr = ds[()]
        if arr.size == 0:
            return []
        return [x.decode("utf-8") if isinstance(x, bytes) else str(x) for x in arr]

    if sk == "numeric_list":
        return np.array(ds[()])

    if ds.shape == ():
        val = ds[()]
        if isinstance(val, bytes):
            return val.decode("utf-8")
        if isinstance(val, str):
            return val
        if isinstance(val, np.generic):
            return val.item()
        return val

    return np.array(ds[()])

