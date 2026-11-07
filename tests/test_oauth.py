import base64
import hashlib
import json as jsonlib
import unittest
from urllib.parse import parse_qs, unquote, urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from api.oauth import LOGIN_AAD, LOGIN_HKDF_INFO, begin_authorization, exchange_callback, parse_callback


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def raise_for_status(self):
        return None

    def json(self):
        return self.value


class FakeSession:
    def __init__(self):
        self.shared_secret = None
        self.salt = b"synthetic-oauth-salt"

    def post(self, _url, *, json, **_kwargs):
        body = json
        client_public = serialization.load_der_public_key(base64.b64decode(body["cpub_k"]))
        server_private = ec.generate_private_key(ec.SECP256R1())
        self.shared_secret = server_private.exchange(ec.ECDH(), client_public)
        server_der = server_private.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=self.salt, info=LOGIN_HKDF_INFO,
        ).derive(self.shared_secret)
        iv = bytes(range(12))
        ciphertext = AESGCM(key).encrypt(
            iv, jsonlib.dumps({"token": "synthetic-token"}).encode(), LOGIN_AAD,
        )
        return FakeResponse({"code": 1, "data": {
            "handshake_required": False,
            "encrypted": True,
            "handshake": {
                "version": "v1",
                "spub_k": base64.b64encode(server_der).decode(),
                "salt": base64.b64encode(self.salt).decode(),
            },
            "payload": {
                "version": "v1",
                "aad": LOGIN_AAD.decode(),
                "iv": base64.b64encode(iv).decode(),
                "cipher_text": base64.b64encode(ciphertext).decode(),
            },
        }})

    def get(self, _url, **_kwargs):
        return FakeResponse({"code": 1, "data": {"user_info": {}}})


class OAuthTest(unittest.TestCase):
    def test_authorization_and_callback_binding(self):
        authorization = begin_authorization()
        values = parse_qs(urlsplit(authorization.authorization_url).query)
        state = values["state"][0]
        marker = parse_qs(urlsplit(unquote(values["redirect_uri"][0])).query)["authorize"][0]
        callback = f"https://app.vocabgo.com/student/?authorize={marker}&code=synthetic-code&state={state}"
        self.assertEqual(
            parse_callback(callback, authorization.state_digest, authorization.marker_digest),
            "synthetic-code",
        )

    def test_callback_rejects_wrong_origin_and_binding(self):
        state = base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode()
        marker = "x" + bytes(range(16)).hex()
        state_digest = hashlib.sha256(b"asterism:cidaren:oauth-state:v1\0" + state.encode()).hexdigest()
        marker_digest = hashlib.sha256(b"asterism:cidaren:authorize-marker:v1\0" + marker.encode()).hexdigest()
        callback = f"https://evil.example/student/?authorize={marker}&code=code&state={state}"
        with self.assertRaises(RuntimeError):
            parse_callback(callback, state_digest, marker_digest)

    def test_callback_rejects_malformed_port(self):
        with self.assertRaises(RuntimeError):
            parse_callback("https://app.vocabgo.com:bad/student/?code=x", "", "")

    def test_full_jv99_response_uses_embedded_version(self):
        from decryptencrypt.debase64 import debase64, set_crypto_document, clear_crypto_document
        secret, salt, iv = bytes(range(32)), b"synthetic-salt", bytes(range(12))
        aad = "vcg-exam:test-account"
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt,
                   info=b"vcg-exam-aes:test-account").derive(secret)
        encrypted = AESGCM(key).encrypt(iv, b'{"ok": true}', aad.encode())
        set_crypto_document({"login_info": {
            "a": "h" + base64.b64encode(secret).decode(),
            "b": "a" + base64.b64encode(salt).decode(),
        }})
        try:
            self.assertEqual(debase64({"jv": 99, "data": {
                "iv": base64.b64encode(iv).decode(),
                "cipher_text": base64.b64encode(encrypted).decode(), "aad": aad,
            }}), {"ok": True})
        finally:
            clear_crypto_document()

    def test_exchange_decrypts_token_and_returns_jv99_context(self):
        authorization = begin_authorization()
        values = parse_qs(urlsplit(authorization.authorization_url).query)
        state = values["state"][0]
        marker = parse_qs(urlsplit(unquote(values["redirect_uri"][0])).query)["authorize"][0]
        callback = f"https://app.vocabgo.com/student/?authorize={marker}&code=synthetic-code&state={state}"
        client = FakeSession()
        result = exchange_callback(
            callback,
            authorization.state_digest,
            authorization.marker_digest,
            session=client,
        )
        self.assertEqual(result.token, "synthetic-token")
        self.assertEqual(
            base64.b64decode(result.crypto_document["login_info"]["a"][1:]),
            client.shared_secret,
        )


if __name__ == "__main__":
    unittest.main()
