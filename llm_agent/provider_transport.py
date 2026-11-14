"""Bounded authenticated HTTP transport shared by current LLM and OAG adapters."""
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirect disabled for authenticated request", headers, fp)


def transport(request):
    return urllib.request.build_opener(NoRedirect()).open(request, timeout=40)
