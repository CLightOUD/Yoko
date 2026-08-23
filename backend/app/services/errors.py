class ServiceError(Exception):
    """Base exception for expected business-layer failures."""


class AuthenticationRequiredError(ServiceError):
    pass


class AuthenticationUnavailableError(ServiceError):
    pass


class InvalidCredentialsError(ServiceError):
    pass


class UsernameAlreadyExistsError(ServiceError):
    pass


class TooManyAttemptsError(ServiceError):
    pass


class InvalidRequestError(ServiceError):
    pass


class ResourceNotFoundError(ServiceError):
    pass


class ResourceConflictError(ServiceError):
    pass


class ModelUnavailableError(ServiceError):
    pass


class ToolExecutionError(ServiceError):
    pass


class DatabaseUnavailableError(ServiceError):
    pass
