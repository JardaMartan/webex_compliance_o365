#!/bin/#!/usr/bin/env python3

import os
import sys
import uuid
import logging
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

from urllib.parse import urlparse, quote, parse_qsl, urlencode, urlunparse

from webexteamssdk import WebexTeamsAPI, ApiError, AccessToken
webex_api = WebexTeamsAPI(access_token="12345")

import boto3
from ddb_single_table_obj import DDB_Single_Table

from O365 import Account, FileSystemTokenBackend
from o365_db_token_storage import DBTokenBackend
from o365_group import Group

import json, requests
from datetime import datetime, timedelta, timezone
import time
from flask import Flask, request, redirect, url_for, Response

import concurrent.futures
import signal
import re

import buttons_cards as bc

flask_app = Flask(__name__)
flask_app.config["DEBUG"] = True
requests.packages.urllib3.disable_warnings()

logger = logging.getLogger()

ddb = None

ADMIN_SCOPE = ["audit:events_read"]

TEAMS_COMPLIANCE_SCOPE = ["spark-compliance:events_read",
    "spark-compliance:memberships_read", "spark-compliance:memberships_write",
    "spark-compliance:messages_read", "spark-compliance:messages_write",
    "spark-compliance:rooms_read", "spark-compliance:rooms_write",
    "spark-compliance:team_memberships_read", "spark-compliance:team_memberships_write",
    "spark-compliance:teams_read",
    "spark:people_read"] # "spark:rooms_read", "spark:kms"
    
MORE_SCOPE = ["spark:memberships_read", "spark:memberships_write",
    "spark:messages_read", "spark:messages_write",
    "spark:team_memberships_read", "spark:team_memberships_write",
    "spark:teams_read", "spark:teams_write"]
    
TEAMS_COMPLIANCE_READ_SCOPE = ["spark-compliance:events_read",
    "spark-compliance:memberships_read",
    "spark-compliance:messages_read",
    "spark-compliance:rooms_read",
    "spark-compliance:team_memberships_read",
    "spark-compliance:teams_read",
    "spark:people_read"]

MEETINGS_COMPLIANCE_SCOPE = ["spark-compliance:meetings_write"]

DEFAULT_SCOPE = ["spark:kms"]

SUSPECT_MIME_TYPES = ["application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template",
    "application/vnd.ms-word.document.macroEnabled.12",
    "application/vnd.ms-word.template.macroEnabled.12",
    "application/vnd.ms-word.document.macroEnabled.12",
    "application/vnd.ms-word.template.macroEnabled.12",
    "application/msexcel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
    "application/vnd.ms-excel.sheet.macroEnabled.12",
    "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
    "application/vnd.ms-excel.template.macroEnabled.12",
    "application/vnd.ms-excel.addin.macroEnabled.12",
    "application/mspowerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.presentationml.template",
    "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
    "application/vnd.ms-powerpoint.addin.macroEnabled.12",
    "application/vnd.ms-powerpoint.presentation.macroEnabled.12",
    "application/vnd.ms-powerpoint.slideshow.macroEnabled.12",
    "application/vnd.ms-powerpoint.template.macroEnabled.12",
    "application/pdf"]

STATE_CHECK = "webex is great" # integrity test phrase
EVENT_CHECK_INTERVAL = 15
SAFE_TOKEN_DELTA = 3600 # safety seconds before access token expires - renew if smaller

GRAPH_SCOPE = ["offline_access",
    "User.Read.All",
    "Group.Read.All",
    "Group.ReadWrite.All",
    "GroupMember.Read.All",
    "GroupMember.ReadWrite.All",
    "Sites.FullControl.All",
    "Sites.Manage.All",
    "Sites.Read.All",
    "Sites.ReadWrite.All",
    "Subscription.Read.All",
    "Team.ReadBasic.All",
    "TeamMember.Read.All",
    "TeamMember.ReadWrite.All",
    "TeamMember.ReadWriteNonOwnerRole.All",
    "User.Read",
    "User.Read.All"]
O365_SCOPE = GRAPH_SCOPE
O365_LOCAL_USER_KEY = "LOCAL"
O365_ACCOUNT_KEY = "GENERIC"
O365_API_CHECK_INTERVAL = 300 # seconds

