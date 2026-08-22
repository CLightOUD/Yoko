class ServiceError(Exception):
    """Base exception for expected business-layer failures."""


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
