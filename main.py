import json
import os
import sys
import time

import jsonpickle
import numpy
from decouple import config
from eta import ETA
from steam import Steam

# Config
DEBUG_APP_LOAD = False
DELAY = 1  # minimum of 0.75, recently-rate-limited minimum of 1.2

# Set up API
KEY = config('STEAM_API_KEY')
steam = Steam(KEY)

username = ''
user = 'No match'
files = [
    'debug.log.json',
    'achievements.json',
    'counting.json',
    'outliers.json',
    'games.json',
]

# Continuously ask for a username
while user == 'No match':
    # Show where to find the value needed if a username is not working
    if username != '':
        print('User could not be found')
        print('Copy the value from Edit Profile > Custom URL')
    # Ask for the username
    username = input('Username: ')
    # Search for the username
    user = steam.users.search_user(search=username)

# Load the steam id
if type(user) is not dict:
    sys.exit('User not loaded')

steam_id = user['player']['steamid']

"""""""""""""""""""""""""""""""""""""""
Actual data loading
"""""""""""""""""""""""""""""""""""""""
print("Downloading game and achievement data from Steam ...")  # Status Message

# Get a list of the user's games
games = steam.users.get_owned_games(steam_id=steam_id)

achievements = []

total = len(games['games'])
eta = ETA(total, modulo=2)

# Reset logging each time
if os.path.exists('debug.log.json'):
    os.remove('debug.log.json')
with open('debug.log.json', 'a') as log:
    for game in games['games']:
        eta.print_status()
        app_id = int(game['appid'])

        # Load game data
        try:
            app = steam.apps.get_app_details(app_id=app_id)
        except:
            if DEBUG_APP_LOAD: print('app data load: ' + str(app_id))
            log.write('app data load: ' + str(app_id) + '\n')
            continue
        app = jsonpickle.loads(app)

        # Avoid Rate limiting
        time.sleep(DELAY)

        # Skip failed games
        try:
            if not app[str(app_id)]['success']:
                if DEBUG_APP_LOAD: print('app has data: ' + str(app_id))
                log.write('app has data: ' + str(app_id) + '\n')
                continue
        except:
            if DEBUG_APP_LOAD: print('app data: ' + str(app_id))
            log.write('app data: ' + str(app_id) + '\n')
            continue

        # TODO: 2 logs above + 1 below: print the name of apps that failed

        app_achievements = 0
        # Load number of achievements in game
        try:
            if "achievements" in app[str(app_id)]['data'].keys():
                app_achievements = int(app[str(app_id)]['data']['achievements']['total'])
        except:
            if DEBUG_APP_LOAD: print('app achievement data: ' + str(app_id))
            log.write('app achievement data: ' + str(app_id) + '\n')
            continue

        # Skips games with no achievements
        if app_achievements < 1:
            if DEBUG_APP_LOAD: print('app achievement count: ' + str(app_id))
            log.write('app achievement count: ' + str(app_id) + '\n')
            continue

        # TODO: Do user achievements earlier to avoid loading non-counting games
        # # Plus this would make the Progress bar more accurate

        # Load the user's achievement info for this game
        try:
            user_stats = steam.apps.get_user_achievements(steam_id=int(steam_id), app_id=app_id)
        except:
            if DEBUG_APP_LOAD: print('user data load: ' + str(app_id))
            log.write('user data load: ' + str(app_id) + '\n')
            continue

        # Avoid Rate limiting
        time.sleep(DELAY * 0.25)

        # Skip games that failed to load achievements (unknown reason why)
        try:
            if not user_stats['playerstats']['success']:
                if DEBUG_APP_LOAD: print('app has user data: ' + str(app_id))
                log.write('app has user data: ' + str(app_id) + '\n')
                continue
        except:
            if DEBUG_APP_LOAD: print('user data: ' + str(app_id))
            log.write('user data: ' + str(app_id) + '\n')
            continue

        """""""""""""""""""""""""""""""""""""""
        Actual achievement data saving
        """""""""""""""""""""""""""""""""""""""

        # Save achievement data
        game_achievements = user_stats['playerstats']['achievements']

        for achievement in game_achievements:
            achievement['achieved'] = achievement['achieved'] == 1  # Change truthy values to a boolean
            achievement['game'] = app_id
            achievements.append(achievement)

del achievement
del app_achievements
del app
del game_achievements
del user_stats
del log
eta.done()

