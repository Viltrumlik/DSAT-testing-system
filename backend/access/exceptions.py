"""Authorization contract errors (programmer mistakes, not end-user auth failures)."""


class SubjectContractViolation(ValueError):
    """
    Raised when code passes the wrong *kind* of subject string (platform vs domain)
    or an unknown platform label into an API that requires the other vocabulary.

    End-user denial for valid types remains a boolean ``False`` from ``authorize()``;
    this exception exists so misuse fails loudly in CI and during development.
    """


class AccessConsistencyDrift(SubjectContractViolation):
    """Raised when a queryset filter disagrees with :func:`can_view_tests` (regression guard)."""
