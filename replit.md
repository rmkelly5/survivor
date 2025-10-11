# NFL Survivor Pool Application

## Overview
This is a Django-based NFL Survivor Pool web application where users can make weekly NFL picks for a survivor pool competition. Users select one team per week, and if that team wins, they advance to the next week. If the team loses, they're eliminated from the pool.

## Project Status
- **Last Updated:** October 11, 2025
- **Status:** Production-ready with PostgreSQL database
- **Current State:** Application is running with NFL API integration and PostgreSQL backend

## Recent Changes
- October 11, 2025: Migrated to PostgreSQL for production readiness
  - Successfully migrated from SQLite to PostgreSQL (68 objects migrated)
  - Installed psycopg2-binary for PostgreSQL connectivity
  - Updated settings.py to use PostgreSQL environment variables
  - All data preserved: 6 users, 32 teams, 12 picks (5 wins, 2 losses, 5 TBD)
  - Application tested and verified working with PostgreSQL
  
- October 11, 2025: Implemented TBD status and NFL API integration
  - Modified Pick model's `is_win` field to support tri-state values (None/True/False)
  - Added TBD status display for games that haven't been played yet
  - Updated fetch_nfl_winners command to extract team nicknames from ESPN API
  - Fixed leaderboard and allPicks views to handle NULL values
  - Fetched historical results for weeks 1-5 from ESPN API
  
- October 10, 2025: Imported from GitHub and configured for Replit
  - Installed all required Python dependencies
  - Configured ALLOWED_HOSTS for Replit proxy environment
  - Set up Django development server on port 5000
  - Configured production deployment with Gunicorn
  - Created static directory structure
  - Updated settings.py to use environment variables for SECRET_KEY and DEBUG (production-ready)

## Technology Stack
- **Framework:** Django 5.2.7
- **Language:** Python 3.12
- **Database:** PostgreSQL (Replit-managed)
- **Key Dependencies:**
  - psycopg2-binary: PostgreSQL adapter for Python
  - django-tables2: For displaying pick tables
  - django-background-tasks: For background job processing
  - pandas: For data manipulation
  - requests: For fetching NFL game data
  - gunicorn: Production WSGI server

## Project Structure
```
survivor/               # Main Django project directory
├── settings.py        # Django settings
├── urls.py           # Main URL routing
└── wsgi.py          # WSGI configuration

survivorPool/          # Main application for survivor pool
├── management/       # Custom Django management commands
│   └── commands/    # NFL data fetching commands
├── templates/       # HTML templates
├── static/         # CSS and static files
├── tasks/          # Background tasks
├── models.py       # Database models
├── views.py        # View logic
└── forms.py        # Django forms

members/              # User authentication app
├── templates/       # Login/registration templates
└── views.py        # Auth views
```

## Features
- User registration and authentication
- Weekly NFL pick selection
- Leaderboard tracking
- Pick history and details
- Automated NFL game winner fetching
- Background task processing for data updates

## Development
- **Workflow:** Django Server runs on port 5000
- **Command:** `python manage.py runserver 0.0.0.0:5000`
- **Access:** Available through Replit webview

## Deployment
- **Type:** Autoscale deployment (stateless web app)
- **Production Server:** Gunicorn
- **Command:** `gunicorn --bind=0.0.0.0:5000 --reuse-port survivor.wsgi:application`

### Required Environment Variables for Deployment
Before deploying to production on Replit, you must set these environment variables in the Replit Secrets:
1. **DJANGO_SECRET_KEY**: Generate a secure secret key (e.g., using `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`)
2. **DJANGO_ALLOWED_HOSTS**: Set to `*` for Replit deployments (required for dynamic proxy routing)
3. **DJANGO_DEBUG**: Set to `False` or leave unset (defaults to False for security)

### PostgreSQL Database Environment Variables
The application automatically uses these PostgreSQL environment variables (provided by Replit):
- **PGDATABASE**: Database name
- **PGUSER**: Database user
- **PGPASSWORD**: Database password
- **PGHOST**: Database host
- **PGPORT**: Database port
- **DATABASE_URL**: Full connection string (alternative to individual vars)

## Configuration Notes
- Database migrations have been applied
- Static files directory created at `/static/`
- Time zone configured to EST
- **Security & Environment Variables:**
  - **DJANGO_DEBUG**: Set to 'True' for development (default: False for production)
  - **DJANGO_SECRET_KEY**: Override with custom secret key for production deployments
  - **DJANGO_ALLOWED_HOSTS**: 
    - Development workflow sets to '*' (required for Replit proxy)
    - Default is 'localhost,127.0.0.1' for security
    - For production on Replit, must be set to '*' due to dynamic proxy routing

## Database Models
- **Pick:** User's weekly NFL team picks
- **NFLTeam:** NFL team information
- User authentication handled by Django's built-in User model
