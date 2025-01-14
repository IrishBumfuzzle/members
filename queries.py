import csv
import io
from typing import List

import strawberry
from fastapi.encoders import jsonable_encoder

from db import membersdb
from models import Member
from utils import getClubDetails, getUser, getClubs, getUsersInBulk

# import all models and types
from otypes import (
    Info,
    MemberType,
    SimpleClubInput,
    SimpleMemberInput,
    MemberInputDataReportDetails,
    MemberCSVResponse,
)

"""
Member Queries
"""


@strawberry.field
def member(memberInput: SimpleMemberInput, info: Info) -> MemberType:
    """
    Description:
        Returns member details for a specific club
    Scope: CC & Specific Club
    Return Type: MemberType
    Input: SimpleMemberInput (cid, uid)
    """
    user = info.context.user
    if user is None:
        raise Exception("Not Authenticated")

    uid = user["uid"]
    member_input = jsonable_encoder(memberInput)

    if (member_input["cid"] != uid or user["role"] != "club") and user["role"] != "cc":
        raise Exception("Not Authenticated to access this API")

    member = membersdb.find_one(
        {
            "$and": [
                {"cid": member_input["cid"]},
                {"uid": member_input["uid"]},
            ]
        },
        {"_id": 0},
    )
    if member is None:
        raise Exception("No such Record")

    return MemberType.from_pydantic(Member.model_validate(member))


@strawberry.field
def memberRoles(uid: str, info: Info) -> List[MemberType]:
    """
    Description:
        Returns member roles from each club
    Scope: CC & Specific Club
    Return Type: uid (str)
    Input: SimpleMemberInput (cid, uid, roles)
    """
    user = info.context.user
    if user is None:
        role = "public"
    else:
        role = user["role"]

    results = membersdb.find({"uid": uid}, {"_id": 0})

    if not results:
        raise Exception("No Member Result/s Found")

    members = []
    for result in results:
        roles = result["roles"]
        roles_result = []

        for i in roles:
            if i["deleted"] is True:
                continue
            if role != "cc":
                if i["approved"] is False:
                    continue
            roles_result.append(i)

        if len(roles_result) > 0:
            result["roles"] = roles_result
            members.append(MemberType.from_pydantic(Member.model_validate(result)))

    return members


@strawberry.field
def members(clubInput: SimpleClubInput, info: Info) -> List[MemberType]:
    """
    Description:
        For CC:
            Returns all the non-deleted members.
        For Specific Club:
            Returns all the non-deleted members of that club.
        For Public:
            Returns all the non-deleted and approved members.
    Scope: CC + Club (For All Members), Public (For Approved Members)
    Return Type: List[MemberType]
    Input: SimpleClubInput (cid)
    """
    user = info.context.user
    if user is None:
        role = "public"
    else:
        role = user["role"]

    club_input = jsonable_encoder(clubInput)

    if role not in ["cc"] or club_input["cid"] != "clubs":
        results = membersdb.find({"cid": club_input["cid"]}, {"_id": 0})
    else:
        results = membersdb.find({}, {"_id": 0})

    if results:
        members = []
        for result in results:
            roles = result["roles"]
            roles_result = []

            for i in roles:
                if i["deleted"] is True:
                    continue
                if not (
                    role in ["cc"]
                    or (role in ["club"] and user["uid"] == club_input["cid"])
                ):
                    if i["approved"] is False:
                        continue
                roles_result.append(i)

            if len(roles_result) > 0:
                result["roles"] = roles_result
                members.append(MemberType.from_pydantic(Member.model_validate(result)))

        return members

    else:
        raise Exception("No Member Result/s Found")


@strawberry.field
def currentMembers(clubInput: SimpleClubInput, info: Info) -> List[MemberType]:
    """
    Description:
        For Everyone:
            Returns all the current non-deleted and approved members of the given clubid.

    Scope: Anyone (Non-Admin Function)
    Return Type: List[MemberType]
    Input: SimpleClubInput (cid)
    """  # noqa: E501
    user = info.context.user
    if user is None:
        role = "public"
    else:
        role = user["role"]

    club_input = jsonable_encoder(clubInput)

    if club_input["cid"] == "clubs":
        if role != "cc":
            raise Exception("Not Authenticated")

        results = membersdb.find({}, {"_id": 0})
    else:
        results = membersdb.find({"cid": club_input["cid"]}, {"_id": 0})

    if results:
        members = []
        for result in results:
            roles = result["roles"]
            roles_result = []

            for i in roles:
                if i["deleted"] is True or int(i["end_year"]) is not None:
                    continue
                if i["approved"] is False:
                    continue
                roles_result.append(i)

            if len(roles_result) > 0:
                result["roles"] = roles_result
                members.append(MemberType.from_pydantic(Member.model_validate(result)))

        return members
    else:
        raise Exception("No Member Result/s Found")


