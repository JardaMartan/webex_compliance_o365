from O365.utils import BaseTokenBackend
from ddb_single_table_obj import DDB_Single_Table
import logging

class DBTokenBackend(BaseTokenBackend):
    """ A token backend based on files on the single-table DynamoDB """

    logger = logging.getLogger(__name__)
    
    def __init__(self, owner_id="local", storage_id="noname", secondary_id="no_id"):
        """
        Init Backend
        :param str owner_id: Owner ID (primary key)
        :param str storage_id: Storage ID (secondary key)
        """
        super().__init__()
        
        self.owner_id = owner_id
        self.storage_id = storage_id
        self.secondary_id = secondary_id
        self.token_tag = "O365_TOKEN"
        self.ddb = DDB_Single_Table()
        
    def __repr__(self):
        return str(self.ddb.table_name+":"+self.owner_id+":"+self.storage_id+":"+self.secondary_id)
        
    @property
    def storage_hash(self):
        return self.token_tag+"#"+self.storage_id

    def load_token(self):
        """
        Retrieves the token from the DB
        :return dict or None: The token if exists, None otherwise
        """
        token = None
        db_data = self.ddb.get_db_record(self.owner_id, self.storage_hash)
        if db_data is None:
            try:
                db_data = self.ddb.get_db_records_by_secondary_key(self.storage_hash, self.secondary_id)[0]
                self.logger.debug("DB data: {}".format(db_data))
                token = db_data.get("token", None)
                if token is not None:
                    self.owner_id = db_data.get("pk")
                    self.logger.info("owner id set to: {}".format(self.owner_id))
            except IndexError as e:
                self.logger.debug("No token retrieved")
        else:
            token = db_data.get("token")
        
        return token

    def save_token(self):
        """
        Saves the token dict in the DB
        :return bool: Success / Failure
        """
        if self.token is None:
            raise ValueError('You have to set the "token" first.')

        try:
            self.ddb.save_db_record(self.owner_id, self.storage_hash, self.secondary_id, **{"token": self.token})
        except Exception as e:
            log.error('Token could not be saved: {}'.format(str(e)))
            return False

        return True

    def delete_token(self):
        """
        Deletes the token record from DB
        :return bool: Success / Failure
        """
        
        self.ddb.delete_db_record(self.owner_id, self.storage_hash)

        return True

    def check_token(self):
        """
        Cheks if the token exists in the filesystem
        :return bool: True if exists, False otherwise
        """
        
        tk = self.load_token()
        return tk is not None
