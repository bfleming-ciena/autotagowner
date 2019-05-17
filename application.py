# from azure.common import credentials
import json

import os

import sys

from azure.common import credentials

from azure.mgmt.resource import ResourceManagementClient

from flask import Flask, jsonify, make_response, request

from msrestazure.azure_active_directory import MSIAuthentication

app = Flask(__name__)
history = ["No messages."]

# If I want to apply tags using ResourceManagementClient, it expects a schema
# version.  Haven't found a way to look this up dynamically. todo: research
api_version_lookup = {"Microsoft.ClassicStorage/storageAccounts": "2016-11-01",
                      "Microsoft.Compute/availabilitySets": "2019-03-01",
                      "Microsoft.Compute/disks": "2018-09-30",
                      "Microsoft.Compute/images": "2016-11-01",
                      "Microsoft.Compute/snapshots": "2018-09-30",
                      "Microsoft.Compute/virtualMachines": "2019-03-01",
                      "Microsoft.DataFactory/dataFactorie": "2018-06-01",
                      "Microsoft.DataFactory/factories": "2018-06-01",
                      "Microsoft.DataLakeAnalytics/accounts": "2016-11-01",
                      "Microsoft.DataLakeStore/accounts": "2016-11-01",
                      "Microsoft.Databricks/workspaces": "2018-04-01",
                      "Microsoft.Network/applicationGateways": "2019-02-01",
                      "Microsoft.Network/loadBalancers": "2019-02-01",
                      "Microsoft.Network/networkInterfaces": "2018-10-01",
                      "Microsoft.Network/publicIPAddresses": "2019-02-01",
                      "Microsoft.Sql/servers": "2015-01-01",
                      "Microsoft.Sql/servers/databases": "2014-04-01",
                      "Microsoft.Storage/storageAccounts": "2018-11-01"}


# Value is saved in the web application config.
def authenticate(request):
    if "key" in os.environ:
        key = os.environ['key']
        if 'code' in request.args and request.args['code'] == key:
            return True
    else:
        return False


# Last x messages sent. Useful for debugging.
@app.route('/api/clearhistory', methods=['GET','POST'])
def clearhistoryurl():
    if not authenticate(request):
        return make_response("", 401)

    global history
    history = ["No changes"]
    return make_response(str(type(history)), 200)

# Last x messages sent. Useful for debugging.
@app.route('/api/history', methods=['GET', 'POST'])
def historyurl():
    if not authenticate(request):
        return make_response("", 401)

    global history
    if len(history) > 50:  # keep last 50 messages.
        history = history[-50:]
    if len(history) <= 0:
        return make_response(str(type(history)), 200)
    else:
        return make_response("<p><p>".join(history), 200)


