"""Block the AI endpoint from being pointed at the network it sits on.

The base URL is user-editable on purpose - any OpenAI-compatible server works,
including a local model. But "the user may point it at localhost" is a
deliberate feature, and "anything reachable from this machine" is not. Without
a distinction between the two, the field is a request-forgery primitive:
point it at 169.254.169.254 and the response body carries the cloud instance's
credentials, or at an internal admin port and the error text confirms what is
listening there.

The rules, in order:

  * Only http and https. ``file://`` and ``ftp://`` reach the filesystem.
  * Loopback is always allowed - that is the local-model feature.
  * Link-local is never allowed. 169.254.0.0/16 is the cloud metadata service
    on every major provider and is not something a local model runs on.
  * Private LAN ranges need explicit consent, because running Ollama on
    192.168.1.50:11434 is a normal thing to want and silently breaking it
    would be worse than the risk.
  * Redirects are not followed blindly. A public host that answers 302 with a
    Location of 169.254.169.254 turns an allowed URL into a forbidden request
    without the user changing anything.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

#: Schemes the client will actually speak. Anything else is either a file read
#: or a protocol the rest of this code does not expect.
ALLOWED_SCHEMES = frozenset({"http", "https"})

#: Where the caller has to opt in before a private range is reachable.
ALLOW_PRIVATE_ENV = "GHM_ALLOW_PRIVATE_AI_HOST"


class EndpointBlocked(ValueError):
    """The configured AI endpoint is not one this app will contact."""


def _resolved_addresses(host: str) -> list[ipaddress._BaseAddress]:
    """Every address ``host`` resolves to.

    Checked rather than trusting the literal: ``http://127.0.0.1.nip.io`` and
    any other name that points at a loopback or metadata address would sail
    past a string comparison and be fetched anyway.
    """
    literal = host.strip("[]")
    try:
        return [ipaddress.ip_address(literal)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        return []
    found: list[ipaddress._BaseAddress] = []
    for info in infos:
        try:
            found.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    return found


def _private_allowed() -> bool:
    import os

    return os.environ.get(ALLOW_PRIVATE_ENV, "").strip().lower() in {"1", "true", "yes"}


def check_endpoint(url: str) -> str:
    """Validate an AI base URL, returning it unchanged.

    Raises :class:`EndpointBlocked` with a message meant to be shown to the
    user, because every reason it can fire is something the user can act on.
    """
    text = str(url or "").strip()
    if not text:
        raise EndpointBlocked("No endpoint is configured.")

    try:
        parsed = urlparse(text)
    except ValueError as exc:
        raise EndpointBlocked(f"That is not a usable address: {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise EndpointBlocked(
            f"Only http and https endpoints are supported, not {scheme or 'a bare address'}."
        )

    host = (parsed.hostname or "").strip()
    if not host:
        raise EndpointBlocked("That address has no host in it.")

    addresses = _resolved_addresses(host)
    if not addresses:
        # Unresolvable right now. Not a security decision - a DNS hiccup or a
        # typo - and refusing it would break an endpoint that works offline
        # from a cache. requests will report the real failure.
        return text

    for address in addresses:
        if address.is_loopback:
            continue

        if address.is_link_local:
            # 169.254.169.254 answers with instance credentials on AWS, GCP
            # and Azure. There is no local-model case for it.
            raise EndpointBlocked(
                f"{address} is a link-local address. These are used by cloud "
                "metadata services that hand out instance credentials, so this "
                "app will not contact one."
            )

        if address.is_private or address.is_reserved or address.is_unspecified:
            if _private_allowed():
                continue
            raise EndpointBlocked(
                f"{address} is on a private network. This app only reaches "
                "loopback (127.0.0.1) on its own. If you meant to use a model "
                f"server on your LAN, set {ALLOW_PRIVATE_ENV}=1."
            )

    return text


def redirect_is_allowed(status_code: int, location: str, *, base_url: str) -> bool:
    """Whether a redirect may be followed.

    Redirects are the way an allowed URL reaches a blocked one, so each hop is
    re-checked rather than only the address the user typed.
    """
    if status_code not in {301, 302, 303, 307, 308}:
        return False
    try:
        target = check_endpoint(location)
    except EndpointBlocked:
        return False
    return bool(target)
