import unittest

from backend.gateway.errors import (
    GatewayAuthenticationError,
    GatewayConnectionError,
    GatewayConfigurationError,
    GatewayError,
    GatewayModelAliasError,
    GatewayProviderUnavailableError,
    GatewayRequestRejectedError,
    GatewayResponseError,
    GatewayTimeoutError,
)


class GatewayErrorTests(unittest.TestCase):
    def test_gateway_error_preserves_message_and_context(self) -> None:
        error = GatewayError(
            "provider unavailable",
            alias="local_chat",
            provider="ollama",
        )

        self.assertEqual(str(error), "provider unavailable")
        self.assertEqual(
            error.to_log_context(),
            {"alias": "local_chat", "provider": "ollama"},
        )

    def test_gateway_error_omits_empty_context(self) -> None:
        error = GatewayError("unsafe request")

        self.assertEqual(error.to_log_context(), {})

    def test_domain_errors_share_base_type(self) -> None:
        for error_type in (
            GatewayConfigurationError,
            GatewayConnectionError,
            GatewayAuthenticationError,
            GatewayModelAliasError,
            GatewayProviderUnavailableError,
            GatewayRequestRejectedError,
            GatewayResponseError,
            GatewayTimeoutError,
        ):
            with self.subTest(error_type=error_type):
                self.assertIsInstance(error_type("failure"), GatewayError)


if __name__ == "__main__":
    unittest.main()
