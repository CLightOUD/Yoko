class ServiceError(Exception):
    """Base exception for expected business-layer failures."""


class InvalidRequestError(ServiceError):
    pass


class ResourceNotFoundError(ServiceError):
    pass


class ResourceConflictError(ServiceError):
    pass
