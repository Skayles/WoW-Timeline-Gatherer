"""WCL errors. ``str(error)`` is a French message meant to be shown to the user."""


class WclError(Exception):
    """Base class for every Warcraft Logs related failure."""


class MissingCredentialsError(WclError):
    pass


class AuthenticationError(WclError):
    pass


class ReportNotFoundError(WclError):
    pass


class PrivateReportError(WclError):
    pass


class RateLimitError(WclError):
    pass


class WclNetworkError(WclError):
    pass


class WclApiError(WclError):
    """Any other HTTP or GraphQL error returned by WCL."""
