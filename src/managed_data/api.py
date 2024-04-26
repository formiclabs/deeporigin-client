"""this module contains high-level functions used to
interact with the data product"""

import os
from typing import Optional, Union

from beartype import beartype
from deeporigin.exceptions import DeepOriginException
from deeporigin.managed_data._api import (
    convert_id_format,
    describe_file,
    describe_row,
    download_file,
    list_database_rows,
    list_rows,
)
from deeporigin.managed_data.client import Client
from deeporigin.managed_data.schema import DatabaseReturnType, IDFormat
from deeporigin.utils import PREFIX


@beartype
def get_tree(
    *,
    include_rows: bool = True,
    client: Optional[Client] = None,
) -> dict:
    """Construct a tree of all workspaces, databases and rows

    Returns a tree that contains all workspaces, databases and
    (optionally) rows. The tree is returned as a dictionary,
    and children of each object are contained in a field
    called `children`.


    Args:
        include_rows: If True, rows are included in the tree.

    Returns:
        A dictionary describing the tree structure of all workspaces
        and databases.

    """

    if include_rows:
        # we need to fetch everything, so use a single call
        objects = list_rows(client=client)
        rows = [obj for obj in objects if obj["type"] == "row"]
        workspaces = [obj for obj in objects if obj["type"] == "workspace"]
        databases = [obj for obj in objects if obj["type"] == "database"]
    else:
        workspaces = list_rows(row_type="workspace", client=client)
        databases = list_rows(row_type="database", client=client)
        objects = workspaces + databases

    for obj in workspaces + databases:
        obj["children"] = []

    root_object = [obj for obj in objects if obj["parentId"] is None]

    # check that there is exactly one root
    if len(root_object) != 1:
        raise DeepOriginException(
            f"Expected there to be exactly one root object. Instead, there were {len(root_object)}"
        )

    tree = root_object[0]

    _add_children(tree, workspaces)
    for workspace in workspaces:
        _add_children(workspace, workspaces + databases)

    if include_rows:
        for database in databases:
            _add_children(database, rows)

    return tree


@beartype
def _add_children(node: dict, objects: list[dict]) -> None:
    """Internal function to add children to a node


    Warning: Internal function
        Do not use this function.

    """
    node["children"] = [obj for obj in objects if obj["parentId"] == node["id"]]


@beartype
def get_cell_data(
    *,
    row_id: str,
    column_name: str,
    client: Optional[Client] = None,
):
    """Extract data from a cell in a database, referenced
    by `row_id` and `column_name`

    Returns the value in a single cell in a database.

    Warning: Caution
        This function internally calls
        [get_row_data][src.managed_data.api.get_row_data],
        so it is not efficient to write a loop to get all values
        of cells from a row. It will be faster to call
        [get_row_data][src.managed_data.api.get_row_data] directly.


    Args:
        row_id: ID (or Human ID) of a row
        column_name: Name of column

    Returns:
        Value of that cell.

    """

    data = get_row_data(row_id, client=client)
    return data[column_name]


@beartype
def download(
    source: str,
    destination: str,
    *,
    include_files: bool = False,
    client: Optional[Client] = None,
) -> None:
    """Download resources from Deep Origin and save to
    local destination

    Download databases, objects and other entities from
    Deep Origin managed data and save to local disk.

    Info: Work in progress
        All features in this function have not been implemented yet.


    Args:
        source: ID (or Human ID) of a resource on Deep Origin
        destination: Path to local directory to save resources
        include_files: if True, download files in database

    """

    if not os.path.isdir(destination):
        raise DeepOriginException(f"{destination} should be a path to a folder.")

    source = source.replace(PREFIX, "")

    # first, need to determine what this is.
    obj = describe_row(source, client=client)
    if obj["type"] == "database":
        download_database(
            obj,
            destination,
            include_files=include_files,
            client=client,
        )
    else:
        raise NotImplementedError(
            "Downloading this type of data object has not been implemented yet"
        )


