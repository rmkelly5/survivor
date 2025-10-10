# NFL Survivor Pool Application

## Overview
This is a Django-based NFL Survivor Pool web application where users can make weekly NFL picks for a survivor pool competition. Users select one team per week, and if that team wins, they advance to the next week. If the team loses, they're eliminated from the pool.

## Project Status
- **Last Updated:** October 10, 2025
- **Status:** Successfully imported and configured for Replit environment
- **Current State:** Application is running and functional

## Recent Changes
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
- **Database:** SQLite (db.sqlite3)
- **Key Dependencies:**
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
