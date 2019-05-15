# Automatically Tag Virtual Machines in Azure
## Intended to run as in the web app service.

Python/Flask Web Application that can subscribe to Event Grid and auto-tag the VM or Storage Account with the creator of the object. That is set in it_Owner (per our policy).

Requirements.

1. Set the environment variabke key=yourpassword in your web app.
2. Enable managed identity for the web app
3. Grant contributor access to the subscriptions you plan to monitor
4. Event Grid subscription to the web hook
Filter out for write success, and if you want subject contains "virtualMachines" and "storageAccounts" to limit messages.

https://autotag.azurewebsites.net/api/update?code=password

The web hook will validate itself with Event Grid at the above URL and will receive messages there.

