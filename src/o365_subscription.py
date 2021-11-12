from O365.utils import ApiComponent
from datetime import datetime, timedelta

class Subscription(ApiComponent):
    
    def __init__(self, account):
        # connection is only needed if you want to communicate with the api provider
        
        self.con = account.con
        protocol = account.protocol
        account.main_resource = "subscriptions"
        
        super().__init__(protocol=protocol, main_resource=account.main_resource)

    def list(self, params = None):
        # self.build_url just merges the protocol service_url with the enpoint passed as a parameter
        # to change the service_url implement your own protocol inherinting from Protocol Class
        url = self.build_url("")
        
        response = self.con.get(url, params = params)  # note the use of the connection here.

        # handle response and return to the user...

        return response
        
    def create(self, resource, changeType, notificationUrl, expiresIn=3600*24*7):
        url = self.build_url("")
        
        expiration = datetime.utcnow() + timedelta(0, expiresIn)
        
        req_params = {
            "changeType": changeType,
            "resource": resource,
            "notificationUrl": notificationUrl,
            "expirationDateTime": expiration.isoformat(timespec="milliseconds")+"Z",
            "clientState": "secretClientState"
        }
        
        response = self.con.post(url, data = req_params)
        
        return response

    def delete(self, subscriptionId):
        url = self.build_url("/"+subscriptionId)
        
        response = self.con.delete(url)
        
        return response
