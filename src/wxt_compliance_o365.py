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

"""
# avoid using a proxy for DynamoDB communication
import botocore.endpoint
def _get_proxies(self, url):
    return None
botocore.endpoint.EndpointCreator._get_proxies = _get_proxies
import boto3
from ddb_single_table_obj import DDB_Single_Table
"""

from O365 import Account, FileSystemTokenBackend
# from o365_db_token_storage import DBTokenBackend
from o365_group import Group

import json, requests
from datetime import datetime, timedelta, timezone
import time
from flask import Flask, request, redirect, url_for, Response, make_response
from flask.logging import default_handler

import concurrent.futures
import signal
import re
import base64

import buttons_cards as bc

logger = logging.getLogger()
logger.addHandler(default_handler)

from logging.config import dictConfig

# dictConfig({
#     'version': 1,
#     'formatters': {'default': {
#         'format': '[%(asctime)s] %(levelname)7s in %(module)s: %(message)s',
#     }},
    # 'handlers': {'wsgi': {
    #     'class': 'logging.StreamHandler',
    #     'stream': 'ext://flask.logging.wsgi_errors_stream',
    #     'formatter': 'default'
    # }},
    # 'root': {
    #     'level': 'INFO',
    #     'handlers': ['wsgi']
    # }
# })

flask_app = Flask(__name__)
flask_app.config["DEBUG"] = True
requests.packages.urllib3.disable_warnings()

# DynamoDB singleton. Needs to be initialized at the start of the application.
# ddb = None

# Webex integration scopes
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

# automatically added to any integration
DEFAULT_SCOPE = ["spark:kms"]

# MS Office MIME types
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
    
ALLOWED_MIME_TYPES_REGEX = [
    "image\/.*"
]

STATE_CHECK = "webex is great" # integrity test phrase

# timers
EVENT_CHECK_INTERVAL = 15 # delay in main loop
M365_GROUP_CHECK_INTERVAL = 15 # delay of M365 Group users sync to Webex Team
SAFE_TOKEN_DELTA = 3600 # safety seconds before access token expires - renew if smaller

# Graph API scopes
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

TIMESTAMP_KEY = "LAST_CHECK"

def sigterm_handler(_signo, _stack_frame):
    "When sysvinit sends the TERM signal, cleanup before exiting."

    flask_app.logger.info("Received signal {}, exiting...".format(_signo))
    
    thread_executor._threads.clear()
    concurrent.futures.thread._threads_queues.clear()
    sys.exit(0)

signal.signal(signal.SIGTERM, sigterm_handler)
signal.signal(signal.SIGINT, sigterm_handler)

STORAGE_PATH = "/token_storage/data/"
WEBEX_TOKEN_FILE = "webex_tokens_{}.json"
TIMESTAMP_FILE = "timestamp_{}.json"

thread_executor = concurrent.futures.ThreadPoolExecutor()
wxt_username = "COMPLIANCE"
wxt_user_id = None
wxt_token_key = "COMPLIANCE"
wxt_bot_id = None
token_refreshed = False
o365_account_changed = False

# default options for the application run
options = {
    "file_events": False,
    "notify": False,
    "m365_user_sync": False,
    "webex_user_sync": False,
    "check_aad_user": False,
    "check_actor": False,
    "skip_timestamp": False,
    "team_space_moderation": False,
    "language": "cs_CZ"
}

# statistics
statistics = {
    "started": datetime.utcnow(),
    "events": 0,
    "max_time": 0,
    "max_time_at": datetime.now(),
    "resources": {},
    "file_types": {
        "scanned": 0,
        "deleted": 0
    },
    "aad_check": {
        "checked": 0,
        "rejected": 0
    }
}

class AccessTokenAbs(AccessToken):
    """
    Store Access Token with a real timestamp.
    
    Access Tokens are generated with 'expires-in' information. In order to store them
    it's better to have a real expiration date and time. Timestamps are saved in UTC.
    Note that Refresh Token expiration is not important. As long as it's being used
    to generate new Access Tokens, its validity is extended even beyond the original expiration date.
    
    Attributes:
        expires_at (float): When the access token expires
        refresh_token_expires_at (float): When the refresh token expires.
    """
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
    """
    Save tokens.
    
    Parameters:
        tokens (AccessTokenAbs): Access & Refresh Token object
    """
    global token_refreshed
    
    flask_app.logger.debug("AT timestamp: {}".format(tokens.expires_at))
    token_record = {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_at": tokens.expires_at,
        "refresh_token_expires_at": tokens.refresh_token_expires_at
    }
    # ddb.save_db_record(token_key, "TOKENS", str(tokens.expires_at), **token_record)
    file_destination = get_webex_token_file(token_key)
    with open(file_destination, "w") as file:
        flask_app.logger.debug("Saving Webex tokens to: {}".format(file_destination))
        json.dump(token_record, file)
    
    token_refreshed = True # indicate to the main loop that the Webex token has been refreshed
    
def get_webex_token_file(token_key):
    return STORAGE_PATH + WEBEX_TOKEN_FILE.format(token_key)
    
def get_tokens_for_key(token_key):
    """
    Load tokens.
    
    Parameters:
        token_key (str): A key to the storage of the token
        
    Returns:
        AccessTokenAbs: Access & Refresh Token object or None
    """
    try:
        file_source = get_webex_token_file(token_key)
        with open(file_source, "r") as file:
            flask_app.logger.debug("Loading Webex tokens from: {}".format(file_source))
            token_data = json.load(file)
            tokens = AccessTokenAbs(token_data)
            return tokens
    except Exception as e:
        flask_app.logger.info("Webex token load exception: {}".format(e))
        return None

    """
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
    """