def sigterm_handler(_signo, _stack_frame):
    "When sysvinit sends the TERM signal, cleanup before exiting."

    flask_app.logger.info("Received signal {}, exiting...".format(_signo))
    
    thread_executor._threads.clear()
    concurrent.futures.thread._threads_queues.clear()
    sys.exit(0)

signal.signal(signal.SIGTERM, sigterm_handler)
signal.signal(signal.SIGINT, sigterm_handler)

thread_executor = concurrent.futures.ThreadPoolExecutor()
wxt_username = "COMPLIANCE"
sxt_user_id = None
wxt_token_key = "COMPLIANCE"
wxt_resource = None
wxt_type = None
wxt_actor_email = None
wxt_compliance = False
token_refreshed = False
o365_account_changed = False

class AccessTokenAbs(AccessToken):
    def __init__(self, access_token_json):
        super().__init__(access_token_json)
        if not "expires_at" in self._json_data.keys():
            self._json_data["expires_at"] = str((datetime.now(timezone.utc) + timedelta(seconds = self.expires_in)).timestamp())
        flask_app.logger.debug("Access Token expires in: {}s, at: {}".format(self.expires_in, self.expires_at))
        if not "refresh_token_expires_at" in self._json_data.keys():
            self._json_data["refresh_token_expires_at"] = str((datetime.now(timezone.utc) + timedelta(seconds = self.refresh_token_expires_in)).timestamp())
        flask_app.logger.debug("Refresh Token expires in: {}s, at: {}".format(self.refresh_token_expires_in, self.refresh_token_expires_at))
        
    @property
    def expires_at(self):
        return self._json_data["expires_at"]
        
    @property
    def refresh_token_expires_at(self):
        return self._json_data["refresh_token_expires_at"]

def save_tokens(token_key, tokens):
    global token_refreshed
    
    flask_app.logger.debug("AT timestamp: {}".format(tokens.expires_at))
    token_record = {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_at": tokens.expires_at,
        "refresh_token_expires_at": tokens.refresh_token_expires_at
    }
    ddb.save_db_record(token_key, "TOKENS", str(tokens.expires_at), **token_record)
    
    token_refreshed = True
    
def get_tokens_for_key(token_key):
    db_tokens = ddb.get_db_record(token_key, "TOKENS")
    flask_app.logger.debug("Loaded tokens from db: {}".format(db_tokens))
    
    if db_tokens:
        tokens = AccessTokenAbs(db_tokens)
        flask_app.logger.debug("Got tokens: {}".format(tokens))
        ## TODO: check if token is not expired, generate new using refresh token if needed
        return tokens
    else:
        flask_app.logger.error("No tokens for key {}.".format(token_key))
        return None

def refresh_tokens_for_key(token_key):
    tokens = get_tokens_for_key(token_key)
    client_id = os.getenv("WEBEX_INTEGRATION_CLIENT_ID")
    client_secret = os.getenv("WEBEX_INTEGRATION_CLIENT_SECRET")
    integration_api = WebexTeamsAPI()
    try:
        new_tokens = AccessTokenAbs(integration_api.access_tokens.refresh(client_id, client_secret, tokens.refresh_token).json_data)
        save_tokens(token_key, new_tokens)
        flask_app.logger.info("Tokens refreshed for key {}".format(token_key))
    except ApiError as e:
        flask_app.logger.error("Client Id and Secret loading error: {}".format(e))
        return "Error refreshing an access token. Client Id and Secret loading error: {}".format(e)
        
    return new_tokens
    
# O365
def get_o365_account(user_id, org_id, resource = None):
    o365_client_id = os.getenv("O365_CLIENT_ID")
    o365_client_secret = os.getenv("O365_CLIENT_SECRET")
    o365_credentials = (o365_client_id, o365_client_secret)
    
    o365_tenant_id = os.getenv("O365_TENANT_ID")

    token_backend = DBTokenBackend(user_id, "O365_GUEST_CHECK", org_id)
    args = {}
    if resource:
        args["resource"] = resource
    account = Account(o365_credentials, tenant_id = o365_tenant_id, token_backend=token_backend, auth_flow_type = "authorization", **args)
    
    flask_app.logger.debug("account {} is{} authenticated".format(user_id, "" if account.is_authenticated else " not"))

    return account
    
