import requests
from datetime import datetime

def get_nfl_weekly_winners(year: int, week: int):
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?week={week}&year={year}&seasontype=2"
    response = requests.get(url)
    data = response.json()

    winners = []

    for event in data.get("events", []):
        competition = event["competitions"][0]
        competitors = competition["competitors"]

        # Find the winner (home or away)
        for team in competitors:
            if team["winner"]:
                team_name = team["team"]["displayName"]
                team_score = team["score"]
                opponent = [t for t in competitors if t != team][0]
                opponent_name = opponent["team"]["displayName"]
                opponent_score = opponent["score"]

                winners.append({
                    "winner": team_name,
                    "score": team_score,
                    "loser": opponent_name,
                    "loser_score": opponent_score,
                    "game_date": competition["date"]
                })
                break  # only one winner

    return winners