@strawberry.field
def pendingMembers(info: Info) -> List[MemberType]:
    """
    Description: Returns all the non-deleted and non-approved members.
    Scope: CC
    Return Type: List[MemberType]
    Input: None
    """
    user = info.context.user
    if user is None or user["role"] not in ["cc"]:
        raise Exception("Not Authenticated")

    results = membersdb.find({}, {"_id": 0})

    if results:
        members = []
        for result in results:
            roles = result["roles"]
            roles_result = []

            for i in roles:
                if i["deleted"] or i["approved"] or i["rejected"]:
                    continue
                roles_result.append(i)

            if len(roles_result) > 0:
                result["roles"] = roles_result
                members.append(MemberType.from_pydantic(Member.model_validate(result)))

        return members
    else:
        raise Exception("No Member Result/s Found")


@strawberry.field
def downloadMembersData(
    details: MemberInputDataReportDetails, info: Info
) -> MemberCSVResponse:
    user = info.context.user
    if user is None:
        raise Exception("You do not have permission to access this resource.")

    if details.clubid != "allclubs":
        clubList = [details.clubid]
    else:
        allClubs = getClubs(info.context.cookies)
        clubList = [club["cid"] for club in allClubs]
        details.typeMembers = "current"

    results = membersdb.find({"cid": {"$in": clubList}}, {"_id": 0})

    allMembers = []
    userDetailsList = dict()
    userIds = []
    for result in results:
        roles = result["roles"]
        roles_result = []
        currentMember = False
        withinTimeframe = False

        for i in roles:
            if i["deleted"] is True:
                continue
            if details.typeMembers == "current" and i["end_year"] is None:
                currentMember = True
            elif details.typeMembers == "past" and (
                (
                    details.dateRoles[1]
                    >= (2024 if i["end_year"] is None else int(i["end_year"]))
                    and details.dateRoles[0]
                    <= (2024 if i["end_year"] is None else int(i["end_year"]))
                )
                or (
                    details.dateRoles[1] >= int(i["start_year"])
                    and details.dateRoles[0] <= int(i["start_year"])
                )
            ):
                withinTimeframe = True

            roles_result.append(i)

        if len(roles_result) > 0:
            append = False
            result["roles"] = roles_result
            if details.typeMembers == "current" and currentMember == True:
                append = True
            elif details.typeMembers == "past" and withinTimeframe == True:
                append = True
            elif details.typeMembers == "all":
                append = True

            if append:
                # Last possible moment to filter by batch since getUser is expensive
                if details.batchFiltering != "all":
                    userDetails = getUser(result["uid"], info.context.cookies)
                    if userDetails is None:
                        continue
                    if userDetails["batch"] != details.batchFiltering:
                        continue
                    userDetailsList[result["uid"]] = userDetails
                allMembers.append(result)
                userIds.append(result["uid"])
    if details.batchFiltering == "all":
        userDetailsList = getUsersInBulk(userIds, info.context.cookies)

    headerMapping = {
        "clubid": "Club Name",
        "uid": "Name",
        "rollno": "Roll No",
        "batch": "Batch",
        "email": "Email",
        "partofclub": "Is Currently Part of Club",
        "roles": "Roles",
        "poc": "Is POC",
    }

    # Prepare CSV content
    csvOutput = io.StringIO()
    fieldnames = [headerMapping.get(field.lower(), field) for field in details.fields]
    csv_writer = csv.DictWriter(csvOutput, fieldnames=fieldnames)
    csv_writer.writeheader()

    # So that we don't have to query the club name for each member
    clubNames = dict()

    for member in allMembers:
        memberData = {}
        if userDetailsList.get(member["uid"]) is None:
            userDetails = getUser(member["uid"], info.context.cookies)
        else:
            userDetails = userDetailsList.get(member["uid"])
        if userDetails is None:
            continue
        if clubNames.get(member["cid"]) is None:
            clubNames[member["cid"]] = getClubDetails(
                member["cid"], info.context.cookies
            )["name"]

        clubName = clubNames.get(member["cid"])

        for field in details.fields:
            value = ""
            mappedField = headerMapping.get(field.lower())
            if field == "clubid":
                value = clubName
            elif field == "uid":
                value = userDetails["firstName"] + " " + userDetails["lastName"]
            elif field == "rollno":
                value = userDetails["rollno"]
            elif field == "batch":
                value = userDetails["batch"]
            elif field == "email":
                value = userDetails["email"]
            elif field == "partofclub":
                value = "No"
                for role in member["roles"]:
                    if role["end_year"] is None:
                        value = "Yes"
                        break
            elif field == "roles":
                listOfRoles = []
                for i in member["roles"]:
                    roleFormatting = [
                        i["name"],
                        int(i["start_year"]),
                        int(i["end_year"]) if i["end_year"] is not None else None,
                    ]
                    if details.typeRoles == "all":
                        listOfRoles.append(roleFormatting)
                    elif details.typeRoles == "current":
                        if roleFormatting[2] == None:
                            listOfRoles.append(roleFormatting)
                value = str(listOfRoles)
            elif field == "poc":
                value = "Yes" if member["poc"] == True else "No"

            memberData[mappedField] = value
        csv_writer.writerow(memberData)

    csv_content = csvOutput.getvalue()
    csvOutput.close()

    return MemberCSVResponse(
        csvFile=csv_content,
        successMessage="CSV file generated successfully",
        errorMessage="",
    )


# register all queries
queries = [
    member,
    memberRoles,
    members,
    currentMembers,
    pendingMembers,
    downloadMembersData,
]
