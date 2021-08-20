from O365.utils import ApiComponent 

class Group(ApiComponent):
    
    def __init__(self, account):
        # connection is only needed if you want to communicate with the api provider
        
        self.con = account.con
        protocol = account.protocol
        account.main_resource = "groups"
        
        super().__init__(protocol=protocol, main_resource=account.main_resource)

    def get(self, group_id, params = None):
        
        # self.build_url just merges the protocol service_url with the enpoint passed as a parameter
        # to change the service_url implement your own protocol inherinting from Protocol Class
        url = self.build_url("/"+group_id)
        
        response = self.con.get(url, params = params)  # note the use of the connection here.

        # handle response and return to the user...

        return response
        
    def members(self, group_id, params = None):
        
        # self.build_url just merges the protocol service_url with the enpoint passed as a parameter
        # to change the service_url implement your own protocol inherinting from Protocol Class
        url = self.build_url("/"+group_id+"/members")
        
        response = self.con.get(url, params = params)  # note the use of the connection here.

        # handle response and return to the user...

        return response
        
    def add_member(self, group_id, member_id):
        url = self.build_url("/"+group_id+"/members/$ref")
        
        member = {"@odata.id": "https://graph.microsoft.com/v1.0/directoryObjects/{}".format(member_id)}
        
        response = self.con.post(url, json = member)  # note the use of the connection here.

        # handle response and return to the user...

        return response
            
    def delete_member(self, group_id, member_id):
        url = self.build_url("/"+group_id+"/members/"+member_id+"/$ref")
        
        response = self.con.delete(url)  # note the use of the connection here.

        # handle response and return to the user...

        return response
                
    def list(self, params = None):
        url = self.build_url("")  
        

        response = self.con.get(url, params = params)  # note the use of the connection here.

        # handle response and return to the user...

        return response