def get_o365_account_noauth():
    o365_client_id = os.getenv("O365_CLIENT_ID")
    o365_client_secret = os.getenv("O365_CLIENT_SECRET")
    o365_credentials = (o365_client_id, o365_client_secret)

    o365_tenant_id = os.getenv("O365_TENANT_ID")

    account = Account(o365_credentials, tenant_id = o365_tenant_id, auth_flow_type = "authorization")
    
    flask_app.logger.debug("get O365 account without authentication")

    return account
    
def o365_check_token():
    global o365_account_changed
    
    account = get_o365_account(O365_LOCAL_USER_KEY, O365_ACCOUNT_KEY)
    
    if not account.is_authenticated:
        flask_app.logger.error("No valid O365 authorization, trying refresh token...")
        con = account.connection
        token = con.token_backend.get_token()
        if not token is None:
            flask_app.logger.debug("Refresh O365 authorization, long lived: {}".format(token.is_long_lived))
            con.refresh_token()
            flask_app.logger.debug("Refresh O365 authorization done")
            o365_account_changed = True

    # query_condition = "$filter=userType eq 'Guest' and mail eq '{}'".format(event.data.personEmail)
    query_condition = "userType eq 'Guest' and mail eq 'nonexistent@perlovka.guru'"
    aad = account.directory()
    user_dir = aad.get_users(query = query_condition)
    
    for user in user_dir:
        flask_app.logger.info("AAD dummy query result: {}".format([user.mail, user.user_principal_name, user.display_name]))
    
# Flask part of the code

"""
1. initialize database table if needed
2. start event checking thread
"""
@flask_app.before_first_request
def startup():
    global ddb
    
    ddb = DDB_Single_Table()
    flask_app.logger.debug("initialize DDB object {}".format(ddb))
        
    flask_app.logger.debug("Starting event check...")
    check_events(EVENT_CHECK_INTERVAL, wxt_compliance, wxt_resource, wxt_type, wxt_actor_email)
    # thread_executor.submit(check_events, EVENT_CHECK_INTERVAL, wxt_compliance, wxt_resource, wxt_type, wxt_actor_email)
    # o365_check_token()

@flask_app.route("/")
def hello():
    return "Hello World!"

"""
OAuth proccess done
"""
@flask_app.route("/authdone", methods=["GET"])
def authdone():
    ## TODO: post the information & help, maybe an event creation form to the 1-1 space with the user
    return "Thank you for providing the authorization. You may close this browser window."

"""
OAuth grant flow start
"""
@flask_app.route("/authorize", methods=["GET"])
def authorize():
    myUrlParts = urlparse(request.url)
    full_redirect_uri = os.getenv("REDIRECT_URI")
    if full_redirect_uri is None:
        full_redirect_uri = myUrlParts.scheme + "://" + myUrlParts.netloc + url_for("manager")
    flask_app.logger.info("Authorize redirect URL: {}".format(full_redirect_uri))

    client_id = os.getenv("WEBEX_INTEGRATION_CLIENT_ID")
    redirect_uri = quote(full_redirect_uri, safe="")
    scope = TEAMS_COMPLIANCE_SCOPE + DEFAULT_SCOPE + MORE_SCOPE
    scope_uri = quote(" ".join(scope), safe="")
    join_url = webex_api.base_url+"authorize?client_id={}&response_type=code&redirect_uri={}&scope={}&state={}".format(client_id, redirect_uri, scope_uri, STATE_CHECK)

    return redirect(join_url)
    
