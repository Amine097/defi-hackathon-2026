"""Minimal Solidity ABI codec (head/tail encoding, ABI spec v2) for the calls FAULTLINE builds itself.

Supported types: address, bool, uint<N>, int<N>, bytes<N> (N <= 32), bytes, string, tuples "(T1,T2,...)" and dynamic
arrays "T[]" of any of them. Pure Python (no web3 dependency on Vercel); checked against known encodings in tests.
"""
from __future__ import annotations

from .keccak import keccak256

WORD = 32


def split_types(s: str) -> list[str]:
    """'address,(uint256,bytes),bytes[]' -> ['address', '(uint256,bytes)', 'bytes[]'] (top level commas only)."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return [t.strip() for t in out]


def _components(t: str) -> list[str]:
    if t.startswith("tuple"):
        t = t[5:]
    return split_types(t[1:-1])


def _is_tuple(t: str) -> bool:
    return (t.startswith("(") or t.startswith("tuple(")) and t.endswith(")")


def is_dynamic(t: str) -> bool:
    if t.endswith("[]"):
        return True
    if t in ("bytes", "string"):
        return True
    if _is_tuple(t):
        return any(is_dynamic(c) for c in _components(t))
    return False


def _word(n: int) -> bytes:
    return n.to_bytes(WORD, "big")


def _encode_static(t: str, v) -> bytes:
    if t == "address":
        n = int(v, 16) if isinstance(v, str) else int(v)
        if n >> 160:
            raise ValueError(f"address out of range: {v}")
        return _word(n)
    if t == "bool":
        return _word(1 if v else 0)
    if t.startswith("uint"):
        bits = int(t[4:] or 256)
        n = int(v)
        if n < 0 or n >> bits:
            raise ValueError(f"{t} out of range: {v}")
        return _word(n)
    if t.startswith("int"):
        bits = int(t[3:] or 256)
        n = int(v)
        if not -(1 << (bits - 1)) <= n < (1 << (bits - 1)):
            raise ValueError(f"{t} out of range: {v}")
        return _word(n % (1 << 256))
    if t.startswith("bytes"):
        size = int(t[5:])
        b = bytes.fromhex(v[2:]) if isinstance(v, str) else bytes(v)
        if len(b) != size:
            raise ValueError(f"{t} needs {size} bytes, got {len(b)}")
        return b.ljust(WORD, b"\0")
    raise ValueError(f"unsupported static type {t}")


def encode_single(t: str, v) -> bytes:
    if t.endswith("[]"):
        inner = t[:-2]
        return _word(len(v)) + encode_tuple([inner] * len(v), list(v))
    if _is_tuple(t):
        return encode_tuple(_components(t), list(v))
    if t in ("bytes", "string"):
        b = v.encode() if t == "string" else (bytes.fromhex(v[2:]) if isinstance(v, str) else bytes(v))
        return _word(len(b)) + b.ljust((len(b) + WORD - 1) // WORD * WORD, b"\0")
    return _encode_static(t, v)


def encode_tuple(types: list[str], values: list) -> bytes:
    if len(types) != len(values):
        raise ValueError(f"{len(types)} types for {len(values)} values")
    heads, tails = [], []
    head_size = sum(WORD if is_dynamic(t) else len(encode_single(t, v)) for t, v in zip(types, values))
    offset = head_size
    for t, v in zip(types, values):
        enc = encode_single(t, v)
        if is_dynamic(t):
            heads.append(_word(offset))
            tails.append(enc)
            offset += len(enc)
        else:
            heads.append(enc)
    return b"".join(heads) + b"".join(tails)


def selector(signature: str) -> bytes:
    return keccak256(signature.encode())[:4]


def encode_call(signature: str, args: list) -> str:
    """'repay((address,address,address,address,uint256),uint256,uint256,address,bytes)' + args -> 0x calldata."""
    name_end = signature.index("(")
    types = split_types(signature[name_end + 1:-1])
    return "0x" + (selector(signature) + encode_tuple(types, args)).hex()


# ---- decoding -----------------------------------------------------------------------------------------------------
def _static_size(t: str) -> int:
    if _is_tuple(t) and not is_dynamic(t):
        return sum(_static_size(c) for c in _components(t))
    return WORD


def _decode_static(t: str, data: bytes, pos: int):
    w = data[pos:pos + WORD]
    if len(w) < WORD:
        raise ValueError("data too short")
    n = int.from_bytes(w, "big")
    if t == "address":
        return "0x" + w[-20:].hex()
    if t == "bool":
        return n != 0
    if t.startswith("uint"):
        return n
    if t.startswith("int"):
        return n - (1 << 256) if n >> 255 else n
    if t.startswith("bytes"):
        return "0x" + w[:int(t[5:])].hex()
    raise ValueError(f"unsupported type {t}")


def decode_single(t: str, data: bytes, pos: int):
    """Decode type t whose encoding starts at data[pos] (pos = start of the value's own encoding)."""
    if t.endswith("[]"):
        n = int.from_bytes(data[pos:pos + WORD], "big")
        return decode_tuple([t[:-2]] * n, data, pos + WORD)
    if _is_tuple(t):
        return decode_tuple(_components(t), data, pos)
    if t in ("bytes", "string"):
        n = int.from_bytes(data[pos:pos + WORD], "big")
        b = data[pos + WORD:pos + WORD + n]
        return b.decode("utf-8", "replace") if t == "string" else "0x" + b.hex()
    return _decode_static(t, data, pos)


def decode_tuple(types: list[str], data: bytes, base: int = 0) -> list:
    out, pos = [], base
    for t in types:
        if is_dynamic(t):
            off = int.from_bytes(data[pos:pos + WORD], "big")
            out.append(decode_single(t, data, base + off))
            pos += WORD
        else:
            out.append(decode_single(t, data, pos))
            pos += _static_size(t)
    return out


def decode(types: list[str] | str, hexdata: str) -> list:
    if isinstance(types, str):
        types = split_types(types)
    data = bytes.fromhex(hexdata[2:] if hexdata.startswith("0x") else hexdata)
    return decode_tuple(types, data)


def event_topic(signature: str) -> str:
    return "0x" + keccak256(signature.encode()).hex()


MARKET_PARAMS = "(address,address,address,address,uint256)"


def market_params_tuple(mp: dict) -> list:
    """Morpho Blue MarketParams(loanToken, collateralToken, oracle, irm, lltv) from a reader dict."""
    return [mp["loan_token"], mp["collateral_token"] or "0x" + "0" * 40, mp["oracle"], mp["irm"], int(mp["lltv_raw"])]


def market_id(mp: dict) -> str:
    return "0x" + keccak256(encode_tuple(split_types(MARKET_PARAMS[1:-1]), market_params_tuple(mp))).hex()
