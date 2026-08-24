import base64
import json
import os
import re
import sys
from pathlib import Path

from log.log import Log, get_file_logger

bs64 = Log("base64")
file_logger = get_file_logger("_base64")

JV_TWO = {
    "2_1254": [0, 1, 2, 4, 5, 36, 47, 48, 59, 96, 107],
    "2_9214": [0, 1, 2, 4, 5, 6, 7, 48, 49, 66, 149, 150, 284, 374, 375],
    "2_10232": [0, 1, 2, 5, 6, 7, 8, 46, 65, 66, 199, 270, 328, 329],
    "2_10234": [0, 1, 2, 4, 5, 6, 7, 46, 65, 66, 198, 270, 328, 329],
}

JV_THREE = {
    "3_1021": {
        "uc": [{"s": 0, "n": 1}, {"s": 1, "n": 2}, {"s": 33, "n": 1},
               {"s": 57, "n": 1}, {"s": 111, "n": 1}],
        "avg": 5, "loc": [1, 3, 2, 0, 4],
    },
    "3_2265": {
        "uc": [{"s": 0, "n": 2}, {"s": 1, "n": 3}, {"s": 33, "n": 1},
               {"s": 57, "n": 1}, {"s": 121, "n": 1}],
        "avg": 5, "loc": [3, 1, 0, 4, 2],
    },
    "3_2277": {
        "uc": [{"s": 0, "n": 3}, {"s": 1, "n": 3}, {"s": 32, "n": 2},
               {"s": 50, "n": 1}, {"s": 110, "n": 1}],
        "avg": 5, "loc": [3, 1, 0, 4, 2],
    },
}

DEFAULT_JV_TWO = JV_TWO["2_9214"]
_runtime_crypto_document = None


def _json_loads_maybe(value):
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def set_crypto_document(document):
    """Install one process-local OAuth crypto document for headless clients."""
    global _runtime_crypto_document
    if isinstance(document, bytes):
        document = document.decode("utf-8")
    document = _json_loads_maybe(document)
    if not isinstance(document, dict):
        raise ValueError("crypto document must be a JSON object")
    # Copy through JSON so callers cannot mutate the active context and so the
    # accepted shape is exactly what the file-backed path already supports.
    _runtime_crypto_document = json.loads(json.dumps(document))


def clear_crypto_document():
    """Remove the process-local OAuth crypto document."""
    global _runtime_crypto_document
    _runtime_crypto_document = None


def _normalise_input(data, jv):
    if isinstance(data, dict):
        jv = jv or data.get("jv")
        if "data" in data:
            data = data["data"]
    return data, str(jv or "0")


def _candidate_crypto_paths():
    env_path = os.environ.get("EASY_CIDAREN_CRYPTO_FILE")
    if env_path:
        yield Path(env_path)

    root = Path(__file__).resolve().parent.parent
    cwd = Path.cwd()
    bundle_root = Path(getattr(sys, "_MEIPASS", root))

    for base in (cwd, root, bundle_root):
        yield base / "config" / "crypto.json"
        yield base / "get token" / "fetch_token" / "crypto.json"


def _decode_prefixed_base64(value, prefix):
    if not value:
        return None
    if value.startswith(prefix):
        value = value[1:]
    return base64.b64decode(value)


def _read_crypto_context():
    if _runtime_crypto_document is not None:
        runtime = _decode_crypto_document(_runtime_crypto_document)
        if runtime is not None:
            shared_secret, salt = runtime
            return shared_secret, salt, "process-local OAuth session"

    for path in _candidate_crypto_paths():
        if not path.exists():
            continue

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        decoded = _decode_crypto_document(data)
        if decoded is not None:
            shared_secret, salt = decoded
            return shared_secret, salt, path

    raise RuntimeError(
        "收到 jv=99 加密响应，但未找到可用的 crypto.json。"
        "请用新版“获取token”工具重新获取 token，让它同时生成 crypto.json。"
    )


def _decode_crypto_document(data):
    login_info = (
        data.get("login_info")
        or data.get("CDR_LOGIN_INFO")
        or data.get("loginInfo")
        or data
    )
    login_info = _json_loads_maybe(login_info)
    if not isinstance(login_info, dict):
        return None
    shared_secret = _decode_prefixed_base64(login_info.get("a", ""), "h")
    salt = _decode_prefixed_base64(login_info.get("b", ""), "a")
    if not shared_secret or not salt:
        return None
    return shared_secret, salt