def refresh_tokens_for_key(token_key):
    """
    Run the Webex 'get new token by using refresh token' operation.
    
    Get new Access Token. Note that the expiration of the Refresh Token is automatically
    extended no matter if it's indicated. So if this operation is run regularly within
    the time limits of the Refresh Token (typically 3 months), the Refresh Token never expires.
    
    Parameters:
        token_key (str): A key to the storage of the token
        
    Returns:
        str: message indicating the result of the operation
    """
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
        
    return "Tokens refreshed for {}".format(token_key)
    
# O365
def get_o365_account(user_id, org_id, resource = None):
    """
    Initialize O365 Account object.
    
    The object is then used for calling Graph API. Both parameters are used as keys
    for Access and Refresh tokens storage.
    
    Parameters:
        user_id (str): User id (e-mail)
        org_id (str): O365 organization id.
        
    Returns:
        O365.Account: Account object
    """
    o365_client_id = os.getenv("O365_CLIENT_ID")
    o365_client_secret = os.getenv("O365_CLIENT_SECRET")
    o365_credentials = (o365_client_id, o365_client_secret)
    
    o365_tenant_id = os.getenv("O365_TENANT_ID")

    token_backend = FileSystemTokenBackend(token_path=STORAGE_PATH, token_filename='o365_token.txt')
    # token_backend = DBTokenBackend(user_id, "O365_GUEST_CHECK", org_id)
    args = {}
    if resource:
        args["resource"] = resource
    account = Account(o365_credentials, tenant_id = o365_tenant_id, token_backend=token_backend, auth_flow_type = "authorization", **args)
    
    flask_app.logger.debug("account {} is{} authenticated".format(user_id, "" if account.is_authenticated else " not"))

    return account
    
def get_o365_account_noauth():
    """
    Pre-initialize O365 Account object.
    
    Prepare the Account object for subsequent OAuth authorization.
    
    Returns:
        O365.Account: Account object    
    """
    o365_client_id = os.getenv("O365_CLIENT_ID")
    o365_client_secret = os.getenv("O365_CLIENT_SECRET")
    o365_credentials = (o365_client_id, o365_client_secret)

    o365_tenant_id = os.getenv("O365_TENANT_ID")

    account = Account(o365_credentials, tenant_id = o365_tenant_id, auth_flow_type = "authorization")
    
    flask_app.logger.debug("get O365 account without authentication")

    return account
    
def o365_check_token():
    """
    Check the validity of the O365 access token
    
    Run an OAuth refresh token operation and save the token. Verify if the token
    works by running a dummy Graph API request.
    """
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
            o365_account_changed = True # indicate to the main loop that the O365 token has been refreshed

    # query_condition = "$filter=userType eq 'Guest' and mail eq '{}'".format(event.data.personEmail)
    query_condition = "userType eq 'Guest' and mail eq 'nonexistent@perlovka.guru'"
    aad = account.directory()
    user_dir = aad.get_users(query = query_condition)
    
    for user in user_dir:
        flask_app.logger.info("AAD dummy query result: {}".format([user.mail, user.user_principal_name, user.display_name]))
    
def save_timestamp(timestamp_key, timestamp):
    """
    Save a timestamp.
    
    Parameters:
        timestamp_key (str): storage key for the timestamp
        timestamp (float): datetime timestamp
    """
    timestamp_destination = get_timestamp_file(timestamp_key)
    flask_app.logger.debug("Saving timestamp to {}".format(timestamp_destination))
    with open(timestamp_destination, "w") as file:
        json.dump({"timestamp": timestamp}, file)
    
    # ddb.save_db_record(timestamp_key, "TIMESTAMP", timestamp)
    
def load_timestamp(timestamp_key):
    """
    Save a timestamp.
    
    Parameters:
        timestamp_key (str): storage key for the timestamp
        
    Returns:
        float: timestamp for datetime
    """
    timestamp_source = get_timestamp_file(timestamp_key)
    flask_app.logger.debug("Loading timestamp from {}".format(timestamp_source))
    try:
        with open(timestamp_source, "r") as file:
            ts = json.load(file)
            return float(ts.get("timestamp"))
    except Exception as e:
        flask_app.logger.info("Timestamp load exception: {}".format(e))
        return None
    
    """
    db_timestamp = ddb.get_db_record(timestamp_key, "TIMESTAMP")
    flask_app.logger.debug("Loaded timestamp from db: {}".format(db_timestamp))
    
    try:
        res = float(db_timestamp["pvalue"])
        return res
    except Exception as e:
        flask_app.logger.debug("timestamp exception: {}".format(e))
        return None
    """
        
def get_timestamp_file(timestamp_key):
    return STORAGE_PATH + TIMESTAMP_FILE.format(timestamp_key)
    
def secure_scheme(scheme):
    return re.sub(r"^http$", "https", scheme)
        
# Flask part of the code