"""
OAuth grant flow redirect url
generate access and refresh tokens using "code" generated in OAuth grant flow
after user successfully authenticated to Webex

See: https://developer.webex.com/blog/real-world-walkthrough-of-building-an-oauth-webex-integration
https://developer.webex.com/docs/integrations
"""   
@flask_app.route("/manager", methods=["GET"])
def manager():
    global wxt_username
    
    if request.args.get("error"):
        return request.args.get("error_description")
        
    input_code = request.args.get("code")
    check_phrase = request.args.get("state")
    flask_app.logger.debug("Authorization request \"state\": {}, code: {}".format(check_phrase, input_code))

    myUrlParts = urlparse(request.url)
    full_redirect_uri = os.getenv("REDIRECT_URI")
    if full_redirect_uri is None:
        full_redirect_uri = myUrlParts.scheme + "://" + myUrlParts.netloc + url_for("manager")
    flask_app.logger.debug("Manager redirect URI: {}".format(full_redirect_uri))
    
    try:
        client_id = os.getenv("WEBEX_INTEGRATION_CLIENT_ID")
        client_secret = os.getenv("WEBEX_INTEGRATION_CLIENT_SECRET")
        tokens = AccessTokenAbs(webex_api.access_tokens.get(client_id, client_secret, input_code, full_redirect_uri).json_data)
        flask_app.logger.debug("Access info: {}".format(tokens))
    except ApiError as e:
        flask_app.logger.error("Client Id and Secret loading error: {}".format(e))
        return "Error issuing an access token. Client Id and Secret loading error: {}".format(e)
        
    webex_integration_api = WebexTeamsAPI(access_token=tokens.access_token)
    try:
        user_info = webex_integration_api.people.me()
        flask_app.logger.debug("Got user info: {}".format(user_info))
        wxt_username = user_info.emails[0]
        save_tokens(wxt_token_key, tokens)
        
        ## TODO: add periodic access token refresh
    except ApiError as e:
        flask_app.logger.error("Error getting user information: {}".format(e))
        return "Error getting your user information: {}".format(e)
        
    return redirect(url_for("authdone"))
    
"""
O365 OAuth grant flow
"""
@flask_app.route('/o365auth')
def o365_auth():
    my_state = request.args.get("state", "local")
    flask_app.logger.debug("input state: {}".format(my_state))
    
    myUrlParts = urlparse(request.url)
    # full_redirect_uri = secure_scheme(myUrlParts.scheme) + "://" + myUrlParts.netloc + url_for("o365_do_auth")
    full_redirect_uri = myUrlParts.scheme + "://" + myUrlParts.netloc + url_for("o365_do_auth")
    flask_app.logger.debug("Authorize redirect URL: {}".format(full_redirect_uri))

    # callback = quote(full_redirect_uri, safe="")
    callback = full_redirect_uri
    scopes = O365_SCOPE
    
    account = get_o365_account_noauth()

    url, o365_state = account.con.get_authorization_url(requested_scopes=scopes, redirect_uri=callback)
    
    # replace "state" parameter injected by O365 object
    o365_auth_parts = urlparse(url)
    o365_query = dict(parse_qsl(o365_auth_parts.query))
    o365_query["state"] = my_state
    new_o365_auth_parts = o365_auth_parts._replace(query = urlencode(o365_query))
    new_o365_url = urlunparse(new_o365_auth_parts)
    
    flask_app.logger.debug("O365 auth URL: {}".format(new_o365_url))

    # the state must be saved somewhere as it will be needed later
    # my_db.store_state(state) # example...

    return redirect(new_o365_url)

@flask_app.route('/o365doauth')
def o365_do_auth():
    global o365_account_changed
    
    # token_backend = FileSystemTokenBackend(token_path='.', token_filename='o365_token.txt')
    my_state = request.args.get("state", O365_LOCAL_USER_KEY)
    flask_app.logger.debug("O365 state: {}".format(my_state))
    
    # person_data = webex_api.people.get(my_state)
    # flask_app.logger.debug("O365 login requestor data: {}".format(person_data))
    
    account = get_o365_account(my_state, O365_ACCOUNT_KEY) # person_data.orgId
    
    # retreive the state saved in auth_step_one
    # my_saved_state = my_db.get_state()  # example...

    # rebuild the redirect_uri used in auth_step_one
    myUrlParts = urlparse(request.url)
    # full_redirect_uri = secure_scheme(myUrlParts.scheme) + "://" + myUrlParts.netloc + url_for("o365_do_auth")
    full_redirect_uri = myUrlParts.scheme + "://" + myUrlParts.netloc + url_for("o365_do_auth")
    flask_app.logger.debug("Authorize doauth redirect URL: {}".format(full_redirect_uri))

    # callback = quote(full_redirect_uri, safe="")
    callback = full_redirect_uri
    req_url = re.sub(r"^http:", "https:", request.url)
    
    flask_app.logger.debug("URL: {}".format(req_url))

    result = account.con.request_token(req_url, 
                                       state=my_state,
                                       redirect_uri=callback)
                                       
    flask_app.logger.info("O365 authentication status: {}".format("authenticated" if account.is_authenticated else "not authenticated"))
    
    # if result is True, then authentication was succesful 
    #  and the auth token is stored in the token backend
    if result:
        o365_account_changed = True
        return redirect(url_for("authdone"))
    else:
        return "Authentication failed: {}".format(result)