@beartype
def download_database(
    source: Union[str, dict],
    destination: str = os.getcwd(),
    *,
    include_files: bool = False,
    client: Optional[Client] = None,
) -> None:
    """Download a database and save it to a CSV on local disk

    Download a database from Deep Origin managed data
    and save to local disk as a CSV.

    Args:
        source: ID (or Human ID) of a resource on Deep Origin
        destination: Path to local directory to save resources
        include_files: if True, download files in database

    """

    if not os.path.isdir(destination):
        raise DeepOriginException(f"{destination} should be a path to a folder.")

    if isinstance(source, str):
        source = describe_row(source, client=client)
    elif not {"hid", "id"}.issubset(set(list(source.keys()))):
        raise DeepOriginException(
            f"If `source` is a dictionary, expected it contain the `hid` and `id` keys. These keys were not found. Instead, the keys are: {source.keys()}"
        )

    database_id = source["id"]
    database_hid = source["hid"]
    df = get_dataframe(
        database_id,
        use_file_names=True,
        client=client,
    )

    # now download all files in the database
    if include_files:
        file_ids = df.attrs["file_ids"]

        for file_id in file_ids:
            download_file(file_id, destination, client=client)

    df.to_csv(os.path.join(destination, database_hid + ".csv"))


@beartype
def get_dataframe(
    database_id: str,
    *,
    use_file_names: bool = True,
    reference_format: IDFormat = "human-id",
    return_type: DatabaseReturnType = "dataframe",
    client: Optional[Client] = None,
):
    """Generate a pandas.DataFrame from a database

    Download a database from Deep Origin managed data
    and save to local disk as a CSV.

    Args:
        database_id: ID (or Human ID) of a database on Deep Origin
        use_file_names: If True, refer to files by name rather than file_ID
        reference_format: Refer to rows on Deep Origin using Human IDs or System IDs.
        return_type: Whether to return a pandas.Dataframe or a dictionary
    """

    # figure out the rows
    rows = list_database_rows(database_id, client=client)

    # figure out the column names and ID of the database
    response = describe_row(database_id, client=client)
    assert (
        response["type"] == "database"
    ), f"Expected database_id: {database_id} to resolve to a database, but instead, it resolved to a {response['type']}"

    columns = response["cols"]
    database_id = response["id"]
    row_id = response["hidPrefix"] + "-id"

    # make a dictionary with all data in the database
    data = dict()
    data["Validation Status"] = []
    data[row_id] = []

    # keep track of all files and references in this database
    file_ids = []
    reference_ids = []

    for column in columns:
        data[column["id"]] = []

    for row in rows:
        data[row_id].append(row["hid"])
        data["Validation Status"].append(row["validationStatus"])

        fields = row["fields"]

        for column in columns:
            value = _parse_column_value(
                column=column,
                fields=fields,
                file_ids=file_ids,
                reference_ids=reference_ids,
                use_file_names=use_file_names,
                reference_format=reference_format,
            )
            if column["cardinality"] == "many":
                data[column["id"]].append(value)
            else:
                data[column["id"]].extend(value)

    if return_type == "dataframe":
        # make the dataframe

        # this import is here because we don't want to
        # import pandas unless we actually use this function
        import pandas as pd

        df = pd.DataFrame(data)
        df.attrs["file_ids"] = list(set(file_ids))
        df.attrs["reference_ids"] = list(set(reference_ids))
        df.attrs["id"] = database_id
        df.attrs["primary_key"] = row_id

        return _type_and_cleanup_dataframe(df, columns)

    else:
        # rename keys
        column_mapper = dict()
        for column in columns:
            column_mapper[column["id"]] = column["name"]
        renamed_data = data.copy()
        for key in column_mapper.keys():
            new_key = column_mapper[key]
            renamed_data[new_key] = data[key]
            renamed_data.pop(key, None)
        return renamed_data


@beartype
def _parse_column_value(
    *,
    column: dict,
    fields: list[dict],
    file_ids: list,
    reference_ids: list,
    use_file_names: bool,
    reference_format: IDFormat,
):
    """Internal function parse column values

    Warning: Internal function
        Do not use this function.
    """

    value = [field["value"] for field in fields if field["columnId"] == column["id"]]

    # special treatment for some column types
    if column["type"] == "select" and len(value) == 1:
        value = value[0]["selectedOptions"]
    elif column["type"] == "file" and len(value) == 1:
        value = value[0]["fileIds"]

        file_ids.extend(value)

        if use_file_names:
            value = [describe_file(file_id)["name"] for file_id in value]
    elif column["type"] == "reference" and len(value) == 1:
        value = value[0]["rowIds"]
        reference_ids.extend(value)

        if reference_format == "human-id":
            value = convert_id_format(ids=value)
            value = [thing["hid"] for thing in value]

    # if there is no item
    if len(value) == 0:
        value = [None]

    return value