def _decrypt_jv99(payload):
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    except ModuleNotFoundError as exc:
        raise RuntimeError("jv=99 解密需要 cryptography，请先安装 requirements.txt。") from exc

    payload = _json_loads_maybe(payload)
    if isinstance(payload, dict) and payload.get("payload"):
        payload = payload["payload"]
    if not isinstance(payload, dict):
        raise ValueError("jv=99 响应不是有效的加密 payload。")

    iv = payload.get("iv")
    cipher_text = payload.get("cipher_text") or payload.get("cipherText")
    aad = payload.get("aad") or ""
    if not iv or not cipher_text or not aad:
        raise ValueError("jv=99 响应缺少 iv/cipher_text/aad。")

    ucd = aad.split(":")[-1]
    if not ucd:
        raise ValueError("jv=99 响应 aad 缺少会话标识。")

    shared_secret, salt, context_path = _read_crypto_context()
    info = f"vcg-exam-aes:{ucd}".encode("utf-8")
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=info,
    ).derive(shared_secret)

    plain = AESGCM(key).decrypt(
        base64.b64decode(iv),
        base64.b64decode(cipher_text),
        aad.encode("utf-8"),
    )
    text = plain.decode("utf-8")
    file_logger.info(f"jv=99 解密成功，使用密钥文件：{context_path}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _remove_confusion(data, jv):
    if jv in JV_THREE:
        config = JV_THREE[jv]
        cleaned = data
        for rule in config["uc"]:
            start, count = rule["s"], rule["n"]
            cleaned = (cleaned[:start] if start else "") + cleaned[start + count:]
        chunk_size = len(cleaned) // config["avg"]
        if chunk_size == 0:
            raise ValueError(f"jv={jv} 混淆数据长度无效")
        chunks = [
            cleaned[index * chunk_size:(index + 1) * chunk_size]
            for index in range(config["avg"])
        ]
        new_data = "".join(
            chunks[config["loc"].index(index)] for index in range(config["avg"])
        )
        new_data += cleaned[config["avg"] * chunk_size:]
    else:
        char_list = list(data)
        indices = JV_TWO.get(jv, DEFAULT_JV_TWO)
        for index in sorted(indices, reverse=True):
            if 0 <= index < len(char_list):
                del char_list[index]
        new_data = "".join(char_list)
    file_logger.info(f"去除混淆后：{new_data}")
    return new_data


def _decode_base64_payload(data, jv):
    try:
        return base64.b64decode(data.encode("utf-8")).decode("utf-8")
    except Exception:
        new_data = _remove_confusion(data, jv)
        return base64.b64decode(new_data.encode("utf-8")).decode("utf-8", errors="ignore")


def _loads_decoded_json(decoded):
    decoded = decoded.strip()
    if decoded.startswith("{"):
        return json.loads(decoded)

    matches = re.findall(r'{\".*', decoded)
    if not matches:
        raise ValueError(f"解码后未找到 JSON：{decoded[:100]}")

    result = matches[0]
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        if result.startswith("{"):
            result = result[1:]
            result = re.findall(r'{\".*', result)[0]
            return json.loads(result)
        raise


def debase64(data: dict or str, jv: str = "0"):
    """
    解码词达人响应。
    """
    data, jv = _normalise_input(data, jv)
    file_logger.info(f"开始解码jv:{jv},{data}")

    if jv == "99":
        return _decrypt_jv99(data)

    if isinstance(data, (dict, list)):
        return data

    decoded = _decode_base64_payload(data, jv)
    result = _loads_decoded_json(decoded)
    bs64.logger.info(f"解码成功{result}")
    return result


if __name__ == "__main__":
    debase64(
        "EZeJ2uxyJ3b3JkIjoiZG9taW5hdGUiLCJ0b3BpY19jb2RlIoLjoibEZoNWRveHNtTEmlUVmx5SGVIdUxiSmV2WkplU2FsbGlXcHFvbzU3VHhhcVpnNDlxYVdPYmJXdGlqR3FWWmIyK1lHR1JabUp4NvYjI1cmEzR2FhV2hzYjI1cllwREFscE9SalpSbGFXZVRaVzlzWjJsd2NadU5abHlXYUc5dmNIQnNZbWlPYW1obmEydHRiR2Fha0dsbWs1eHZiV3FPYVpNPSIsIm92ZXJfc3RhtdHVzIjoxLCJhbnN3ZXJfcmVzdWx0IjoxLCJjbGVhbl9zdGF0dXMiOjIsImFuc3dlcl9jb3JyZWN0cyI6WzJdfQ=="
    )