@app.route('/api/update', methods=['GET', 'POST'])
def update():

    try:
        if not authenticate(request):
            return make_response("", 401)

        global history

        json_data = json.loads(request.data.decode(encoding='UTF-8').replace("\'", "\""))
        history.append(request.data.decode(encoding='UTF-8').replace("\'", "\""))
        if len(history) > 50:  # keep last 50 messages.
            history = history[-50:]

        # Handle registration with the event grid
        if 'validationCode' in json_data[0]['data']:
            response = {}
            response['ValidationResponse'] = json_data[0]['data']['validationCode']
            return make_response(jsonify(response), 200)
        else:

            # VM Creation
            if is_event(json_data[0], event_type=u'Microsoft.Resources.ResourceWriteSuccess',
                        operation_name=u'Microsoft.Compute/virtualMachines/write'):
                creator = get_creator(json_data[0])
                id = get_id(json_data[0])
                subscription = id.split('/')[2]
                if creator is not None and len(creator) > 0 and resource_apply_tags(id, subscription, u'Microsoft.Compute/virtualMachines', {"it_Owner": creator}):
                    sys.stderr.write("VIRTUAL MACHINE EVENT: RESPONSE 200 *****************" + str(id) + "<br>" + "\n\n")
                    return make_response("Accepted", 200)
                else:
                    return make_response("OK", 200) # On error, just accept lost data?

            # Disk Creation
            if is_event(json_data[0], event_type=u'Microsoft.Resources.ResourceWriteSuccess',
                        operation_name=u'Microsoft.Compute/disks/write'):
                creator = get_creator(json_data[0])
                id = get_id(json_data[0])
                subscription = id.split('/')[2]
                if creator is not None and len(creator) > 0 and resource_apply_tags(id, subscription, u'Microsoft.Compute/disks', {"it_Owner": creator}):
                    sys.stderr.write("VIRTUAL MACHINE EVENT: RESPONSE 200 *****************" + str(id) + "<br>" + "\n\n")
                    return make_response("Accepted", 200)
                else:
                    return make_response("OK", 200) # On error, just accept lost data?

            # Storage Account Creation
            if is_event(json_data[0], event_type=u'Microsoft.Resources.ResourceWriteSuccess',
                        operation_name=u'Microsoft.Storage/storageAccounts/write'):
                creator = get_creator(json_data[0])
                id = get_id(json_data[0])
                subscription = id.split('/')[2]

                if creator is not None and len(creator) > 0 and resource_apply_tags(id, subscription, "Microsoft.Storage/storageAccounts", {"it_Owner": creator}):
                    return make_response("Accepted", 200)
                else:
                    return make_response("Internal Server Error", 500)

    except Exception as e:
        return make_response("Internal Server Error", 500)

    return make_response("OK", 200)


def is_event(msg, event_type=None, operation_name=None):
    try:
        if 'eventType' in msg and 'data' in msg:
            # value is unicode so need to use ==
            if msg['eventType'] == event_type and \
                    msg['data']['operationName'] == operation_name:
                return True
    except:
        return False

    return False


def get_id(msg):
    try:
        if 'data' in msg and 'resourceUri' in msg['data']:
            return msg['data']['resourceUri']
    except:
        return None

    return None


def get_creator(msg, key_endswith="identity/claims/name"):
    try:
        if 'claims' in msg['data']:
            for key in msg['data']['claims']:
                if key.endswith(key_endswith):
                    return msg['data']['claims'][key]
    except:
        return None

    return None


# I found the ResourceManagementClient useful becuz it accepts any resource.
# Otherwise I would need to the resource-specific class for every resource
# I wanted to tag. The downside is it requires the api_version which is hard
# to get automatically.
def resource_apply_tags(id, subscription, provider, tags):

    if "LOCAL_DEBUG" in os.environ and os.environ["LOCAL_DEBUG"] == '1':
        # When running locally for debug/development
        sys.stderr.write("****** USING CLI AUTHENTICATION ***********")
        creds, _ = credentials.get_azure_cli_credentials(resource=None, with_tenant=False)
    else:
        # When running on Azure, and managed identity is used to grant tag priviledge.
        sys.stderr.write("****** USING MSI AUTHENTICATION ***********")
        creds = MSIAuthentication()

    resource_client = ResourceManagementClient(creds, subscription)

    try:
        r = resource_client.resources.get_by_id(id, api_version_lookup[provider])
    except:
        print("Lookup Failed: Skipped...", id)
        return False

    # The tag operation is not additive. Preserve tags already there and add new ones.
    try:
        current_tags = r.tags
        if 'it_Owner' in current_tags and len(current_tags['it_Owner']) > 0:
            sys.stderr.write("**************it_Owner exists.  Do Nothing. ***************")
            return False
    except:
        assert False, "Invalid tags provided."

    merged_tags = {}
    if current_tags:
        merged_tags.update(current_tags)
    merged_tags.update(tags)

    r.tags = merged_tags

    resource_client.resources.create_or_update_by_id(id, api_version_lookup[provider], r)

    return True
