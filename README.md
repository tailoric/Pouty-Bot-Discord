# Pouty-Bot-Discord


## Bot Setup
* clone repository
* create bot account on https://discordapp.com/developers/applications/me
* create a json file called `credentials.json` inside the `data` folder with the following schema:
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
  example config below (located at `data/postgres.json`).
  ```json
    {
      "user" : "postgres",
      "dbname": "postgres",
      "password": "pouty",
      "hostaddr": "localhost"
    }
  ```
  inside the `data` folder and put in the necessary information
* then create a file called `initial_cogs.json` inside the `data` directory and put in the cogs you want to use for example
  ```json
  [
    "cogs.owner",
    "cogs.playlist"
  ]
  ```
* [set up an virtual environment](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/#creating-a-virtual-environment)
* install the requirements via `pip install -r requirements.txt` inside the root directory of the repository
* run the bot via `python bot.py` (I currently run the bot on python version 3.5.2)

### Docker

If you have docker installed simply build the Dockerfile and run the docker-compose.yml  
files mentioned above need to be prepared as explained however
```bash
$ docker build -t pouty-bot .
$ docker compose up
```

`data/postgres.json` needs to have the same values set as defined in the docker-compose.yaml file
```json
    {
      "user" : "postgres",
      "dbname": "botdb",
      "password": "postgres_pouty",
      "hostaddr": "postgres"
    }
```