"""""""""""""""""""""""""""""""""""""""
AGCR calculation
"""""""""""""""""""""""""""""""""""""""
print("Formatting data and calculating AGCR ...")  # Status Message

games = {}
achievements_done = 0
for achievement in achievements:
    game = achievement['game']

    # Track number of completed achievements total
    achievements_done += 1 if achievement['achieved'] else 0

    # Instantiate tracking of a game
    if game not in games.keys():
        games[game] = {
            'app_id': game,
            'counts': achievement['achieved'],
            'completion': 0.0,
            'achievements_total': 1,
            'achievements_done': 1 if achievement['achieved'] else 0,
            'impact': 0.0,
            'achievements': {
                achievement['apiname']: achievement['achieved']
            }
        }
    # Update tracking of a game
    else:
        if not games[game]['counts']:
            games[game]['counts'] = achievement['achieved']
        games[game]['achievements_total'] += 1
        games[game]['achievements_done'] += 1 if achievement['achieved'] else 0
        games[game]['achievements'][achievement['apiname']] = achievement['achieved']

del achievements
del achievement

# Get the numbers for which games count towards the user's AGCR and their completion%
games_that_count = []
running_completion_percent = []
for key, game in games.items():
    if game['app_id'] in games_that_count:
        continue
    if game['counts']:
        games_that_count.append(game['app_id'])
        # Track the completion% of each game
        completion = game['achievements_done'] / game['achievements_total']
        running_completion_percent.append(completion)
        games[key]['completion'] = completion

del key
del game
del completion

# Average completion%, to 2 decimal places
agcr = sum(running_completion_percent) / len(games_that_count) * 100
agcr = '{0:.2f}'.format(agcr)

print('games that count: ' + str(len(games_that_count)))
print('AGCR: ' + str(agcr) + '%')

# https://steamcommunity.com/sharedfiles/filedetails/?id=650166273

"""""""""""""""""""""""""""""""""""""""
AGCR-impact calculations
"""""""""""""""""""""""""""""""""""""""
print("Calculating game impact ...")  # Status Message

# Change games dict to a list
real_games = []
for trash, game in games.items():
    if game['counts']:
        real_games.append(game)
games = real_games
del real_games
del trash

# Determine impact of this game on AGCR
for game_id, game in enumerate(games):
    for calc_id, percent in enumerate(running_completion_percent):
        # Find the stored % in the list for averaging
        if abs(percent - game['completion']) < 1e-5:
            running_calculation = running_completion_percent.copy()
            # Change it to a 100% completion
            running_calculation[calc_id] = 1.0
            # Finding the new AGCR with that change
            calculation_agcr = sum(running_calculation)
            calculation_agcr /= len(games_that_count)
            calculation_agcr *= 100
            calculation_agcr = float('{0:.2f}'.format(calculation_agcr))
            # Save the difference in AGCR values
            games[game_id]['impact'] = abs(calculation_agcr - float(agcr))
            break

del game_id
del calc_id
del game
del percent
del running_calculation
del calculation_agcr

with open('games.json', 'w') as file:
    json.dump(games, file, indent=2)
del file

"""""""""""""""""""""""""""""""""""""""
Resolution calculations
"""""""""""""""""""""""""""""""""""""""

# TODO: Rework this to work off of impact, to find high impact games with low achievements-left or totals

# Determine lower threshold to separate outliers
completion_lower_quartile = numpy.array(running_completion_percent)
completion_lower_quartile = numpy.quantile(completion_lower_quartile, 0.1)  # Bottom 10%

low_outliers = []

# List outliers
for game in games:
    if game['counts']:
        if game['completion'] < completion_lower_quartile:
            low_outliers.append(game)

low_outliers.sort(key=lambda x: x['achievements_done'], reverse=True)
low_outliers.sort(key=lambda x: x['achievements_total'])

with open('outliers.json', 'w') as file:
    json.dump(low_outliers, file, indent=2)
del file

# TODO: Find a list of achievements with high global completion% that are not done in high impact games
# TODO Find a list of high global completion% achievement clusters in low play time games

"""""""""""""""""""""""""""""""""""""""
Formatting
"""""""""""""""""""""""""""""""""""""""

# HTML output?
# PNG output?

"""
for file in files:
    if os.path.exists(file):
        os.remove(file)
"""
