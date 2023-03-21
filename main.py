"""
Created in 2023 by Ethan Henderson (zbee) <ethan@zbee.codes> (zbee.codes)
"""

import json
import os
import sys
import time
import webbrowser

import numpy
from decouple import config
from eta import ETA
from jinja2 import Environment, FileSystemLoader
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
    "SMITE",
    "Europa Universalis IV",
    "Cookie Clicker",
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
bypassed = False
while user == 'No match':
    # Accept Steam IDs (no vanity URL set) via short-circuit
    if username.isdigit():
        steam_id = int(username)
        bypassed = True
        break
    # Show where to find the value needed if a username is not working
    if username != '':
        print('User could not be found')
        print('Copy the value from Edit Profile > Custom URL')
    # Ask for the username
    username = input('Username: ')
    # Search for the username
    user = steam.users.search_user(search=username)

# Load the steam id
if not bypassed:
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
            failed_games.append(game['name'])
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
                continue
        except:
            if DEBUG: log.write(f"user data: {app_id} ({game['name']}) \n")
            failed_games.append(game['name'])
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
impact_upper_quartile = numpy.quantile(impact_upper_quartile, 0.9)

high_outliers = []

# List outliers
for game in games:
    if game['counts'] and game['app_name'] not in black_listed_games:
        if game['impact'] > impact_upper_quartile:
            high_outliers.append(game)

# Pad out this list so that all sections are the same quantity of games
if len(high_outliers) < 10:
    high_games = games.copy()
    high_games_remove = []

    for game in high_games:
        if (game['app_name'] in black_listed_games) or (game in high_outliers):
            high_games_remove.append(game)
    for game in high_games_remove:
        high_games.remove(game)

    high_outliers.extend(high_games)

    del game
    del high_games
    del high_games_remove

high_outliers.sort(key=lambda x: x['impact'], reverse=True)
high_outliers = high_outliers[0:10]

with open('outliers.json', 'w') as file:
    json.dump(high_outliers, file, indent=2)
del file

# Games that are >80% complete
eighty_games_list = games.copy()
eighty_games_list_remove = []

for game in eighty_games_list:
    if (game['app_name'] in black_listed_games) or (game['completion'] < 0.8) or (game['completion'] == 1.0):
        eighty_games_list_remove.append(game)
for game in eighty_games_list_remove:
    eighty_games_list.remove(game)
del game
del eighty_games_list_remove

eighty_games_list.sort(key=lambda x: x['completion'], reverse=True)
eighty_games_list = eighty_games_list[0:22]

# Games that are high impact and low achievement count
hilo_games = games.copy()
hilo_games_remove = []

for game in hilo_games:
    if (game['app_name'] in black_listed_games) or (game in high_outliers) or (game in eighty_games_list) \
            or (game['achievements_total'] > 50):
        hilo_games_remove.append(game)
for game in hilo_games_remove:
    hilo_games.remove(game)
del game
del hilo_games_remove

hilo_games.sort(key=lambda x: (x['impact'], x['achievements_total']))
hilo_games.reverse()
hilo_games = hilo_games[0:10]

with open('hilo_games.json', 'w') as file:
    json.dump(high_outliers, file, indent=2)
del file

# Games that are just high impact
high_games = games.copy()
high_games_remove = []

for game in high_games:
    if (game['app_name'] in black_listed_games) or (game in high_outliers) or (game in hilo_games) \
            or (game in eighty_games_list):
        high_games_remove.append(game)
for game in high_games_remove:
    high_games.remove(game)
del game

high_games.sort(key=lambda x: x['impact'], reverse=True)
high_games = high_games[0:10]

# Games that are only 1 achievement
one_games_list = games.copy()
one_games_list_remove = []

for game in one_games_list:
    if (game['app_name'] in black_listed_games) or (game['achievements_done'] != 1):
        one_games_list_remove.append(game)
for game in one_games_list_remove:
    one_games_list.remove(game)
del game
del one_games_list_remove
one_games_list = one_games_list[0:22]

# TODO: List of achievements with high global completion% that are not done in high impact games
# TODO: List of high global completion% achievement clusters in low play time games (finishing a campaign)

"""""""""""""""""""""""""""""""""""""""
Formatting
"""""""""""""""""""""""""""""""""""""""
print("Generating output file ...")  # Status Message

# Basic metrics
eighty_games = 0
one_games = 0
achievements_unlocked = 0
achievements_left = 0
for game in games:
    eighty_games += 1 if 0.8 < game['completion'] < 1.0 else 0
    one_games += 1 if game['achievements_done'] == 1 else 0
    achievements_unlocked += game['achievements_done'] if game['counts'] else 0
    achievements_left += game['achievements_total'] if game['counts'] else 0
achievements_left -= achievements_unlocked

# Set up template and file
results_filename = "agcr.html"
environment = Environment(loader=FileSystemLoader("./"))
template = environment.get_template("template.html")

# Render output file
context = {
    'agcr': agcr,
    'games_count': '{:n}'.format(len(games_that_count)),
    'eighty_games': '{:n}'.format(eighty_games),
    'one_games': '{:n}'.format(one_games),
    'achievements_unlocked': '{:n}'.format(achievements_unlocked),
    'achievements_left': '{:n}'.format(achievements_left),
    'failed_games': failed_games,
    'highest_impact': high_outliers,
    'hilo_games': hilo_games,
    'high_games': high_games,
    'eighty_games_list': eighty_games_list,
    'one_games_list': one_games_list,
}

with open(results_filename, mode="w", encoding="utf-8") as results:
    results.write(template.render(context))
    print(f"Wrote to '{results_filename}'. It is being opened in your browser")  # Status Message
    webbrowser.open('file://' + os.path.realpath(results_filename))

# Clean up
if not DEBUG:
    for file in files:
        if os.path.exists(file):
            os.remove(file)
