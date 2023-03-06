""" This Cloud Function leverages the Looker Python SDK to automate Looker content cleanup.

It accomplishes the following tasks:
1. Get unused content and deleted content data from a Looker System Activity query in JSON.
2. Archive (soft delete) dashboards and Looks which were last accessed more than 90 days ago.
3. Permanently (hard) delete dashboards and Looks which have been archived for more than 90 days.
4. Send an email notification using Looker's scheduler of all the content that was archived & permanently deleted.

Search `todo` to:
- Update DAYS_BEFORE_SOFT_DELETE (# of days content is unused before archival) and DAYS_BEFORE_HARD_DELETE (# of days in trash before permanently deletion).
- Update NOTIFICATION_EMAIL_ADDRESS (email address for content deletion notification).
- Toggle dry run of automation off/on.

Last modified: March 2023
"""

import looker_sdk
from looker_sdk import models40
import json
from datetime import datetime

sdk = looker_sdk.init40()

# todo: update to desired configuration
DAYS_BEFORE_SOFT_DELETE = 90
DAYS_BEFORE_HARD_DELETE = 90
NOTIFICATION_EMAIL_ADDRESS = "email@address.com"


def main(request):
    """ Run the main function.
    """
    # Run a System Activity query to get unused content in past 90 days, archive (soft delete) the content, then send an email with a list of the content.
    unused_content_query_id = get_unused_content_query_id(
        DAYS_BEFORE_SOFT_DELETE)
    unused_content = get_unused_content(unused_content_query_id)
    unused_dashboard_ids = get_dashboard_ids(unused_content)
    unused_look_ids = get_look_ids(unused_content)

    for dashboard_id in unused_dashboard_ids:
        soft_delete_dashboard(dashboard_id)

    for look_id in unused_look_ids:
        soft_delete_look(look_id)

    send_content_notification(
        unused_content_query_id,
        "soft",
        NOTIFICATION_EMAIL_ADDRESS
    )

    # Run a System Activity query to get content deleted 90+ days ago, permenantly (hard) delete the content, then send an email with a list of the content.
    deleted_content_query_id = get_deleted_content_query_id(
        DAYS_BEFORE_HARD_DELETE)
    deleted_content = get_deleted_content(deleted_content_query_id)
    deleted_dashboard_ids = get_dashboard_ids(deleted_content)
    deleted_look_ids = get_look_ids(deleted_content)

    for dashboard_id in deleted_dashboard_ids:
        hard_delete_dashboard(dashboard_id)

    for look_id in deleted_look_ids:
        hard_delete_look(look_id)

    send_content_notification(
        deleted_content_query_id,
        "hard",
        NOTIFICATION_EMAIL_ADDRESS
    )

    return "Successfully ran soft delete and hard delete content automation."


def get_unused_content_query_id(days: int):
    """ Get the query ID for a System Activity query which returns all content that hasn't been used in at least 90 days. 

    Args:
      days (int): The number of days a content should be unused for before soft-deleting it.

    Returns:
      A re-useable query ID that can be used to run the query & send a schedule with the query's results.
    """
    unused_content_query = models40.WriteQuery(
        model="system__activity",
        view="content_usage",
        fields=[
            "dashboard.id",
            "look.id",
            "content_usage.content_title",
            "content_usage.content_type",
            "content_usage.last_accessed_date"
        ],
        pivots=None,
        fill_fields=None,
        filters={
            "content_usage.days_since_last_accessed": f">{days}",
            "content_usage.content_type": "dashboard,look",
            "_dashboard_linked_looks.is_used_on_dashboard": "No",
            "look.public": "No"
        },
        filter_expression="if(is_null(${dashboard.deleted_date}) = no OR is_null(${look.deleted_date}) = no,no,yes)",
        sorts=["content_usage.last_accessed_date"],
        limit="50000"
    )
    unused_content_query = sdk.create_query(
        body=unused_content_query
    )
    return unused_content_query.id


def get_unused_content(query_id: str):
    """ Run a query against System Activity to get a list of unused content.

    Args:
      query_id (str): The ID of the query.

    Returns:
      A list of dictionaries, where each dictionary represents an unused dashboard or Look.
    """
    unused_content = json.loads(sdk.run_query(
        query_id=query_id,
        result_format="json",
        cache=True
    ))

    return unused_content


def get_deleted_content_query_id(days: int):
    """ Get the query ID for a System Activity query which returns all content that's been soft deleted for 90+ days. 

    Args:
      days (int): The number of days a content should be soft deleted for before hard deleting it.

    Returns:
      A re-useable query ID that can be used to run the query & send a schedule with the query's results.
    """
    deleted_query = models40.WriteQuery(
        model="system__activity",
        view="content_usage",
        fields=[
            "dashboard.id",
            "look.id",
            "content_usage.content_title",
            "content_usage.content_type",
            "content_usage.last_accessed_date",
            "dashboard.deleted_date",
            "look.deleted_date"
        ],
        dynamic_fields='[{"category":"dimension",\
            "expression":"diff_days(coalesce(${dashboard.deleted_date},${look.deleted_date}), now())",\
            "label":"Days Since Moved to Trash",\
            "value_format":null,\
            "value_format_name":null,\
            "dimension":"days_since_moved_to_trash",\
            "_kind_hint":"dimension",\
            "_type_hint":"number"}]',
        pivots=None,
        fill_fields=None,
        filters={
            "content_usage.content_type": "dashboard,look",
            "days_since_moved_to_trash": f">{days}"
        },
        filter_expression="if(is_null(${dashboard.deleted_date}) = no OR is_null(${look.deleted_date}) = no,yes,no)",
        sorts=["content_usage.last_accessed_date"],
        limit="50000"
    )
    trashed_content_query = sdk.create_query(
        body=deleted_query
    )
    return trashed_content_query.id


