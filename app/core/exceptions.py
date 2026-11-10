class ScrubberBaseException(Exception):
  """Base exception for the application. Never include raw PII in message."""

  def __init__(self, user_message: str, status_code: int = 400) -> None:
    super().__init__(user_message)
    self.user_message = user_message
    self.status_code = status_code


class FileValidationError(ScrubberBaseException):
  """Raised when an uploaded file fails signature, extension, or size validation."""

  def __init__(self, user_message: str) -> None:
    super().__init__(user_message=user_message, status_code=400)


class DocumentExtractionError(ScrubberBaseException):
  """Raised when a supported file is corrupted, empty, or unreadable."""

  def __init__(self, filename: str, reason: str) -> None:
    safe_msg = f"Could not read '{filename}': {reason}"
    super().__init__(user_message=safe_msg, status_code=422)
    self.filename = filename
    self.reason = reason


class PrivacyVerificationFailedError(ScrubberBaseException):
  """Raised when the post-scrubbing security gate detects residual sensitive data."""

  def __init__(self, findings_summary: list[str]) -> None:
    super().__init__(
        user_message=(
            "Privacy verification blocked processing because potential "
            "sensitive identifiers were detected in the output."
        ),
        status_code=422,
    )
    self.findings_summary = findings_summary


class ExternalAIServiceError(ScrubberBaseException):
  """Raised when Groq API fails, times out, or returns an invalid structure."""

  def __init__(
      self,
      user_message: str = (
          "We couldn't generate your spending report right now. "
          "Your saved statements are safe. Please try again."
      ),
  ) -> None:
    super().__init__(user_message=user_message, status_code=502)