"""
1. initialize database table if needed
2. start event checking thread
"""
@flask_app.before_first_request
def startup():
    """
    Initialize the application.
    
    Create DynamoDB storage singleton. Start the main loop thread.
    """
    """
    global ddb
    
    ddb = DDB_Single_Table()
    flask_app.logger.debug("initialize DDB object {}".format(ddb))
    """
    
    flask_app.logger.debug("Starting event check...")
    # check_events(EVENT_CHECK_INTERVALl)
    thread_executor.submit(check_events, EVENT_CHECK_INTERVAL)
    # o365_check_token()

@flask_app.route("/")
def hello():
    """
    A dummy URL.
    
    Used for a dummy request which initializes the application. See start_runner() below.
    
    Returns:
        str: something highly informative
    """
    response = make_response(format_event_stats(), 200)
    response.mimetype = "text/plain"
    return response

"""
OAuth proccess done
"""
@flask_app.route("/authdone", methods=["GET"])
def authdone():
    """
    Landing page for the OAuth authorization process.
    
    Used to hide the OAuth response URL parameters.
    """
    ## TODO: post the information & help, maybe an event creation form to the 1-1 space with the user
    return "Thank you for providing the authorization. You may close this browser window."

@flask_app.route("/authorize", methods=["GET"])
def authorize():
    """
    Start the Webex OAuth grant flow.
    
    See: https://developer.webex.com/docs/integrations
    Note that scopes and redirect URI of your integration have to match this application.
    """
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
    
@flask_app.route("/manager", methods=["GET"])
def manager():
    """
    Webex OAuth grant flow redirect URL
    
    Generate access and refresh tokens using 'code' generated in OAuth grant flow
    after user successfully authenticated to Webex

    See: https://developer.webex.com/blog/real-world-walkthrough-of-building-an-oauth-webex-integration
    https://developer.webex.com/docs/integrations
    """   

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
        
    # hide the original redirect URL and its parameters from the user's browser
    return redirect(url_for("authdone"))
    
@flask_app.route('/o365auth')
def o365_auth():
    """
    O365 OAuth grant flow
    
    Note that scopes and redirect URI of your Enterprise Application have to match this application.
    """

    my_state = request.args.get("state", "local")
    flask_app.logger.debug("input state: {}".format(my_state))
    
    myUrlParts = urlparse(request.url)
    full_redirect_uri = secure_scheme(myUrlParts.scheme) + "://" + myUrlParts.netloc + url_for("o365_do_auth")
    # full_redirect_uri = myUrlParts.scheme + "://" + myUrlParts.netloc + url_for("o365_do_auth")
    flask_app.logger.debug("Authorize redirect URL: {}".format(full_redirect_uri))

    # callback = quote(full_redirect_uri, safe="")
    callback = full_redirect_uri
    scopes = O365_SCOPE
    
    account = get_o365_account_noauth()

    url, o365_state = account.con.get_authorization_url(requested_scopes=scopes, redirect_uri=callback)
    
    # the state must be saved somewhere as it will be needed later
    # my_db.store_state(state) # example...

    # do not bother saving the state, replace "state" parameter injected by O365 object
    o365_auth_parts = urlparse(url)
    o365_query = dict(parse_qsl(o365_auth_parts.query))
    o365_query["state"] = my_state
    new_o365_auth_parts = o365_auth_parts._replace(query = urlencode(o365_query))
    new_o365_url = urlunparse(new_o365_auth_parts)
    
    flask_app.logger.debug("O365 auth URL: {}".format(new_o365_url))

    return redirect(new_o365_url)

@flask_app.route('/o365doauth')
def o365_do_auth():
    """
    Webex OAuth grant flow redirect URL
    """
    global o365_account_changed
    
    my_state = request.args.get("state", O365_LOCAL_USER_KEY)
    flask_app.logger.debug("O365 state: {}".format(my_state))
    
    account = get_o365_account(my_state, O365_ACCOUNT_KEY) # person_data.orgId
    
    # retreive the state saved in auth_step_one
    # my_saved_state = my_db.get_state()  # example...

    # rebuild the redirect_uri used in auth_step_one
    myUrlParts = urlparse(request.url)
    full_redirect_uri = secure_scheme(myUrlParts.scheme) + "://" + myUrlParts.netloc + url_for("o365_do_auth")
    # full_redirect_uri = myUrlParts.scheme + "://" + myUrlParts.netloc + url_for("o365_do_auth")
    flask_app.logger.debug("Authorize doauth redirect URL: {}".format(full_redirect_uri))

    # callback = quote(full_redirect_uri, safe="")
    callback = full_redirect_uri
    # AzureAD allows only https redirect URIs
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
    
@flask_app.route("/o365wh", methods=["GET", "POST"])
def o365_webhook():
    """
    Graph API webhook example
    
    See: https://docs.microsoft.com/en-us/graph/api/resources/subscription
    """
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

