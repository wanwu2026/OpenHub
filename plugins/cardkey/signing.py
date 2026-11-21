"""CardKey 签发核心：从 CardKeySDK/tools/cardkey_tool.py 迁入，字节级一致。

独立模块，不跨仓库 import。仅标准库 + 系统 openssl（保持零第三方依赖）。
私钥只在服务器，绝不进客户端。
"""
import base64
import os
import struct
import subprocess
import tempfile

MAGIC = 0x4B564C31  # "KVL1"
VERSION = 1
B32ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def b32encode(data: bytes) -> str:
    bits = ""
    for b in data:
        bits += format(b, "08b")
    while len(bits) % 5:
        bits += "0"
    return "".join(B32ALPHABET[int(bits[i:i + 5], 2)] for i in range(0, len(bits), 5))


def b32decode(text: str) -> bytes:
    s = "".join(c for c in text.upper() if c in B32ALPHABET)
    bits = "".join(format(B32ALPHABET.index(c), "05b") for c in s)
    out = bytearray()
    for i in range(0, len(bits) - len(bits) % 8, 8):
        out.append(int(bits[i:i + 8], 2))
    return bytes(out)


def build_payload(product_id: str, device_id: str, issued_at: int, expires_at: int, serial: int) -> bytes:
    pb = product_id.encode("utf-8")
    db = device_id.encode("utf-8")
    if len(pb) > 1024 or len(db) > 1024:
        raise ValueError("字符串过长")
    return (struct.pack(">I", MAGIC)
            + struct.pack(">B", VERSION)
            + struct.pack(">H", len(pb)) + pb
            + struct.pack(">H", len(db)) + db
            + struct.pack(">q", issued_at)
            + struct.pack(">q", expires_at)
            + struct.pack(">q", serial))


def parse_payload(data: bytes) -> dict:
    off = 0
    magic = struct.unpack_from(">I", data, off)[0]; off += 4
    version = struct.unpack_from(">B", data, off)[0]; off += 1
    if magic != MAGIC:
        raise ValueError("magic 不匹配")
    if version != VERSION:
        raise ValueError("版本不支持")
    plen = struct.unpack_from(">H", data, off)[0]; off += 2
    product = data[off:off + plen].decode("utf-8"); off += plen
    dlen = struct.unpack_from(">H", data, off)[0]; off += 2
    device = data[off:off + dlen].decode("utf-8"); off += dlen
    issued = struct.unpack_from(">q", data, off)[0]; off += 8
    expires = struct.unpack_from(">q", data, off)[0]; off += 8
    serial = struct.unpack_from(">q", data, off)[0]; off += 8
    return dict(product=product, device=device, issued=issued, expires=expires, serial=serial)


def gen_keypair(outdir: str) -> str:
    """生成 RSA-2048 密钥对，返回公钥 base64（DER）。私钥写 outdir/private.pem。"""
    os.makedirs(outdir, exist_ok=True)
    priv = os.path.join(outdir, "private.pem")
    pub_der = os.path.join(outdir, "public.der")
    subprocess.run(["openssl", "genrsa", "-out", priv, "2048"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["openssl", "rsa", "-in", priv, "-pubout", "-outform", "DER", "-out", pub_der],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(pub_der, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    os.remove(pub_der)
    return b64


def sign(payload: bytes, priv_path: str) -> bytes:
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(payload)
        data_path = tf.name
    sig_path = data_path + ".sig"
    try:
        subprocess.run(["openssl", "dgst", "-sha256", "-sign", priv_path, "-out", sig_path, data_path],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(sig_path, "rb") as f:
            return f.read()
    finally:
        os.remove(data_path)
        if os.path.exists(sig_path):
            os.remove(sig_path)


def verify_sig(payload: bytes, sig: bytes, pub_b64: str) -> bool:
    with tempfile.TemporaryDirectory() as d:
        der = os.path.join(d, "pub.der")
        data = os.path.join(d, "data")
        sg = os.path.join(d, "sig")
        with open(der, "wb") as f:
            f.write(base64.b64decode(pub_b64))
        with open(data, "wb") as f:
            f.write(payload)
        with open(sg, "wb") as f:
            f.write(sig)
        r = subprocess.run(["openssl", "dgst", "-sha256", "-verify", der, "-signature", sg, data],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return r.returncode == 0


def make_license(product_id: str, device_id: str, issued_at: int, expires_at: int,
                 serial: int, priv_path: str) -> str:
    """签发一张 KVL1 凭证串。"""
    payload = build_payload(product_id, device_id, issued_at, expires_at, serial)
    sig = sign(payload, priv_path)
    return "KVL1-" + b32encode(payload) + "-" + b32encode(sig)