"""
Manual token refresh of a single user. Not needed if the thread is running.
"""
@flask_app.route("/tokenrefresh", methods=["GET"])
def token_refresh():
    token_key = request.args.get("token_key")
    if token_key is None:
        return "Please provide a user id"
    
    return refresh_token_for_key(token_key)
    
def refresh_token_for_key(token_key):
    tokens = get_tokens_for_key(token_key)
    integration_api = WebexTeamsAPI()
    client_id = os.getenv("WEBEX_INTEGRATION_CLIENT_ID")
    client_secret = os.getenv("WEBEX_INTEGRATION_CLIENT_SECRET")
    try:
        new_tokens = AccessTokenAbs(integration_api.access_tokens.refresh(client_id, client_secret, tokens.refresh_token).json_data)
        save_tokens(token_key, new_tokens)
    except ApiError as e:
        flask_app.logger.error("Client Id and Secret loading error: {}".format(e))
        return "Error refreshing an access token. Client Id and Secret loading error: {}".format(e)
        
    return "token refresh for key {} done".format(token_key)

"""
Manual token refresh of all users. Not needed if the thread is running.
"""
@flask_app.route("/tokenrefreshall", methods=["GET"])
def token_refresh_all():
    results = ""
    user_tokens = ddb.get_db_record_by_secondary_key("TOKENS")
    for token in user_tokens:
        flask_app.logger.debug("Refreshing: {} token".format(token["pk"]))
        results += refresh_token_for_key(token["pk"])+"\n"
    
    return results

# TODO: manual query of events API
@flask_app.route("/queryevents", methods=["GET"])
def query_events():
    results = ""
    
    return results
    
@flask_app.route("/o365wh", methods=["GET", "POST"])
def o365_webhook():
    webhook = request.get_json(silent=True)
    flask_app.logger.debug("O365 webhook received: {}".format(webhook))
    
    if request.method == "POST":
        
        # validation token when a new subscription is created
        validationToken = request.args.get("validationToken")
        if validationToken:
            flask_app.logger.debug("validation token check: {}".format(validationToken))
            return Response(validationToken, mimetype="text/plain")
            
        try:
            if webhook.get("changeType") == "updated":
                resource = webhook.get("resource")
                data = webhook.get("resourceData")
                delta = data.get("members@delta")
                if data and delta:
                    account = get_o365_account(O365_LOCAL_USER_KEY, O365_ACCOUNT_KEY)
                    
                    # TODO: get O365 group name, get team list, find a team with the same name, get users' e-mail, update team membership
                        
        except Exception as e:
            flask_app.logger.error("O365 webhook exception: {}".format(e))
            
        return Response("", status=202, mimetype="text/plain")
        
    elif request.method == "GET":
        #TODO: subscription setup
        pass
    
    return "OK"

