from steam import Steam
from decouple import config
from eta import ETA
import jsonpickle
import sys
import time

# Config
DEBUG_APP_LOAD = False
DELAY = 0.8  # minimum of 0.85, recently-rate-limited minimum of 1.3

# Set up API
KEY = config("STEAM_API_KEY")
steam = Steam(KEY)


# Why is it so much effort to pretty-print JSON. Make it less.
def json(thing):
    print(jsonpickle.encode(thing, indent=2))


username = ""
user = "No match"

# Continuously ask for a username
while user == "No match":
    # Show where to find the value needed if a username was entered but could not be found
    if username != "":
        print("User could not be found")
        print("Copy the value from Edit Profile > Custom URL")
    # Ask for the username
    username = input("Username: ")
    # Search for the username
    user = steam.users.search_user(search=username)

# Load the steam id
if type(user) is not dict:
    sys.exit("User not loaded")

# noinspection PyTypeChecker
steam_id = user["player"]["steamid"]

"""""""""""""""""""""""""""""""""""""""
Actual data loading
"""""""""""""""""""""""""""""""""""""""

# Get a list of the user's games
games = steam.users.get_owned_games(steam_id=steam_id)

achievements = []

total = len(games["games"])
eta = ETA(total)

for game in games["games"]:
    eta.print_status()
    app_id = int(game["appid"])

    # Load game data
    try:
        app = steam.apps.get_app_details(app_id=app_id)
    except:
        if DEBUG_APP_LOAD: print("app data load: " + str(app_id))
        continue
    app = jsonpickle.loads(app)

    # Skip failed games
    try:
        if not app[str(app_id)]["success"]:
            if DEBUG_APP_LOAD: print("app has data: " + str(app_id))
            continue
    except:
        if DEBUG_APP_LOAD: print("app data: " + str(app_id))
        continue

    app_achievements = 0
    # Load number of achievements in game
    try:
        if "achievements" in app[str(app_id)]["data"].keys():
            app_achievements = int(app[str(app_id)]["data"]["achievements"]["total"])
    except:
        if DEBUG_APP_LOAD: print("app achievement data: " + str(app_id))
        continue

    # Skips games with no achievements
    if app_achievements < 1:
        if DEBUG_APP_LOAD: print("app achievement count: " + str(app_id))
        continue

    # Load the user's achievement info for this game
    try:
        user_stats = steam.apps.get_user_achievements(steam_id=int(steam_id), app_id=app_id)
    except:
        if DEBUG_APP_LOAD: print("user data load: " + str(app_id))
        continue

    # Skip games that failed to load achievements (unknown reason why)
    try:
        if not user_stats["playerstats"]["success"]:
            if DEBUG_APP_LOAD: print("app has user data: " + str(app_id))
            continue
    except:
        if DEBUG_APP_LOAD: print("user data: " + str(app_id))
        continue

    # Avoid Rate limiting
    time.sleep(DELAY)

    """""""""""""""""""""""""""""""""""""""
    Actual achievement data saving
    """""""""""""""""""""""""""""""""""""""

    # Save achievement data
    game_achievements = user_stats["playerstats"]["achievements"]

    for achievement in game_achievements:
        achievement["achieved"] = achievement["achieved"] == 1  # Change truthy values to Truthy values
        achievements.append(achievement)

eta.done()

print(achievements)
# TODO: Save to file

"""""""""""""""""""""""""""""""""""""""
AGCR calculation
"""""""""""""""""""""""""""""""""""""""

# https://steamcommunity.com/sharedfiles/filedetails/?id=650166273

"""""""""""""""""""""""""""""""""""""""
AGCR-impact calculations
"""""""""""""""""""""""""""""""""""""""

"""""""""""""""""""""""""""""""""""""""
Resolution calculations
"""""""""""""""""""""""""""""""""""""""

# High% global achievement completion in high impact games, which are counted!
# High% global achievement completion in low-achievement games with low average play time of games counted or not?

"""""""""""""""""""""""""""""""""""""""
Formatting
"""""""""""""""""""""""""""""""""""""""

# HTML output?
# PNG output?