def check_events(check_interval=EVENT_CHECK_INTERVAL):
    """
    Check events API thread.
    
    Infinite loop which periodically checks the Events API.
    Doesn't work until "wxt_username" runs through OAuth grant flow above.
    Access token is automatically refreshed if needed using Refresh Token.
    No additional user authentication is required.
    """
    global wxt_username, wxt_user_id, wxt_bot_id, token_refreshed, o365_account_changed, options

    # TODO:
    # 1. threading
    # 2. check how many reponses are returned (max = 100)

    # As it runs as a thread, exceptions do not show on console.
    # Capture any exception and keep the thread running
    try:
        tokens = None
        wxt_client = None
        
        xargs = {}
        
        # check events from the last saved timestamp or from the application start
        if options["skip_timestamp"]:
            last_timestamp = None
        else:
            # load last timestamp from DB
            last_timestamp = load_timestamp(TIMESTAMP_KEY)
        
        if last_timestamp is None:
            from_time = datetime.utcnow()
        else:
            from_time = datetime.fromtimestamp(last_timestamp)

        o365_token_last_check = datetime.utcnow()
        o365_account = get_o365_account(O365_LOCAL_USER_KEY, O365_ACCOUNT_KEY)
        
        m365_group_last_check = datetime.utcnow()
    except Exception as e:
        flask_app.logger.error("check_events() start exception: {}".format(e))
    
    try:
        # the Bot sends messages to users and runs some Team operations
        wxt_bot = WebexTeamsAPI(access_token = os.getenv("BOT_ACCESS_TOKEN"))
        wxt_bot_info = wxt_bot.people.me()
        wxt_bot_id = wxt_bot_info.id
        flask_app.logger.info("Messages will be sent under {}({}) identity".format(wxt_bot_info.displayName, wxt_bot_info.emails[0]))
    except ApiError as e:
        flask_app.logger.error("Webex Bot API request error: {}".format(e))

    while True:
        try:
            # flask_app.logger.debug("Check events tick.")

    # check for token until there is one available in the DB        
            if tokens is None or token_refreshed:
                tokens = get_tokens_for_key(wxt_token_key)
                if tokens:
                    wxt_client = WebexTeamsAPI(access_token=tokens.access_token)

                    user_info = wxt_client.people.me()
                    flask_app.logger.debug("Got user info: {}".format(user_info))
                    wx_org_id = user_info.orgId
                    wxt_username = user_info.emails[0]
                    wxt_user_id = user_info.id
                    
                    token_refreshed = False
                else:
                    flask_app.logger.error("No access tokens for key {}. Authorize the user first.".format(wxt_token_key))
                    
            if tokens:
    # renew access token using refresh token if needed
                token_delta = datetime.fromtimestamp(float(tokens.expires_at)) - datetime.utcnow()
                if token_delta.total_seconds() < SAFE_TOKEN_DELTA:
                    flask_app.logger.info("Access token is about to expire, renewing...")
                    refresh_tokens_for_key(wxt_token_key)
                    tokens = get_tokens_for_key(wxt_token_key)
                    wxt_client = WebexTeamsAPI(access_token=tokens.access_token)
                    new_client = True
                    
            if o365_account_changed:
                o365_account = get_o365_account(O365_LOCAL_USER_KEY, O365_ACCOUNT_KEY)
                o365_account_changed = False

            to_time = datetime.utcnow()
    # query the Events API        
            if wxt_client:
                try:
                    from_stamp = from_time.isoformat(timespec="milliseconds")+"Z"
                    to_stamp = to_time.isoformat(timespec="milliseconds")+"Z"
                    flask_app.logger.debug("check interval {} - {}".format(from_stamp, to_stamp))
                    event_list = wxt_client.events.list(_from=from_stamp, to=to_stamp, **xargs)
                    # TODO: do this in thread max_workers=5
                    flask_app.logger.debug("event handling start at: {}".format(datetime.utcnow().isoformat(timespec="milliseconds")+"Z"))
                    config = load_config(options)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as event_executor:
                        for event in event_list:
                            if event.actorId in (wxt_user_id, wxt_bot_id):
                                flask_app.logger.debug("ignore my own action")
                            else:
                                event_executor.submit(handle_event, event, wxt_client, wxt_bot, o365_account, options, config)
                    flask_app.logger.debug("event handling end at: {}".format(datetime.utcnow().isoformat(timespec="milliseconds")+"Z"))
                    
                except ApiError as e:
                    flask_app.logger.error("API request error: {}".format(e))
                finally:
                    from_time = to_time

            # verify and renew the O365 token
            if (datetime.utcnow() - o365_token_last_check).total_seconds() > O365_API_CHECK_INTERVAL:
                o365_check_token()
                o365_token_last_check = datetime.utcnow()
                
            # synchronize M365 Group members to Webex Teams with the same name
            if (options["m365_user_sync"] or options["webex_user_sync"]) and (datetime.utcnow() - m365_group_last_check).total_seconds() > M365_GROUP_CHECK_INTERVAL:
                # TODO:
                # 1. load all Wx Teams
                # 2. load all M365 Groups - name + id only
                # 3. compare display name, sync all M365 users -> Webex where name matches
                wxt_team_generator = wxt_bot.teams.list()
                m365_group_list = find_o365_group(o365_account)
                flask_app.logger.debug("Existing M365 Groups: {}".format(m365_group_list))
                for wxt_team in wxt_team_generator:
                    for m365_group in m365_group_list:
                        if wxt_team.name == m365_group["displayName"]:
                            flask_app.logger.debug("Found matching Webex Team & M365 Group: {}".format(wxt_team.name))
                            # TODO: sync team membership
                            wxt_team_member_generator = wxt_bot.team_memberships.list(wxt_team.id)
                            m365_group_member_list = get_o365_group_members(o365_account, m365_group["id"])
                            flask_app.logger.debug("M365 Group members: {}".format(m365_group_member_list))
                            for wxt_team_member in wxt_team_member_generator:
                                user_found = False
                                for i in range(0, len(m365_group_member_list)):
                                    if wxt_team_member.personEmail == m365_group_member_list[i]["mail"]:
                                        flask_app.logger.info("User {} on both sides, skipping...".format(wxt_team_member.personEmail))
                                        user_found = True
                                        break
                                if user_found:
                                    del m365_group_member_list[i]
                                elif options["m365_user_sync"]:
                                    if wxt_team_member.isModerator:
                                        flask_app.logger.info("User {} not found in M365 Group, however he's moderator, skipping...".format(wxt_team_member.personEmail))
                                    else:
                                        flask_app.logger.info("User {} not found in M365 Group, deleting from Webex Team...".format(wxt_team_member.personEmail))
                                        wxt_bot.team_memberships.delete(wxt_team_member.id)
                                                    
                            if options["m365_user_sync"]:
                                flask_app.logger.info("Users missing in the Webex Team {}, adding to Webex Team...".format(m365_group_member_list))
                                for m365_group_member in m365_group_member_list:
                                    flask_app.logger.info("Adding user {} to the Webex Team".format(m365_group_member["mail"]))
                                    wxt_bot.team_memberships.create(wxt_team.id, personEmail = m365_group_member["mail"])
                                
                            break
                
                m365_group_last_check = datetime.utcnow()

            # save timestamp
            save_timestamp(TIMESTAMP_KEY, to_time.timestamp())
            now_check = datetime.utcnow()
            diff = (now_check - to_time).total_seconds()
            flask_app.logger.info("event processing took {} seconds".format(diff))
            if diff > statistics["max_time"]:
                statistics["max_time"] = diff
                statistics["max_time_at"] = datetime.now()
            if diff < check_interval:
                time.sleep(check_interval - int(diff))
            else:
                flask_app.logger.error("EVENT PROCESSING IS TAKING TOO LONG ({}), PERFORMANCE IMPROVEMENT NEEDED".format(diff))
        except Exception as e:
            flask_app.logger.error("check_events() loop exception: {}".format(e))
            time.sleep(check_interval)
        finally:
            pass
            
