# dotenv -f .env_docker run python -i o365_interactive.py
#
# f = {'$filter': "displayName eq 'test.the.dots'", "$select": "id, displayName"}
# f = {"$filter": "id eq '1a82c59c-31c5-4c82-ab96-204fde4db4d5'"}

import os
import logging
from O365 import Account, FileSystemTokenBackend, Connection, MSGraphProtocol
from o365_db_token_storage import DBTokenBackend
from o365_group import Group

def get_o365_account(user_id, org_id, main_resource = None):
    o365_client_id = os.getenv("O365_CLIENT_ID")
    o365_client_secret = os.getenv("O365_CLIENT_SECRET")
    o365_credentials = (o365_client_id, o365_client_secret)
    
    o365_tenant_id = os.getenv("O365_TENANT_ID")

    token_backend = DBTokenBackend(user_id, "O365_GUEST_CHECK", org_id)
    args = {}
    if main_resource:
        args["main_resource"] = main_resource
    account = Account(o365_credentials, tenant_id = o365_tenant_id, token_backend=token_backend, auth_flow_type = "authorization", **args)
    
    logging.info("account {} is{} authenticated".format(user_id, "" if account.is_authenticated else " not"))

    return account
    
O365_LOCAL_USER_KEY = "LOCAL"
O365_ACCOUNT_KEY = "GENERIC"

logging.basicConfig(level = logging.INFO)
logging.getLogger().setLevel(logging.INFO)

if __name__ == "__main__":
    account = get_o365_account(O365_LOCAL_USER_KEY, O365_ACCOUNT_KEY)
    
    grp = Group(account)
