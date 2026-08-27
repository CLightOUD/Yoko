from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.app.api.dependencies import get_current_user, require_trusted_origin
from backend.app.api.errors import error_responses
from backend.app.schemas import (
    PushConfigResponse,
    PushSubscriptionBody,
    PushSubscriptionDeleteBody,
    PushSubscriptionDeleteResponse,
    PushSubscriptionResponse,
    UserView,
)
from backend.app.services.push_delivery_service import PushDeliveryService


router = APIRouter(prefix="/api/push", tags=["push"])
CurrentUserDependency = Annotated[UserView, Depends(get_current_user)]


def get_push_delivery_service(request: Request) -> PushDeliveryService:
    return request.app.state.push_delivery_service


PushServiceDependency = Annotated[
    PushDeliveryService,
    Depends(get_push_delivery_service),
]


@router.get(
    "/config",
    response_model=PushConfigResponse,
    responses=error_responses(401, 500),
)
def get_push_config(
    service: PushServiceDependency,
    current_user: CurrentUserDependency,
) -> PushConfigResponse:
    del current_user
    return service.config()


@router.post(
    "/subscriptions",
    response_model=PushSubscriptionResponse,
    responses=error_responses(401, 403, 422, 500),
    dependencies=[Depends(require_trusted_origin)],
)
def subscribe_push(
    request: PushSubscriptionBody,
    service: PushServiceDependency,
    current_user: CurrentUserDependency,
) -> PushSubscriptionResponse:
    return service.subscribe(user_id=str(current_user.id), request=request)


@router.delete(
    "/subscriptions",
    response_model=PushSubscriptionDeleteResponse,
    responses=error_responses(401, 403, 422, 500),
    dependencies=[Depends(require_trusted_origin)],
)
def unsubscribe_push(
    request: PushSubscriptionDeleteBody,
    service: PushServiceDependency,
    current_user: CurrentUserDependency,
) -> PushSubscriptionDeleteResponse:
    return service.unsubscribe(
        user_id=str(current_user.id),
        endpoint=request.endpoint,
    )
