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
        status = competition.get("status", {}).get("type", {}).get("completed")
        
        # Skip games that haven't finished yet
        if not status:
            continue
        
        # Get both teams' scores
        home_team = competitors[0]
        away_team = competitors[1]
        home_score = int(home_team.get("score", 0))
        away_score = int(away_team.get("score", 0))
        
        # Check for tie - both teams lose (count as losses)
        if home_score == away_score:
            winners.append({
                "winner": None,  # No winner in a tie
                "score": home_score,
                "loser": home_team["team"]["displayName"],
                "loser_score": home_score,
                "game_date": competition["date"],
                "is_tie": True
            })
            winners.append({
                "winner": None,  # No winner in a tie
                "score": away_score,
                "loser": away_team["team"]["displayName"],
                "loser_score": away_score,
                "game_date": competition["date"],
                "is_tie": True
            })
            continue
        
        # Find the winner (home or away)
        for team in competitors:
            if team.get("winner"):
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
                    "game_date": competition["date"],
                    "is_tie": False
                })
                break  # only one winner

    return winners