@beartype
def _type_and_cleanup_dataframe(
    df,  # pd.Dataframe, not typed to avoid pandas import
    columns: list[dict],
):
    """Internal function to type and clean a pandas dataframe

    Warning: Internal function
        Do not use this function.
    """

    # this import is here because we don't want to
    # import pandas unless we actually use this function
    import pandas as pd

    column_mapper = dict()
    for column in columns:
        column_mapper[column["id"]] = column["name"]

    # special treatment of Select columns
    for column in columns:
        col_id = column["id"]

        if column["type"] == "select" and column["cardinality"] == "one":
            categories = column["configSelect"]["options"]
            df[col_id] = pd.Categorical(df[col_id], categories=categories)

    # rename columns
    df = df.rename(columns=column_mapper)

    # wipe metadata from columns
    for column in df.columns:
        df[column].attrs = dict()

    # attach metadata to columns
    for column in columns:
        df[column["name"]].attrs = column

    # add a type to Validation Status because this column
    # doesn't actually exist in the database
    df["Validation Status"].attrs = dict(type="Validation Status")
    return df


@beartype
def get_columns(
    row_id: str,
    *,
    client: Optional[Client] = None,
) -> list[dict]:
    """Get column information for a row or a database.

    If row_id is a database, then column metadata and names
    are returned. If row_id is a row, then a dictionary of
    Human IDs and values are returned

    Args:
        row_id: ID (or Human ID) of a row or database on Deep Origin
    """

    response = describe_row(row_id, fields=True, client=client)

    assert response["type"] in [
        "row",
        "database",
    ], "Expected row_id to resolve to a row or a database"

    if response["type"] == "database":
        # return cols info
        return response["cols"]
    else:
        return response["fields"]


@beartype
def get_row_data(
    row_id: str,
    *,
    use_column_keys: bool = False,
    client: Optional[Client] = None,
) -> dict:
    """Get data in a row

    Read data from a row, and return as a dictionary, where
    keys are column names (or keys), and values are values of those
    cells.

    Args:
        row_id: ID (or Human ID) of a row or database on Deep Origin
        use_column_keys: if True, keys of dictionary are column keys

    Raises:
        DeepOriginException: If row_id is not a row
    """

    response = describe_row(row_id, fields=True, client=client)

    if response["type"] != "row":
        raise DeepOriginException(
            f"Expected `row_id` to resolve to a row, instead, it resolves to a `{response['type']}`"
        )

    # ask parent for column names
    parent_response = describe_row(response["parentId"], client=client)

    if parent_response["type"] != "database":
        raise DeepOriginException(
            f"Expected parent of `{row_id}` to resolve to a database, instead, it resolves to a `{parent_response['type']}`"
        )

    # make a dictionary from column IDs to column names
    column_name_mapper = dict()
    column_cardinality_mapper = dict()
    for col in parent_response["cols"]:
        if use_column_keys:
            column_name_mapper[col["id"]] = col["key"]
        else:
            column_name_mapper[col["id"]] = col["name"]
        column_cardinality_mapper[col["id"]] = col["cardinality"]

    # now use this to construct the required dictionary
    row_data = dict()
    for field in response["fields"]:
        column_id = field["columnId"]

        if "value" not in field:
            continue

        value = field["value"]
        if isinstance(value, dict):
            if "selectedOptions" in value.keys():
                value = value["selectedOptions"]
            elif "fileIds" in value.keys():
                value = value["fileIds"]

        if column_cardinality_mapper[column_id] == "one" and isinstance(value, list):
            value = value[0]

        row_data[column_name_mapper[column_id]] = value

    return row_data


@beartype
def merge_databases(dfs: list):
    """Merge dataframes into a single dataframes

    Given a list of dataframes derived from Deep Origin databases,
    merge them into a single dataframe, resolving cross-references
    across databases.

    Info: Work in progress
        All features in this function have not been implemented yet.


    Args:
        dfs: List of pandas.DataFrames


    """

    import pandas as pd

    for df in dfs:
        assert isinstance(df, pd.DataFrame), "Expected a list of dataframes to merge"

    assert len(dfs) == 2, "For now we only support merging 2 databases"

    # make a cross reference mapper that converts
    # system IDs to column names
    cross_reference_mapper = dict()

    for df in dfs:
        cross_reference_mapper[df.attrs["id"]] = df.attrs["primary_key"]

    # rename columns that contain cross-references (foreign keys)
    # so that the pandas merge works correctly

    for df in dfs:
        column_mapper = dict()

        for column in df.columns:
            attrs = df[column].attrs

            if "referenceDatabaseRowId" in attrs.keys():
                column_mapper[column] = cross_reference_mapper[
                    attrs["referenceDatabaseRowId"]
                ]

        df.rename(columns=column_mapper, inplace=True)

    # for now we only support merging 2 DBs
    return dfs[0].merge(dfs[1], how="outer")
