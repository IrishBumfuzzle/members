import json
from functools import cached_property
from typing import Dict, Optional, Union, List

import strawberry
from strawberry.fastapi import BaseContext
from strawberry.types import Info as _Info
from strawberry.types.info import RootValueType

from models import Member, PyObjectId, Roles


# custom context class
class Context(BaseContext):
    @cached_property
    def user(self) -> Union[Dict, None]:
        if not self.request:
            return None

        user = json.loads(self.request.headers.get("user", "{}"))
        return user

    @cached_property
    def cookies(self) -> Union[Dict, None]:
        if not self.request:
            return None

        cookies = json.loads(self.request.headers.get("cookies", "{}"))
        return cookies


# custom info type
Info = _Info[Context, RootValueType]

# serialize PyObjectId as a scalar type
PyObjectIdType = strawberry.scalar(
    PyObjectId, serialize=str, parse_value=lambda v: PyObjectId(v)
)


# TYPES
@strawberry.experimental.pydantic.type(model=Roles, all_fields=True)
class RolesType:
    pass


@strawberry.experimental.pydantic.type(
    model=Member,
    fields=[
        "id",
        "cid",
        "uid",
        "roles",
        "poc",
        "creation_time",
        "last_edited_time",
    ],
)
class MemberType:
    pass


# INPUTS
@strawberry.experimental.pydantic.input(
    model=Roles, fields=["name", "start_year", "end_year"]
)
class RolesInput:
    pass


@strawberry.experimental.pydantic.input(
    model=Member, fields=["cid", "uid", "roles"]
)
class FullMemberInput:
    poc: Optional[bool] = strawberry.UNSET


@strawberry.input
class SimpleMemberInput:
    cid: str
    uid: str
    rid: Optional[str]


@strawberry.input
class SimpleClubInput:
    cid: str


@strawberry.input
class MemberInputDataReportDetails:
    clubid: str | None
    fields: List[str]
    typeMembers: str
    typeRoles: str | None
    batchFiltering: str
    dateRoles: List[int] | None


@strawberry.type
class MemberCSVResponse:
    csvFile: str
    successMessage: str
    errorMessage: str