def handle_event(event, wxt_client, wxt_bot, o365_account, options, config):
    """
    Handle Webex Events API query result
    """
    global statistics
    
    try:
        actor = wxt_client.people.get(event.actorId)
        
        # if we run in a test mode (--check_actor option), the actions take place
        # only for configured users
        if options["check_actor"]:
            actor_list = config.get("actors")
            flask_app.logger.debug("configured actors: {}".format(actor_list))
            if not any(actor.emails[0].lower() in act_member.lower() for act_member in actor_list):
                flask_app.logger.info("{} ({}) not in configured actor list".format(actor.displayName, actor.emails[0]))
                return
        
        save_event_stats(event)

        if event.resource != "messages":
            flask_app.logger.info("Event: {}".format(event))
                    
        room_info = wxt_client.rooms.get(event.data.roomId)
        room_id = base64.b64decode(room_info.id)
        room_uuid = room_id.decode("ascii").split("/")[-1] # uuid is the last element of room id
        
        flask_app.logger.info("Room info: {}".format(room_info))
        
        # Space membership change
        # there is an additional set of actions if a new Team is created
        if event.resource == "memberships" and event.type in ["created","deleted"] and room_info.type == "group" and not event.actorId == wxt_user_id:
            event_in_general_space = False
            new_team = False
            if event.type == "created" and room_info.teamId:
                # make sure Bot is a moderator of the Team
                flask_app.logger.info("Make sure Bot is a Team moderator")
                bot_added_to_team = add_moderator(room_info, wxt_client, wxt_bot, wxt_bot_id)
                team_info = wxt_client.teams.get(room_info.teamId)
                team_id = base64.b64decode(team_info.id)
                team_uuid = team_id.decode("ascii").split("/")[-1] # uuid is the last element of team id
                
                event_in_general_space = team_uuid == room_uuid
                new_team = event_in_general_space and team_info.creatorId == event.data.personId
                flask_app.logger.info(f"event in general space: {event_in_general_space}, new team: {new_team}")
            if event.type == "created" and room_info.creatorId == event.data.personId:                             
                # new team/space created
                flask_app.logger.info("New {} created".format("Team" if new_team else "Space"))
                
                # make the Space moderated if it's part of a Team
                if options["team_space_moderation"] and room_info.teamId:
                    try:
                        flask_app.logger.info(f"Assign {event.data.personEmail} as a Space moderator")
                        wxt_bot.memberships.create(roomId = room_info.id, personId = wxt_bot_id, isModerator = True)
                        wxt_bot.memberships.update(event.data.id, isModerator = True)
                    except ApiError as e:
                        flask_app.logger.info("Update membership error: {}".format(e))
                    
                if options["notify"]:
                    flask_app.logger.debug("Send compliance message")
                    xargs = {
                        "attachments": [bc.wrap_form(bc.nested_replace_dict(bc.localize(bc.SP_WARNING_FORM, options["language"]), {"url_onedrive_link": os.getenv("URL_ONEDRIVE_LINK")}))]
                    }
                    msg = "Jestliže budete v tomto Prostoru sdílet dokumenty, připojte k němu SharePoint úložiště. Návod najdete zde: https://help.webex.com/cs-cz/n4ve41eb/Webex-Link-a-Microsoft-OneDrive-or-SharePoint-Online-Folder-to-a-Space"
                    if room_info.teamId and bot_added_to_team:                            
                        wxt_bot.messages.create(roomId = room_info.id, markdown = msg, **xargs)                                                        
                    else:
                        send_compliance_message(wxt_bot, wxt_bot_id, event.data.roomId, msg,
                            xargs, act_on_behalf_client = wxt_client, act_on_behalf_client_id = wxt_user_id)
                        
            # check if a newly added user has an account in AzureAD
            if event.type == "created" and event_in_general_space and options["check_aad_user"] and event.data.personId != wxt_bot_id:
                user_account = get_o365_user_account(o365_account, event.data.personEmail)
                statistics["aad_check"]["checked"] += 1
                if not user_account:
                    flask_app.logger.info("user {} not found in directory".format(event.data.personEmail))
                    if hasattr(event.data, "personDisplayName"):
                        display_name = event.data.personDisplayName
                    else:
                        display_name = ""
                    form = bc.nested_replace_dict(bc.localize(bc.USER_WARNING_FORM, options["language"]), {"display_name": display_name, "email": event.data.personEmail, "group_name": team_info.name, "url_idm": os.getenv("URL_IDM"), "url_idm_guide": os.getenv("URL_IDM_GUIDE")})
                    wxt_bot.messages.create(roomId = event.data.roomId, markdown = "Uživatel nemá O365 účet.", attachments = [bc.wrap_form(form)])
                    flask_app.logger.info("Deleting team membership for user {}".format(event.data.personEmail))
                    wxt_bot.memberships.delete(event.data.id)
                    statistics["aad_check"]["rejected"] += 1
                    
            # check if the membership changed on the Team level, list O365 Groups, find a group with the same displayName, find a user's account based on the e-mail (maybe a guest account), update group membership
            if room_info.teamId and options["webex_user_sync"]:
                flask_app.logger.info("Check O365 Group relationship")
                if not team_info:
                    team_info = wxt_bot.teams.get(room_info.teamId)
                o365_group = find_o365_group(o365_account, team_info.name)
                if o365_group:
                    flask_app.logger.info("Team name {}, o365 group: {}".format(team_info.name, o365_group))
                    if not user_account:
                        user_account = get_o365_user_account(o365_account, event.data.personEmail)
                    if user_account:
                        if event.type == "created":
                            flask_app.logger.info("add o365 group member: {}".format(user_account["user_info"].user_principal_name))
                            add_o365_group_member(o365_account, o365_group["id"], user_account["user_info"].object_id)
                        else:
                            flask_app.logger.info("delete o365 group member: {}".format(user_account["user_info"].user_principal_name))
                            delete_o365_group_member(o365_account, o365_group["id"], user_account["user_info"].object_id)
                else:
                    flask_app.logger.info("No corresponding O365 Group for Team \"{}\"".format(team_info.name))
                        
        # new message
        # check the attached files, delete the message if any file type violates the sharing policy
        if event.resource == "messages" and event.type == "created" and not event.actorId == wxt_user_id:
            # message_info = wxt_client.messages.get(event.data.id)
            # flask_app.logger.info("Message info: {}".format(message_info))
            if options["file_events"] and hasattr(event.data, "files"):
                hdr = {"Authorization": "Bearer " + wxt_client.access_token}
                for url in event.data.files:
                    statistics["file_types"]["scanned"] += 1
                    file_info = requests.head(url, headers = hdr)
                    flask_app.logger.info("Message file: {}\ninfo: {}".format(url, file_info.headers))
                    
                    # check for disallowed MIME types
                    """
                    allowed_found = True
                    if file_info.headers["Content-Type"] in SUSPECT_MIME_TYPES:
                        allowed_found = False
                    """
                    
                    # check for allowed MIME types
                    allowed_found = False
                    for allowed_regex in ALLOWED_MIME_TYPES_REGEX:
                        if re.match(allowed_regex, file_info.headers["Content-Type"]):
                            allowed_found = True
                            break
                            
                    if not allowed_found:
                        statistics["file_types"]["deleted"] += 1
                        wxt_client.messages.delete(event.data.id)
                        xargs = {
                            "attachments": [bc.wrap_form(bc.nested_replace_dict(bc.localize(bc.SP_LINK_FORM, options["language"]), {"url_onedrive_link": os.getenv("URL_ONEDRIVE_LINK")}))]
                        }
                        send_compliance_message(wxt_bot, wxt_bot_id, event.data.roomId,
                            "Odeslal jste typ dokumentu, který podléhá klasifikaci. **Připojte k tomuto Prostoru SharePoint úložiště a dokument pošlete znovu.** Návod najdete zde: https://help.webex.com/cs-cz/n4ve41eb/Webex-Link-a-Microsoft-OneDrive-or-SharePoint-Online-Folder-to-a-Space",
                            xargs, act_on_behalf_client = wxt_client, act_on_behalf_client_id = wxt_user_id)          
    except Exception as e:
        flask_app.logger.error("handle_event() exception: {}".format(e))

