# Pouty-Bot-Discord


## Bot Setup
* clone repository
* create bot account on https://discordapp.com/developers/applications/me
* create a json file called `credentials.json` with the following schema:
  ```json
  {
  "client-id" : "123456789",
  "client_secret": "AJS23ASJDAS_123124AS214",
  "token": "ASDKASLDASDSdas.asdkkasjdkljsldk"
  }
  ```
  and put in the information
* then create a file called `initial_cogs.json` and put in the cogs you want to use for example
  ```json
  [
    "cogs.owner",
    "cogs.playlist"
  ]
  ```
* install the requirements via `pip install -r requirements.txt` inside the root directory of the repository
* run the bot via `python bot.py` (I currently run the bot on python version 3.5.2)
