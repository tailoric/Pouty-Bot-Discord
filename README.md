# Pouty-Bot-Discord


## Bot Setup
* clone repository
* create bot account on https://discordapp.com/developers/applications/me
* create a json file called `credentials.json` with the following schema:
  ```json
  {
  "owner" : "your_own_id_13456", 
  "client-id" : "123456789",
  "client_secret": "AJS23ASJDAS_123124AS214",
  "token": "ASDKASLDASDSdas.asdkkasjdkljsldk"
  }
  ```
* also install postgresql and connect it with the bot because otherwise the bot won't start.  
  (easiest way is via [docker](https://hackernoon.com/dont-install-postgres-docker-pull-postgres-bee20e200198))  
  The bot will expect a database to run on http://localhost:5432  
  example config below  
  ```json
    {
      "user" : "postgres",
      "dbname": "postgres",
      "password": "pouty"
    }
  ```
  inside the `data` folder and put in the necessary information
* then create a file called `initial_cogs.json` and put in the cogs you want to use for example
  ```json
  [
    "cogs.owner",
    "cogs.playlist"
  ]
  ```
* [set up an virtual environment](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/#creating-a-virtual-environment)
* install the requirements via `pip install -r requirements.txt` inside the root directory of the repository
* run the bot via `python bot.py` (I currently run the bot on python version 3.5.2)
