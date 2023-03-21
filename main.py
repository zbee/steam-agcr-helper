import json
import os
import sys
import time

import numpy
from decouple import config
from eta import ETA
from steam import Steam

"""
Config
"""
# Amount of time (in seconds) to wait between API requests
DELAY = 0.75  # >0.75 recommended

# Games you do not want to be recommended to play
# If you want to add to this, turn on DEBUG and you can copy names from games.json
BLACK_LISTED_GAMES = [
    "Dead by Daylight",
    "Team Fortress 2",
    "Garry's Mod",
    "Total War: WARHAMMER II",
    "Surgeon Simulator",
]

# If you want debug files to be saved for your review after this runs
DEBUG = True

"""
Setup data
"""

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
    'hilo_games.json',
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
total = len(games['games'])

achievements = []
failed_games = []

eta = ETA(total, modulo=2)

# Reset logging each time
if os.path.exists('debug.log.json'):
    os.remove('debug.log.json')
with open('debug.log.json', 'a') as log:
    for game in games['games']:
        eta.print_status()
        app_id = int(game['appid'])

        # Load the user's achievement info for this game
        try:
            user_stats = steam.apps.get_user_achievements(
                steam_id=int(steam_id), app_id=app_id
            )
        except:
            if DEBUG: log.write(f"user data load: {app_id} ({game['name']}) \n")
            continue

        # Avoid Rate limiting
        time.sleep(DELAY)

        # Skip games that failed to load achievements (unknown reason why)
        try:
            if not user_stats['playerstats']['success']:
                if DEBUG: log.write(f"app has user data: {app_id} ({game['name']}) \n")
                failed_games.append(game['name'])
                continue
            if 'achievements' not in user_stats['playerstats'].keys():
                if DEBUG: log.write(f"app no achievements: {app_id} ({game['name']}) \n")
                failed_games.append(game['name'])
                continue
        except:
            if DEBUG: log.write(f"user data: {app_id} ({game['name']}) \n")
            continue

        """""""""""""""""""""""""""""""""""""""
        Actual achievement data saving
        """""""""""""""""""""""""""""""""""""""

        # Save achievement data
        game_achievements = user_stats['playerstats']['achievements']

        for achievement in game_achievements:
            achievement['achieved'] = achievement['achieved'] == 1  # Change truthy values to a boolean
            achievement['game'] = app_id
            achievement['game_name'] = game['name']
            achievement['playtime'] = game['playtime_forever']
            achievement['image'] = 'http://media.steampowered.com/steamcommunity/public/images/apps/' + \
                                   game['img_icon_url'] + '.jpg'
            achievements.append(achievement)

del achievement
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
            'app_name': achievement['game_name'],
            'app_image': achievement['image'],
            'counts': achievement['achieved'],
            'completion': 0.0,
            'achievements_total': 1,
            'achievements_done': 1 if achievement['achieved'] else 0,
            'impact': 0.0,
            'playtime': achievement['playtime'],
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
print("Calculation resolution methods ...")  # Status Message

# List of games that are "black-listed"
"""
These are games that will not be included in any of the recommended sections
>1h play time, <5h play time, <5% achievements + manual entries
The automatically added games are meant to be "Games you tried to and did not like"
"""
black_listed_games = []
black_listed_games.extend(BLACK_LISTED_GAMES)

for game in games:
    if game['app_name'] not in BLACK_LISTED_GAMES:
        if game['completion'] < 0.05 and 60 < game['playtime'] < 300:
            black_listed_games.append(game['app_name'])


# Games that are unusually high impact on AGCR
# Determine upper threshold of "normal" impact of games # Top 10%
impact_upper_quartile = numpy.array(running_completion_percent)
impact_upper_quartile = numpy.quantile(impact_upper_quartile, 0.90)

high_outliers = []


# List outliers
for game in games:
    if game['counts'] and game['app_name'] not in black_listed_games:
        if game['impact'] > impact_upper_quartile:
            high_outliers.append(game)

high_outliers = high_outliers[0:10]

with open('outliers.json', 'w') as file:
    json.dump(high_outliers, file, indent=2)
del file


# Games that are high impact and low achievement count
hilo_games = games.copy()

for key, game in enumerate(hilo_games):
    if game in black_listed_games or game in high_outliers or game['achievements_total'] > 50:
        del hilo_games[key]
del key
del game

hilo_games.sort(key=lambda x: (x['impact'], x['achievements_total']))
hilo_games.reverse()
hilo_games = hilo_games[0:10]

with open('hilo_games.json', 'w') as file:
    json.dump(high_outliers, file, indent=2)
del file


# Games that are just high impact
high_games = games.copy()

for key, game in enumerate(high_games):
    if game in black_listed_games or game in high_outliers or game in hilo_games:
        del high_games[key]
del key
del game

high_games.sort(key=lambda x: x['impact'])
high_games.reverse()
high_games = high_games[0:10]

# TODO: Find a list of achievements with high global completion% that are not done in high impact games
# TODO: Find a list of high global completion% achievement clusters in low play time games

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
