import requests
from dash import Dash, html, dash_table
from fuzzywuzzy import fuzz, process
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# API URLs
API_URL = "https://www.freetogame.com/api/games"
STEAM_API_URL = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"

# SQLAlchemy setup
DATABASE_URL = "sqlite:///games_data.db"
Base = declarative_base()

# Define Game model
class Game(Base):
    __tablename__ = "games"
    
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    thumbnail = Column(String)
    short_description = Column(Text)
    game_url = Column(String)
    genre = Column(String)
    platform = Column(String)
    publisher = Column(String)
    developer = Column(String)
    release_date = Column(String)
    freetogame_profile_url = Column(String)
    steam_appid = Column(Integer, nullable=True)  # Allow NULL for missing Steam IDs
    steam_player_count = Column(Integer, nullable=True)  # Allow NULL for missing player counts

# Initialize the database and create tables
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Fetch the entire Steam App List and build a dictionary with normalized names
def build_steam_app_dict():
    response = requests.get(STEAM_API_URL)
    if response.status_code == 200:
        app_list = response.json().get('applist', {}).get('apps', [])
        return {app['name'].lower(): app['appid'] for app in app_list}
    else:
        print(f"Failed to fetch Steam App List: {response.status_code}")
        return {}

# Function to match game names with fuzzy matching
def match_app_id(name, app_dict, threshold=90):
    name_lower = name.lower()
    if name_lower in app_dict:
        return app_dict[name_lower]
    
    match, score = process.extractOne(name_lower, app_dict.keys(), scorer=fuzz.token_sort_ratio)
    if score >= threshold:
        return app_dict[match]
    else:
        return None

# Function to get current player count from Steam API
def get_steam_player_count(app_id):
    if app_id is None:
        return None
    url = f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={app_id}"
    response = requests.get(url)
    data = response.json()
    return data['response']['player_count'] if 'player_count' in data['response'] else None

# Fetch FreeToGame data
def fetch_api(url):
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data
    else:
        print(f"Failed to fetch data: {response.status_code}")
        print(response.text)
        return None

# Initialize session
session = Session()

# Fetch data from APIs
steam_app_dict = build_steam_app_dict()
api_data = fetch_api(API_URL)
if api_data is None:
    api_data = []

total_games = len(api_data)
for index, game in enumerate(api_data, start=1):
    existing_game = session.query(Game).filter_by(id=game["id"]).first()
    if existing_game:
        continue 

    game_title = game["title"]
    steam_appid = match_app_id(game_title, steam_app_dict)
    steam_player_count = get_steam_player_count(steam_appid) if steam_appid else None
    
    # Create a Game instance
    game_entry = Game(
        id=game["id"],
        title=game["title"],
        thumbnail=game["thumbnail"],
        short_description=game["short_description"],
        game_url=game["game_url"],
        genre=game["genre"],
        platform=game["platform"],
        publisher=game["publisher"],
        developer=game["developer"],
        release_date=game["release_date"],
        freetogame_profile_url=game["freetogame_profile_url"],
        steam_appid=steam_appid,
        steam_player_count=steam_player_count
    )
    
    # Add and commit each game to the database
    session.add(game_entry)  # Use add since we confirmed it doesn't exist

    # Print progress
    print(f"Processing game {index}/{total_games}: {game['title']}")

# Commit the session once all games are processed
session.commit()
session.close()

# Initialize Dash app
app = Dash(__name__)

# Define layout for the Dash app
app.layout = html.Div([
    html.H1("Free-to-Play Games Dashboard"),

    dash_table.DataTable(
        id='game-table',
        columns=[
            {"name": "Thumbnail", "id": "thumbnail", "presentation": "markdown"},
            {"name": "Title", "id": "title"},
            {"name": "Genre", "id": "genre"},
            {"name": "Platform", "id": "platform"},
            {"name": "Publisher", "id": "publisher"},
            {"name": "Developer", "id": "developer"},
            {"name": "Release Date", "id": "release_date"},
            {"name": "Steam Player Count", "id": "steam_player_count"}
        ],
        data=[
            {
                "thumbnail": f"![{game.title}]({game.thumbnail})",
                "title": game.title,
                "genre": game.genre,
                "platform": game.platform,
                "publisher": game.publisher,
                "developer": game.developer,
                "release_date": game.release_date,
                "steam_player_count": game.steam_player_count if game.steam_player_count is not None else "N/A"
            } for game in session.query(Game).all()
        ],
        style_cell={'textAlign': 'left', 'padding': '10px'},
        style_header={'fontWeight': 'bold'},
        style_data={'whiteSpace': 'normal', 'height': 'auto'},
        markdown_options={"html": True}
    )
])

# Run the Dash app
if __name__ == '__main__':
    app.run_server(debug=True)
