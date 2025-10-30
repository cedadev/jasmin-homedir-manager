## JASMIN Homedir Manager
This python module is installed on the jasmin (https://jasmin.ac.uk) HPC system and manages certain user-account-lifecycle processes.
It reads data from the JASMIN accounts portal (https://accounts.jasmin.ac.uk)'s API, and allows the portal to cause changes on the main JASMIN unix system.

## Current Actions
* Teardown training accounts.
  * Training accounts are short-lived accounts to allow people to attend training courses without requiring a full account.
  * Training account lifecycle is managed by the accounts portal.
  * When the accounts portal knows that a training account is no longer being used, it's marks the user's lifecycle state as 'AWAITING_CLEANUP'.
  * This script undertakes the following actions:
    * Get list of training accounts requireing teardown.
    * Check the user in question is a training account. All training accounts have a username in the form trainNNN, where N is an integer.
    * Remove the user's home directory. Since JASMIN home directories are a PURE filesystem, it does this by moving them to the .fast-remove folder.
    * Recreate an empty home directory for the user.
    * Change the user's state in the accounts portal to "DORMANT".

* Remove inactive user accounts.
  * Inactive user accounts are removed after a period of time being inactive.
  * Inactive user lifecycle is managed by the accounts portal.
  * This script will undetake the following seperate actions:
    1. Quarantine home directories prior to removal.
        * Get a list of STANDARD users who have been inactive for at least 1 year 3 months (configurable) and who have a lifecycle state of ACCNT_DEL_NOTIFIED.
        * Move the user's home directory to /home/users/.pending_deletion.
        * Set the user's lifecycle state in the portal to ACCNT_DEL_HOME_MOVED.
    2. Remove expired home directories.
        * Get a list of STANDARD users who have been inactive for at least 1 year 6 months (configurable) and who have a lifecycle state of ACCNT_DEL_HOME_MOVED.
        * Remove the user's home directory.
        * Set the user's lifecycle state to ACCNT_DEL_HOME_REMOVED.

### General Principles
* Read a list of users who need their data manipulated from the portal API.
* Backup the user data to be manipulated.
* Manipulate the user data as required.
* Update the portal API with the channge required.
