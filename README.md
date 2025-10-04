# BGG to Airtable connector

Sync a user's boardgamegeek collection to airtable for fun analysis!

## BGG API notes

BoardGameGeek has an XML API for accessing both game and user data. It's
documented here:

-   https://boardgamegeek.com/wiki/page/BGG_XML_API2

To access a specific user's plays, the endpoint is:

-   https://boardgamegeek.com/xmlapi2/plays?username=<username>

Note: There is code for getting play data commented out in the main
function, but syncing plays to Airtable was impractical due to the
1,000 row limit for tables on free accounts.

To get private collection info, e.g. acquisition date or price paid,
the user has to be logged in. There is no API key. So the session
that accesses the collection endpoint first has to log in to the site.
This is explained in a BGG thread:

-   https://boardgamegeek.com/thread/2182271/programmatic-login-and-collection-update-scripts

## Github Actions

A github actions workflow runs the code once a day. TODO: Have the action
commit something so the workflow won't expire.