def add_moderator(room_info, wxt_client, bot_api, bot_id):
    bot_team_membership = None
    bot_added_to_team = False
    try:
        bot_team_membership_list = bot_api.team_memberships.list(room_info.teamId)
        for team_membership in bot_team_membership_list:
            if team_membership.personId == bot_id:
                bot_team_membership = team_membership
                flask_app.logger.info("existing team membership: {}".format(bot_team_membership))
                break
    except ApiError as e:
        flask_app.logger.info("Bot Team membership doesn't exist")
        
    if not bot_team_membership:
        # somehow team membership API doesn't work
        # my_team_membership = wxt_client.team_memberships.create(room_info.teamId, personId = wxt_user_id, isModerator = True)
        flask_app.logger.debug("Adding myself as Team moderator")
        my_membership = wxt_client.memberships.create(roomId = room_info.id, personId = wxt_user_id, isModerator = True)
        flask_app.logger.debug("Adding bot as Team moderator")
        try:
            bot_team_membership = wxt_client.team_memberships.create(room_info.teamId, personId = bot_id, isModerator = True)
            bot_added_to_team = True
        except ApiError as e:
            flask_app.logger.error("Bot Team membership not created: {}".format(e))
            
        flask_app.logger.debug("Removing myself as Team moderator")
        wxt_client.memberships.delete(my_membership.id)
        
    return bot_added_to_team
        