"""
Check events API thread. Infinite loop which periodically checks the Events API.
Doesn't work until "wxt_username" runs through OAuth grant flow above.
Access token is automatically refreshed if needed using Refresh Token.
No additional user authentication is required.
"""
def check_events(check_interval=EVENT_CHECK_INTERVAL, wx_compliance=False, wx_resource=None, wx_type=None, wx_actor_email=None):
    global wxt_username, wxt_user_id, token_refreshed, o365_account_changed

    tokens = None
    wxt_client = None
    
    xargs = {}
    if wx_resource is not None:
        xargs["resource"] = wx_resource
    if wx_type is not None:
        xargs["type"] = wx_type
    flask_app.logger.debug("Additional args: {}".format(xargs))
    
    from_time = datetime.utcnow()
    o365_token_last_check = datetime.utcnow()
    o365_account = get_o365_account(O365_LOCAL_USER_KEY, O365_ACCOUNT_KEY)

    while True:
        try:
            # flask_app.logger.debug("Check events tick.")

    # check for token until there is one available in the DB        
            if tokens is None or token_refreshed:
                tokens = get_tokens_for_key(wxt_token_key)
                if tokens:
                    wxt_client = WebexTeamsAPI(access_token=tokens.access_token)

    # get actorId if required
                    if wx_actor_email is not None:
                        try:
                            wx_actor_list = wxt_client.people.list(email=wx_actor_email)
                            for person in wx_actor_list:
                                xargs["actorId"] = person.id
                        except ApiError as e:
                            flask_app.logger.error("People list API request error: {}".format(e))
                    
                    user_info = wxt_client.people.me()
                    flask_app.logger.debug("Got user info: {}".format(user_info))
                    wx_org_id = user_info.orgId
                    wxt_username = user_info.emails[0]
                    wxt_user_id = user_info.id
                    
                    token_refreshed = False
                else:
                    flask_app.logger.error("No access tokens for key {}. Authorize the user first.".format(wxt_token_key))
            else:
    # renew access token using refresh token if needed
                token_delta = datetime.fromtimestamp(float(tokens.expires_at)) - datetime.utcnow()
                if token_delta.total_seconds() < SAFE_TOKEN_DELTA:
                    flask_app.logger.info("Access token is about to expire, renewing...")
                    tokens = refresh_tokens_for_key(wxt_token_key)
                    wxt_client = WebexTeamsAPI(access_token=tokens.access_token)
                    new_client = True
                    
            if o365_account_changed:
                o365_account = get_o365_account(O365_LOCAL_USER_KEY, O365_ACCOUNT_KEY)
                o365_account_changed = False

    # query the Events API        
            if wxt_client:
                try:
                    to_time = datetime.utcnow()
                    from_stamp = from_time.isoformat(timespec="milliseconds")+"Z"
                    to_stamp = to_time.isoformat(timespec="milliseconds")+"Z"
                    flask_app.logger.debug("check interval {} - {}".format(from_stamp, to_stamp))
                    if wx_compliance:
                        event_list = wxt_client.events.list(_from=from_stamp, to=to_stamp, **xargs)
                        for event in event_list:
                            flask_app.logger.info("Event: {}".format(event))
                            
                            actor = wxt_client.people.get(event.actorId)
                            
                            # TODO: information logging to an external system
                            # flask_app.logger.info("{} {} {} {} by {}\n data: {}".format(event.created, event.resource, event.type, event.data.personEmail, actor.emails[0], event))
                            
                            room_info = wxt_client.rooms.get(event.data.roomId)
                            flask_app.logger.info("Room info: {}".format(room_info))
                            
                            if event.resource == "memberships" and event.type in ["created","deleted"] and event.data.roomType == "group" and not event.actorId == wxt_user_id:
                                if event.type == "created" and room_info.creatorId == event.data.personId:                             
                                    flask_app.logger.info("send notification")
                                    if room_info.teamId:
                                        flask_app.logger.info("Room is part of a team")
                                        if event.type == "created":
                                            my_team_membership_list = wxt_client.team_memberships.list(room_info.teamId)
                                            my_team_membership = None
                                            for team_membership in my_team_membership_list:
                                                if team_membership.personId == wxt_user_id:
                                                    my_team_membership = team_membership
                                                    flask_app.logger.info("existing team membership: {}".format(my_team_membership))
                                                    break
                                            if not my_team_membership:
                                                # somehow team membership API doesn't work
                                                # my_team_membership = wxt_client.team_memberships.create(room_info.teamId, personId = wxt_user_id, isModerator = True)
                                                my_membership = wxt_client.memberships.create(roomId = room_info.id, personId = wxt_user_id, isModerator = True)
                                        
                                        # xargs = {
                                        #     "attachments": [bc.wrap_form(bc.SP_WARNING_FORM)]
                                        # }
                                        # send_compliance_message(wxt_client, event.data.roomId,
                                        #     "Jestliže budete v tomto Prostoru sdílet dokumenty, připojte k němu SharePoint úložiště. Návod najdete zde: https://help.webex.com/cs-cz/n4ve41eb/Webex-Link-a-Microsoft-OneDrive-or-SharePoint-Online-Folder-to-a-Space",
                                        #     xargs, add_delete_me = False)
                                        wxt_client.messages.create(roomId = event.data.roomId,
                                            markdown = "Jestliže budete v tomto Prostoru sdílet dokumenty, připojte k němu SharePoint úložiště. Návod najdete zde: https://help.webex.com/cs-cz/n4ve41eb/Webex-Link-a-Microsoft-OneDrive-or-SharePoint-Online-Folder-to-a-Space",
                                            attachments = [bc.wrap_form(bc.SP_WARNING_FORM)])
                                        
                                # TODO: check if the membership changed on the Team level, list O365 Groups, find a group with the same displayName, find a user's account based on the e-mail (maybe a guest account), update group membership
                                if room_info.teamId:
                                    flask_app.logger.info("Check O365 Group relationship")
                                    team_info = wxt_client.teams.get(room_info.teamId)
                                    o365_group = find_o365_group_by_name(o365_account, team_info.name)
                                    if o365_group:
                                        flask_app.logger.info("Team name {}, o365 group: {}".format(team_info.name, o365_group))
                                        user_account = get_o365_user_account(o365_account, event.data.personEmail)
                                        if user_account:
                                            if event.type == "created":
                                                flask_app.logger.info("add o365 group member: {}".format(user_account["user_info"].user_principal_name))
                                                add_o365_group_member(o365_account, o365_group["id"], user_account["user_info"].object_id)
                                            else:
                                                flask_app.logger.info("delete o365 group member: {}".format(user_account["user_info"].user_principal_name))
                                                delete_o365_group_member(o365_account, o365_group["id"], user_account["user_info"].object_id)
                                        else:
                                            if event.type == "created":
                                                flask_app.logger.info("user {} not found in directory".format(event.data.personEmail))
                                                if hasattr(event.data, "personDisplayName"):
                                                    display_name = event.data.personDisplayName
                                                else:
                                                    display_name = ""
                                                form = bc.nested_replace_dict(bc.USER_WARNING_FORM, {"display_name": display_name, "email": event.data.personEmail, "group_name": team_info.name})
                                                # xargs = {
                                                #     "attachments": [bc.wrap_form(form)]
                                                # }
                                                # send_compliance_message(wxt_client, event.data.roomId, "Uživatel nemá O365 účet.", xargs, add_delete_me = False)
                                                wxt_client.messages.create(roomId = event.data.roomId, markdown = "Uživatel nemá O365 účet.", attachments = [bc.wrap_form(form)])
                                    else:
                                        flask_app.logger.info("No corresponding O365 Group for Team \"{}\"".format(team_info.name))
                                            
                            if event.resource == "messages" and event.type == "created" and not event.actorId == wxt_user_id:
                                # message_info = wxt_client.messages.get(event.data.id)
                                # flask_app.logger.info("Message info: {}".format(message_info))
                                if event.data.files:
                                    hdr = {"Authorization": "Bearer " + wxt_client.access_token}
                                    for url in event.data.files:
                                        file_info = requests.head(url, headers = hdr)
                                        flask_app.logger.info("Message file: {}\ninfo: {}".format(url, file_info.headers))
                                        if file_info.headers["Content-Type"] in SUSPECT_MIME_TYPES:
                                            xargs = {
                                                "attachments": [bc.wrap_form(bc.SP_LINK_FORM)]
                                            }
                                            send_compliance_message(wxt_client, event.data.roomId,
                                                "Odeslal jste typ dokumentu, který podléhá klasifikaci. **Připojte k tomuto Prostoru SharePoint úložiště a dokument pošlete znovu.** Návod najdete zde: https://help.webex.com/cs-cz/n4ve41eb/Webex-Link-a-Microsoft-OneDrive-or-SharePoint-Online-Folder-to-a-Space",
                                                xargs)          
                                            wxt_client.messages.delete(event.data.id)                                  

                    
                except ApiError as e:
                    flask_app.logger.error("API request error: {}".format(e))
                finally:
                    from_time = to_time

            # verify and renew the O365 token
            if (datetime.utcnow() - o365_token_last_check).total_seconds() > O365_API_CHECK_INTERVAL:
                o365_check_token()
                o365_token_last_check = datetime.utcnow()

        except Exception as e:
            flask_app.logger.error("check_events() loop exception: {}".format(e))
        finally:
            time.sleep(check_interval)
            
