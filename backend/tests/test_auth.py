from unittest import TestCase

from fastapi import HTTPException

from app.auth import create_access_token, create_refresh_token, decode_access_token, hash_password, verify_password, decode_signed_token


class AuthTests(TestCase):
    def test_hash_password_uses_scrypt_and_verifies(self) -> None:
        encoded = hash_password("super-secret-password")
        self.assertTrue(encoded.startswith("scrypt$"))
        self.assertTrue(verify_password("super-secret-password", encoded))
        self.assertFalse(verify_password("wrong-password", encoded))

    def test_access_token_roundtrip(self) -> None:
        token = create_access_token({"sub": "user-1", "email": "demo@example.com", "role": "user"})
        payload = decode_access_token(token)
        self.assertEqual(payload["sub"], "user-1")
        self.assertEqual(payload["typ"], "access")

    def test_refresh_token_rejected_as_access_token(self) -> None:
        token = create_refresh_token({"sub": "user-1"})
        with self.assertRaises(HTTPException):
            decode_access_token(token)
        payload = decode_signed_token(token, expected_type="refresh")
        self.assertEqual(payload["typ"], "refresh")
