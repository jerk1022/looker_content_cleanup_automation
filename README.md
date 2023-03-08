# Looker Content Cleanup Automation with Cloud Functions & Cloud Scheduler

## Overview

This repository contains a [Google Cloud Function](https://cloud.google.com/functions) that leverages the Looker Python SDK to automate Looker content cleanup. It can be triggered to run at your desired cadence using [Cloud Scheduler](https://cloud.google.com/scheduler).

Implementing an automated content cleanup process will help your instance avoid content bloat and make users more productive when searching for content. [Content bloat is the effect on an organization when time is wasted finding the relevant content to answer a question or recreating content that already exists](https://sarahsnewsletter.substack.com/p/the-thrill-of-deprecating-dashboards).

**Content Clean Up Process**

A process for cleaning up unused dashboards and Looks from your Looker instance looks something like:

1. Schedule content clean up automation to run every 90 days.
2. Dashboards and Looks not used in the past 90 days are archived (soft deleted). Soft deleting a piece of content means moving it to the [Trash folder](https://cloud.google.com/looker/docs/admin-spaces#trash) which only admins have access to.
   - Soft deleted content can be restored to its original folder from the UI or with the API ([Appendix](#appendix)).
3. Permanently delete content (i.e. remove from Trash folder) that's been soft-deleted and goes unclaimed for another 90 days.

Running the automation every 90 days allows the script to handle both soft-deleting and permanently deleting content at the same time. That said, the days are configurable within the script.

## Requirements

- Looker instance in which you have Admin or at least `see_system_activity` and `schedule_external_look_emails` permissions.
- Google Cloud Project with the following APIs enabled:
  - Cloud Build API
  - Cloud Functions API
  - Cloud Logging API
  - Cloud Pub/Sub API
  - Cloud Scheduler API
  - Secret Manager API

## How it works

The script executes the following steps each time it is run:

1. Get two query IDs which run a System Activity query to identify content unused in the past 90 days and content deleted more than 90 days ago, respectively.
2. Run both queries to get data for unused content and deleted content.
3. Soft delete unused content
4. Permanently delete content in Trash folder
5. Send two emails containing the soft deleted and permanently deleted content.

To avoid accidental deletions while setting up up the automation, it's currently in dry run / safe mode. This means the soft delete and hard delete functions are commented out in `main.py` (`soft_delete_dashboard`, `soft_delete_look`, `hard_delete_dashboard`, `hard_delete_look`).

Before running the script, in `main.py` search `todo` to:

- Update `DAYS_BEFORE_SOFT_DELETE` (# of days content is unused before archival) and `DAYS_BEFORE_HARD_DELETE` (# of days in trash before permanently deletion).
- Update `NOTIFICATION_EMAIL_ADDRESS` (email address for content deletion notification).
- Toggle dry run of automation off/on depending on if you want content to be deleted.

**Note**: this automation only works for Looks and user-defined dashboards. The unused content email notification will contain all LookML dashboards which can be deleted by removing their dashboard lkml file in its LookML project.

## Setup

The following steps assume deployment using Google Cloud UI Console. Check out ["Your First Function: Python"](https://cloud.google.com/functions/docs/first-python) for steps to deploy using the `gcloud` command-line tool.

1. Obtain a [Looker API3 Key](https://docs.looker.com/admin-options/settings/users#api3_keys)

2. Go to [Cloud Secret Manager](https://cloud.google.com/secret-manager) and enable the Secret Manager API. Create the following secrets:

   1. `looker-base-url`: secret value is your Looker instance URL (e.g. `https://my_looker_instance.cloud.looker.com/`)
   2. `looker-client-id`: secret value is the Client ID generated in Step 1.
   3. `looker-client-secret`: secret value is the Client Secret generated in Step 1.

3. Go to Cloud Functions and create a new function.

4. Cloud Functions function settings:

   1. **Basics**

      - **Environment**: `1st gen`
      - **Function name**: `looker-content-cleanup-automation`
      - **Region**: `us-west1` (or preferred region)
      - **Trigger type**: `HTTP`
      - **Authentication**: `Require authentication`
      - **Require HTTPS**: `Enabled`
      - Select `Save`

   2. **Runtime, build, connections and security settings**

      - **Runtime**

        - **Memory allocated**: `512 MB`
        - **Timeout**: `540`
        - **Runtime service account**: `App Engine default service account`

      - **Security and Image Repo**

        - **Reference a Secret**: reference the `looker-base-url` secret created in Step 2 and map it to the `LOOKERSDK_BASE_URL` environment variable.
          - **Secret**: `looker-base-url`
          - **Reference method**: `Exposed as environment variable`
          - **Name 1**: `LOOKERSDK_BASE_URL`
          - Select `Done`
        - **Reference a Secret**: reference the `looker-client-id` secret created in Step 2 and map it to the `LOOKERSDK_CLIENT_ID` environment variable.
          - **Secret**: `looker-client-id`
          - **Reference method**: `Exposed as environment variable`
          - **Name 1**: `LOOKERSDK_CLIENT_ID`
          - Select `Done`
        - **Reference a Secret**: reference the `looker-client-secret` secret created in Step 2 and map it to the `LOOKERSDK_CLIENT_SECRET` environment variable.
          - **Secret**: `looker-client-secret`
          - **Reference method**: `Exposed as environment variable`
          - **Name 1**: `LOOKERSDK_CLIENT_SECRET`
          - Select `Done`

   3. **Code**

      - **Runtime**: `Python 3.9`
      - Copy and paste the contents of `main.py` in this repository into the `main.py` file once inside Cloud Function's inline editor.
      - **Entry point**: `main`
        - **NOTE**: review the `todo` items listed in the script prior to deploying, otherwise the automation won't work as intended.
      - Copy and paste the contents of `requirements.txt` in this repository to the `requirements.txt` file once inside Cloud Function's inline editor.

   4. Deploy the function.

5. Go to Cloud IAM > IAM and grant the `App Engine default service account` (`<project-name>@appspot.gserviceaccount.com`) principal `Secret Manager Secret Accessor` role to access the secrets created in Step 2.

6. Test the automation function in dry run mode (run queries and send schedules, without soft deleting or hard deleting any content).

   - Check out [this article](https://cloud.google.com/functions/docs/quickstart-python#test_the_function) for detailed instructions.

7. Go to Cloud Scheduler and select `Schedule a job` (or `Create job`).

8. Cloud Scheduler job settings:

   1. **Define the schedule**

      - **Name**: `trigger-looker-content-cleanup-automation`
      - **Region**: `us-west1 (Oregon)` (same region as Cloud Function)
      - **Frequency**: `0 0 1 */3 *` (every 3 months or update to desired frequency of how often the automation should run)
      - **Timezone**: Select desired timezone the scheduled job should use
      - Select `Continue`

   2. **Configure the execution**

      - **Target type**: `HTTP`
      - **URL**: Trigger URL from function created in Step 4
      - **HTTP method**: `POST`
      - **Auth header**: `Add OIDC token`
      - **Service account**: `App Engine default service account`

   3. Select `Create`

9. Test the schedule (Actions > Force run) to confirm it triggers the `looker-content-cleanup-automation` function in dry run mode.

10. After validating everything is working as expected, make the `todo` changes to `main.py` to toggle off dry run mode.

## Appendix

### Restore soft deleted content

```python
import looker_sdk
from looker_sdk import models40

config_file = "looker.ini"
sdk = looker_sdk.init40(config_file)

def restore_soft_delete_dashboard(dashboard_id):
    dashboard = models40.WriteDashboard(deleted=False)
    try:
        sdk.update_dashboard(str(dashboard_id), body=dashboard)
        print(f"Successfully restored dashboard {dashboard_id}")
    except Exception as e:
        print(f"Error: {e}")

def restore_soft_delete_look(look_id):
    look = models40.WriteLookWithQuery(deleted=False)
    try:
        sdk.update_look(str(look_id), body=look)
        print(f"Successfully restored look {look_id}")
    except Exception as e:
        print(f"Error: {e}")

# Provide a list of look_ids to restore
looks_to_restore = []

for look in looks_to_restore:
    restore_soft_delete_look(look)

# Provide a list of dashboard_ids to restore
dashboards_to_restore = [1]

for dashboard in dashboards_to_restore:
    restore_soft_delete_dashboard(dashboard)
```