def get_deleted_content(query_id: str):
    """ Run a query against System Activity to get a list of soft deleted content.

    Args:
      query_id (str): The ID of the query.

    Returns:
      A list of dictionaries, where each dictionary represents an unused dashboard or Look.
    """
    unused_content = json.loads(sdk.run_query(
        query_id=query_id,
        result_format="json",
        cache=True
    ))

    return unused_content


def send_content_notification(query_id: str, delete_type: str, address: str):
    """ Send an email notification to the given email address(es) about the content that was soft/hard deleted on the given date.

    Args:
      query_id (str): The ID of the query.
      delete_type (str): The type of content that was deleted.
      address (str): The address to send the notification to.
    """
    date_today = datetime.today().strftime('%Y-%m-%d')

    scheduled_plan_destination_body = models40.ScheduledPlanDestination(
        format="csv",
        type="email",
        address=address,
        message=f"List of dashboards and Looks that were {delete_type} deleted on {date_today}.\
        Note, LookML dashboards are unaffected by this automation, the dashboard lkml file has to be deleted from its LookML project.",
        apply_formatting=False,
        apply_vis=False
    )
    unused_content_notification = models40.WriteScheduledPlan(
        name=f"[Looker Automation] {delete_type.capitalize()} deleted content ({date_today}).",
        query_id=query_id,
        scheduled_plan_destination=[
            scheduled_plan_destination_body
        ]
    )

    try:
        send_notification = sdk.scheduled_plan_run_once(
            body=unused_content_notification
        )
        return send_notification
    except Exception as e:
        return f"Error sending {delete_type} delete email notification ({date_today}): {e}"


def get_dashboard_ids(content: list):
    """ Get the dashboard IDs for the given content.

    Args:
      content (list): A list of dictionaries, where each dictionary represents a dashboard or look.

    Returns:
      A list of dashboard IDs.
    """
    return [dashboard['dashboard.id'] for dashboard in content if dashboard['content_usage.content_type'] == 'dashboard' and dashboard['dashboard.id'] is not None]


def get_look_ids(content: list):
    """ Get the look IDs for the given content.

    Args:
      content (list): A list of dictionaries, where each dictionary represents a dashboard or look.

    Returns:
      A list of look IDs.
    """
    return [look['look.id'] for look in content if look['content_usage.content_type'] == 'look']


def soft_delete_dashboard(dashboard_id: str):
    """ Soft delete the given dashboard.

    Args:
      dashboard_id: The ID of the dashboard to soft delete.
    """
    # todo: update to `deleted=True` when ready to run automation. Leave as is to do a dry run (run queries & send email, without deleting content).
    dashboard = models40.WriteDashboard(deleted=False)
    try:
        sdk.update_dashboard(str(dashboard_id), body=dashboard)
        return f"Successfully soft deleted dashboard: {dashboard_id}"
    except Exception as e:
        return f"Error with soft deleting dashboard ({dashboard_id}): {e}"


def soft_delete_look(look_id: str):
    """ Soft delete the given look.

    Args:
      look_id: The ID of the look to soft delete.
    """
    # todo: update to `deleted=True` when ready to run automation. Leave as is to do a dry run (run queries & send email, without deleting content).
    look = models40.WriteLookWithQuery(deleted=False)
    try:
        sdk.update_look(str(look_id), body=look)
        return f"Successfully soft deleted Look: {look_id}"
    except Exception as e:
        return f"Error with soft deleting Look ({look_id}): {e}"


def hard_delete_dashboard(dashboard_id: str):
    """ Hard (permanently) delete a dashboard from the instanace. There is no undo for this kind of delete!

    Args:
      dashboard_id: The ID of the dashboard to hard delete.
    """
    try:
        # todo: uncomment delete_dashboard method when ready to run automation. Leave as is to do a dry run (run queries & send email, without deleting content).
        # sdk.delete_dashboard(str(dashboard_id))
        return f"Successfully permanently deleted dashboard: {dashboard_id}"
    except Exception as e:
        return f"Error with permanently deleting dashboard ({dashboard_id}): {e}"


def hard_delete_look(look_id: str):
    """ Hard (permanently) delete a Look from the instanace. There is no undo for this kind of delete!

    Args:
      look_id: The ID of the dashboard to hard delete.
    """
    try:
        # todo: uncomment delete_look method when ready to run automation. Leave as is to do a dry run (run queries & send email, without deleting content).
        # sdk.delete_look(str(look_id))
        return f"Successfully permanently deleted Look: {look_id}"
    except Exception as e:
        return f"Error with permanently deleting Look ({look_id}): {e}"
