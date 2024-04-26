"""This module contains Pydantic `BaseModel`s that describe
responses from Deep Origin's managed data API, and literals that
describe possible values for certain queries.

These models are used both to validate responses and to generate
mock data for testing.
"""

from typing import Literal, Optional, Union

from pydantic import BaseModel

RowType = Literal["row", "database", "workspace"]
FileStatus = Literal["ready", "archived"]
DataType = Literal[
    "integer",
    "str",
    "select",
    "date",
    "text",
    "file",
    "reference",
    "editor",
]


DATAFRAME_ATTRIBUTE_KEYS = {
    "file_ids",
    "id",
    "primary_key",
    "reference_ids",
}


IDFormat = Literal["human-id", "system-id"]

DatabaseReturnType = Literal["dataframe", "dict"]


class DescribeFileResponse(BaseModel):
    """Schema for responses from the
    `DescribeFile` endpoint."""

    id: str
    uri: str
    name: str = "placeholder"
    status: FileStatus
    contentLength: int
    contentType: str

    class Config:
        extra = "forbid"


class ListRowsResponse(BaseModel):
    """Schema for responses from the
    `ListRows` endpoint."""

    id: str
    parentId: Optional[str]
    hid: str
    name: Optional[str] = "placeholder"
    type: RowType

    class Config:
        extra = "forbid"


class FieldItem(BaseModel):
    """Schema for items in the `fields` attribute of responses from
    the `DescribeRow` endpoint."""

    columnId: str
    cellId: str
    validationStatus: str = "valid"
    type: DataType = "text"
    value: Union[str, dict, int] = "placeholder-text"
    systemType: Optional[str] = None

    class Config:
        extra = "forbid"


class ColumnItem(BaseModel):
    """Schema for items in the `cols` attribute of responses from the `DescribeRow` endpoint for a database."""

    id: str
    name: str = "Placeholder Name"
    key: str
    parentId: str = "db-placeholder-1"
    type: DataType = "text"
    dateCreated: str = "2024-04-04T17:03:33.033115"
    cardinality: str = "one"
    canCreate: Optional[bool] = False
    configSelect: Optional[dict] = None

    class Config:
        extra = "forbid"


class DescribeRowResponse(BaseModel):
    """Schema for responses from the `DescribeRow` endpoint. This schema is complex because
    the response schema depends on whether `DescribeRow` is called for a row or database."""

    id: str
    hid: str

    parentId: str
    type: RowType = "row"
    dateCreated: str = "2024-04-04 16:33:58.622469"
    dateUpdated: str = "2024-04-04 16:33:58.622469"
    createdByUserDrn: str = "placeholder"
    rowJsonSchema: dict = {"type": "object", "required": [], "properties": {}}


class DescribeRowResponseRow(DescribeRowResponse):
    """Schema for responses from the `DescribeRow` endpoint for a row.
    This is also the schema for responses from the `DescribeDatabaseRows` endpoint."""

    fields: Optional[list[FieldItem]] = None
    editedByUserDrn: str = "placeholder"
    hidNum: int = 1
    submissionStatus: str = "draft"
    validationStatus: str = "valid"

    class Config:
        extra = "forbid"


class DescribeRowResponseDatabase(DescribeRowResponse):
    """Schema for responses for the `DescribeRow` endpoint for a database."""

    cols: list
    hidPrefix: str
    name: str

    class Config:
        extra = "forbid"