def send_compliance_message(wxt_client, room_id, message, xargs, add_delete_me = True):
    if add_delete_me:
        my_membership_list = wxt_client.memberships.list(roomId = room_id, personId = wxt_user_id)
        my_membership = None
        for my_membership in my_membership_list:
            flask_app.logger.info("existing membership: {}".format(my_membership))
        if not my_membership:
            my_membership = wxt_client.memberships.create(roomId = room_id, personId = wxt_user_id)
        
    wxt_client.messages.create(roomId = room_id, markdown = message, **xargs)
    if add_delete_me:
        wxt_client.memberships.delete(my_membership.id)
    
def find_o365_group_by_name(o365_account, team_name):
    filter = {"$filter": "displayName eq '{}'".format(team_name), "$select": "id, displayName"}
    grp = Group(o365_account)
    result = grp.list(params = filter)
    
    if result.ok:
        res_json = result.json()
        return res_json["value"][0]
    else:
        return None
        
def get_o365_user_account(o365_account, email):
    EXT_USER_INCLUDE = "#EXT#@"
    
    query_condition = "mail eq '{}'".format(email)
    aad = o365_account.directory()
    user_dir = aad.get_users(query = query_condition)

    for user in user_dir:
        result = {"user_info": user, "guest": True if user.user_principal_name.find(EXT_USER_INCLUDE) > 0 else False}
        return result