def save_event_stats(event):
    """
    Save statistics
    
    Saves statistics to a "statistics" singleton
    
    Parameters:
        event (Event): Event API response object
    """
    global statistics
    
    statistics["events"] += 1
    counter_ref = statistics["resources"].get(event.resource)
    if counter_ref is None:
        statistics["resources"][event.resource] = {}
        counter = 0
    else:
        counter = counter_ref.get(event.type, 0)
    counter += 1
    flask_app.logger.debug("save_event_stats() counter for {}/{} is now: {}".format(event.resource, event.type, counter))
    statistics["resources"][event.resource][event.type] = counter
    
def format_event_stats():
    """
    Format event statistics for print
    
    Returns:
        str: formatted statistics
    """
    global statistics
    
    res_str = ""
    for res_key, res_value in statistics["resources"].items():
        res_str += "{}:\n".format(res_key)
        for type_key, type_value in statistics["resources"][res_key].items():
            res_str += "{:<4}{:>14}:{:8d}\n".format("", type_key, type_value)
            
    for other_key in ("file_types", "aad_check"):
        res_str += "{}:\n".format(other_key)        
        for f_key, f_value in statistics[other_key].items():
            res_str += "{:<4}{:>14}:{:8d}\n".format("", f_key, f_value)
            
    start_time = "{:%Y-%m-%d %H:%M:%S GMT}".format(statistics["started"])
    max_timestamp = "{:%Y-%m-%d %H:%M:%S}".format(statistics["max_time_at"])
    now = datetime.utcnow()
    time_diff = now - statistics["started"]
    hours, remainder = divmod(time_diff.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    diff_time = "{}d {:02d}:{:02d}:{:02d}".format(time_diff.days, int(hours), int(minutes), int(seconds))
    result = """Compliance Monitor

Started: {}
Up: {}

Event statistics
Total events: {}
Maximum processing time: {:0.2f}s at {}
{}
""".format(start_time, diff_time, statistics["events"], statistics["max_time"], max_timestamp, res_str)
    
    return result
            
def send_compliance_message(wxt_client, wxt_user_id, room_id, message, xargs, act_on_behalf_client = None, act_on_behalf_client_id = None):
    """
    Send a compliance message + card
    
    The function makes sure the wxt_user_id is a member of the Space to which the message is sent.
    
    Parameters:
        wxt_client (WebexTeamsAPI): API client which sends the message
        wxt_user_id (str): ID of the API client user
        room_id (str): ID of the room to which the message is sent
        message (str): text of the message
        xargs (dict): additional parameters for wxt_client.messages.create() call
        act_on_behalf_client (WebexTeamsAPI): API client with Compliance permissions which can be needed to add wxt_user_id to the Space
        act_on_behalf_client_id (str): act_on_behalf_client's Compliance API user ID
    """
    membership_found = False
    try:
        existing_membership_generator = wxt_client.memberships.list(roomId = room_id, personId = wxt_user_id)
        for existing_membership in existing_membership_generator:
            membership_found = True
            flask_app.logger.info("found existing membership: {}".format(existing_membership))
    except ApiError as e:
        flask_app.logger.debug("client's (Bot) membership not found")
    
    if not membership_found:
        actor_client = act_on_behalf_client if act_on_behalf_client else wxt_client

        my_membership_list = actor_client.memberships.list(roomId = room_id, personId = wxt_user_id)
        my_membership = None
        for my_membership in my_membership_list:
            flask_app.logger.info("existing membership: {}".format(my_membership))
        if not my_membership:
            if act_on_behalf_client_id:
                proxy_membership = actor_client.memberships.create(roomId = room_id, personId = act_on_behalf_client_id)
            my_membership = actor_client.memberships.create(roomId = room_id, personId = wxt_user_id)
            if act_on_behalf_client_id:
                proxy_membership = actor_client.memberships.delete(proxy_membership.id)
        
    wxt_client.messages.create(roomId = room_id, markdown = message, **xargs)

    # remove Bot from the Space
    # if not membership_found:
    #     wxt_client.memberships.delete(my_membership.id)
    
def find_o365_group(o365_account, group_name = None):
    """
    Find M365 Group by name
    
    Parameters:
        o365_account (O365.Account): account used to query the Graph API
        group_name (str): a group name to search for
        
    Returns:
        dict: JSON structure returned by the query
    """
    filter = {"$select": "id, displayName"}
    if group_name:
        filter["$filter"] = "displayName eq '{}'".format(group_name)
    grp = Group(o365_account)
    result = grp.list(params = filter)
    
    if result.ok:
        res_json = result.json()
        if group_name:
            try:
                return res_json["value"][0]
            except IndexError:
                return None
        else:
            return res_json["value"]
    else:
        return None
        
def get_o365_user_account(o365_account, email):
    """
    Find a Guest user account from AzureAD
    
    Search AzureAD for a Guest account with a corresponding e-mail address
    
    Parameters:
        o365_account (O365.Account): account used to query the Graph API
        email (str): user's e-mail address
        
    Returns:
        user object
    """
    EXT_USER_INCLUDE = "#EXT#@"
    
    query_condition = "mail eq '{}'".format(email)
    aad = o365_account.directory()
    user_dir = aad.get_users(query = query_condition)

    for user in user_dir:
        result = {"user_info": user, "guest": True if user.user_principal_name.find(EXT_USER_INCLUDE) > 0 else False}
        return result

def add_o365_group_member(o365_account, group_id, user_id):
    """
    Add a user to M365 Group
    
    Parameters:
        o365_account (O365.Account): account used to query the Graph API
        user_id (str): user's ID (ObjectID) from AzureAD
        
    Returns:
        bool: Operations result
    """
    grp = Group(o365_account)
    result = grp.add_member(group_id, user_id)
    
    return result.ok

def delete_o365_group_member(o365_account, group_id, user_id):
    """
    Remove a user from M365 Group
    
    Parameters:
        o365_account (O365.Account): account used to query the Graph API
        user_id (str): user's ID (ObjectID) from AzureAD
        
    Returns:
        bool: Operations result
    """
    grp = Group(o365_account)
    result = grp.delete_member(group_id, user_id)
    
    return result.ok
    
def get_o365_group_members(o365_account, group_id):
    """
    Get M365 Group members
    
    Parameters:
        o365_account (O365.Account): account used to query the Graph API
        group_id (str): group ID from AzureAD
        
    Returns:
        dict: list of group members
    """
    filter = {"$select": "id, displayName, mail"}
    grp = Group(o365_account)
    result = grp.members(group_id, params = filter)
    
    if result.ok:
        res_json = result.json()
        return res_json["value"]
        
def load_config(options):
    """
    Load the configuration file.
    
    Returns:
        dict: configuration file JSON
    """
    with open("/config/config.json") as file:
        config = json.load(file)
    
    opt = config.get("options", {})
    for key, value in opt.items():
        options[key] = value
    return config
        
def start_runner():
    """
    Independent thread startup, see:
    https://networklore.com/start-task-with-flask/
    """
    def start_loop():
        no_proxies = {
          "http": None,
          "https": None,
        }
        not_started = True
        while not_started:
            logger.info('In start loop')
            try:
                r = requests.get('https://127.0.0.1:5050/', proxies=no_proxies, verify=False)
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
    
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='count', help="Set logging level by number of -v's, -v=WARN, -vv=INFO, -vvv=DEBUG")
    parser.add_argument("-f", "--file_events", action='store_true', help="Monitor file events, default: no")
    parser.add_argument("-n", "--notify", action='store_true', help="Send notification when creating a new Space, default: no")
    parser.add_argument("-m", "--m365_user_sync", action='store_true', help="Sync M365 Group members to Webex Team of the same name, default: no")
    parser.add_argument("-c", "--check_aad_user", action='store_true', help="Check if a newly added user to a Webex Team has an account in Azure AD, default: no")
    parser.add_argument("-w", "--webex_user_sync", action='store_true', help="Sync Webex Team members to M365 Group of the same name, default: no")
    parser.add_argument("-a", "--check_actor", action='store_true', help="Perform actions only if the Webex Event actor is in the \"actors\" list from the /config/config.json file, default: no")
    parser.add_argument("-s", "--skip_timestamp", action='store_true', help="Ignore stored timestamp and monitor the events just from the application start, default: no")
    parser.add_argument("-t", "--team_space_moderation", action='store_true', help="Implicit team space moderation - any Space inside a Team is moderated by its creator, default: no")
    parser.add_argument("-l", "--language", default = "cs_CZ", help="Language (see localization_strings.LANGUAGE), default: cs_CZ")
    
    args = parser.parse_args()
    if args.verbose:
        if args.verbose > 2:
            logging.basicConfig(level=logging.DEBUG)
        elif args.verbose > 1:
            logging.basicConfig(level=logging.INFO)
        if args.verbose > 0:
            logging.basicConfig(level=logging.WARN)
            
    flask_app.logger.info("Logging level: {}".format(logging.getLogger(__name__).getEffectiveLevel()))
    
    flask_app.logger.info("TESTVAR: {}".format(os.getenv("TESTVAR")))
    
    options["file_events"] = args.file_events
    options["notify"] = args.notify
    options["m365_user_sync"] = args.m365_user_sync
    options["webex_user_sync"] = args.webex_user_sync
    options["check_aad_user"] = args.check_aad_user
    options["check_actor"] = args.check_actor
    options["skip_timestamp"] = args.skip_timestamp
    options["team_space_moderation"] = args.team_space_moderation
    options["language"] = args.language
        
    config = load_config(options)

    flask_app.logger.info("OPTIONS: {}".format(options))
    
    flask_app.logger.info("CONFIG: {}".format(config))

    start_runner()
    flask_app.run(host="0.0.0.0", port=5050, ssl_context='adhoc')
