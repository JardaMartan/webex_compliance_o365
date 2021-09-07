# Webex Teams Compliance (Events) API Sample Client

This is a sample implementation of [Compliance](https://developer.webex.com/docs/api/guides/compliance) monitoring of Webex Teams [Events API](https://developer.webex.com/docs/api/v1/events) a [Microsoft Graph API](https://docs.microsoft.com/en-us/graph/api/overview). It periodically checks for new events (EVENT_CHECK_INTERVAL, default 15s) and processes the data. The application is using OAuth grant flow to get the access token both for Webex and Graph APIs. So it can be used also as a sample of [Webex Teams Integration](https://developer.webex.com/docs/integrations) implementation. Because the application implements the OAuth grant flow, it runs a web server using [Flask](https://flask.palletsprojects.com). In order to avoid running the OAuth flow at every start, the Access and Refresh Tokens are stored in a database. The application is using standalone [DynamoDB](https://hub.docker.com/r/amazon/dynamodb-local) running in Docker container. The DynamoDB container is modified to store data persistently.

## How to run it
1. **Create a new Webex Teams integration**
  * login to https://developer.webex.com
  * click on your avatar in the upper right corner and select **[My Webex Apps](https://developer.webex.com/my-apps)**
  * click on **[Create New App](https://developer.webex.com/my-apps/new)** and select **Create an Integration**
  * set the **Redirect URI** to `http://localhost:5050/manager`
  * fill in the required fields and select Scopes `spark:people_read` and all that start with `spark-compliance` (`spark-compliance:events_read`, `spark-compliance:memberships_write`, etc.)
  * click **Save**
  * copy & paste **Integration ID**, **Client ID** and **Client Secret** to the appropriate environment variables in `docker-compose.yml` (WEBEX_INTEGRATION_ID, WEBEX_INTEGRATION_CLIENT_ID, WEBEX_INTEGRATION_CLIENT_SECRET). Do not forget to uncomment the variables. Save the file.
2. **Create Compliance Officer account**
  * login to [Webex Control Hub](https://admin.webex.com) and select a user who will act as a Compliance Officer (or create a new user).
  * in the **Roles and Security** click on **Service Access** and check the **Compliance Officer** checkbox
  * click **Save**
3. **Create a new Enterprise Application in Azure AD**
  * login to your AzureAD instance
  * create Enterprise application, get the client id, object id and client secret and paste them to the appropriate environment variables in `docker-compose.yml`. Do not forget to uncomment the variables. Save the file.
  * set the **Redirect URI** to `http://localhost:5050/o365doauth`
4. **Build the docker** `docker compose build`
5. **Run the docker** `docker compose up` (use `-d` switch to run in background)
6. Because you have not ran the OAuth grant flow yet, the application will log `ERROR:wxt_compliance:No access tokens for user. Authorize the user first.`
7. Open `http://localhost:5050/authorize`, replace `localhost` with your Docker host.
8. If you have done the previous steps correctly, you will be asked to login to Webex. Use the Compliance Officer credentials. After logging in, confirm the scopes required by the application. At the end of the OAuth process you will be redirected to http://localhost:5050/manager with code attached to URL. If you used your Docker host in place of `localhost`, replace it in this URL and press Enter. If all went well you will be presented with a message "**Thank you for providing the authorization. You may close this browser window.**"
9. Repeat the process for Graph API - open `http://localhost:5050/o365auth` and authenticate using your Office365 admin account
10. In the application log you will see the Access and Refresh Tokens being created and saved in DynamoDB.
11. The application will start monitoring the Events API.
12. Try sending a message in Webex Teams, creating s Space or adding/deleting users to a Space. All should be logged by the application.