def add_o365_group_member(o365_account, group_id, user_id):
    grp = Group(o365_account)
    result = grp.add_member(group_id, user_id)
    
    return result.ok

def delete_o365_group_member(o365_account, group_id, user_id):
    grp = Group(o365_account)
    result = grp.delete_member(group_id, user_id)
    
    return result.ok

"""
Independent thread startup, see:
https://networklore.com/start-task-with-flask/
"""
def start_runner():
    def start_loop():
        not_started = True
        while not_started:
            logger.info('In start loop')
            try:
                r = requests.get('http://127.0.0.1:5050/')
                if r.status_code == 200:
                    logger.info('Server started, quiting start_loop')
                    not_started = False
                logger.debug("Status code: {}".format(r.status_code))
            except:
                logger.info('Server not yet started')
            time.sleep(2)

    logger.info('Started runner')
    thread_executor.submit(start_loop)


if __name__ == "__main__":
    import argparse
    
    # default_user = os.getenv("COMPLIANCE_USER")
    # if default_user is None:
    #     default_user = os.getenv("COMPLIANCE_USER_DEFAULT")
    #     if default_user is None:
    #         default_user = "COMPLIANCE"
    # 
    # flask_app.logger.info("Compliance user from env variables: {}".format(default_user))

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='count', help="Set logging level by number of -v's, -v=WARN, -vv=INFO, -vvv=DEBUG")
    parser.add_argument("-c", "--compliance", action='store_true', help="Monitor compliance events, default: no")
    parser.add_argument("-r", "--resource", type = str, help="Resource type (messages, memberships), default: all")
    parser.add_argument("-t", "--type", type = str, help="Event type (created, updated, deleted), default: all")
    parser.add_argument("-a", "--actor", type = str, help="Monitored actor id (user's e-mail), default: all")
    
    args = parser.parse_args()
    if args.verbose:
        if args.verbose > 2:
            logging.basicConfig(level=logging.DEBUG)
        elif args.verbose > 1:
            logging.basicConfig(level=logging.INFO)
        if args.verbose > 0:
            logging.basicConfig(level=logging.WARN)
            
    flask_app.logger.info("Logging level: {}".format(logging.getLogger(__name__).getEffectiveLevel()))
    
    flask_app.logger.info("Using database: {} - {}".format(os.getenv("DYNAMODB_ENDPOINT_URL"), os.getenv("DYNAMODB_TABLE_NAME")))
    
    wxt_compliance = args.compliance
    wxt_resource = args.resource
    wxt_type = args.type
    wxt_actor_email = args.actor
        
    start_runner()
    flask_app.run(host="0.0.0.0", port=5050)
