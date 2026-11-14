"""Authenticated adapters must not forward credentials through redirects."""
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock, patch

from backend import oag
from llm_agent import provider_transport


class ProviderTransportTests(unittest.TestCase):
    def test_redirect_is_blocked_for_any_authenticated_destination(self):
        request = urllib.request.Request('https://provider.invalid/chat',
                                         headers={'Authorization': 'Bearer test-only'})
        with self.assertRaises(urllib.error.HTTPError) as error:
            provider_transport.NoRedirect().redirect_request(
                request, None, 302, 'Found', {}, 'https://elsewhere.invalid/chat')
        self.assertEqual(error.exception.code, 302)
        self.assertIn('Redirect disabled', str(error.exception))
        self.assertIs(oag.NoRedirect, provider_transport.NoRedirect)

    def test_transport_has_bounded_timeout_and_no_redirect_handler(self):
        opener = Mock()
        request = urllib.request.Request('https://provider.invalid/chat')
        with patch.object(urllib.request, 'build_opener', return_value=opener) as factory:
            result = provider_transport.transport(request)
        self.assertIsInstance(factory.call_args.args[0], provider_transport.NoRedirect)
        opener.open.assert_called_once_with(request, timeout=40)
        self.assertIs(result, opener.open.return_value)


if __name__ == '__main__':
    unittest.main()
