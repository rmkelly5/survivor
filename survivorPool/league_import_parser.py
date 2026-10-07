"""Read exported Sheets values and result colors, never evaluate formulas."""
import io
import re
import zipfile
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook

from .models import Team


class ImportValidationError(ValueError):
    pass


def normalized(value):
    return re.sub(r'[^a-z0-9]', '', str(value or '').casefold())


WIN_COLORS = {'B6D7A8', '00FF00', '00B050', '93C47D', 'D9EAD3', 'C6EFCE'}
LOSS_COLORS = {'E06666', 'FF0000', 'EA9999', 'F4CCCC', 'FFC7CE'}
NO_PICK_NAMES = {'nopick', 'missed', 'missedpick', 'none'}
FULL_TEAM_NAMES = (
    'Arizona Cardinals', 'Atlanta Falcons', 'Baltimore Ravens', 'Buffalo Bills',
    'Carolina Panthers', 'Chicago Bears', 'Cincinnati Bengals', 'Cleveland Browns',
    'Dallas Cowboys', 'Denver Broncos', 'Detroit Lions', 'Green Bay Packers',
    'Houston Texans', 'Indianapolis Colts', 'Jacksonville Jaguars', 'Kansas City Chiefs',
    'Las Vegas Raiders', 'Los Angeles Chargers', 'Los Angeles Rams', 'Miami Dolphins',
    'Minnesota Vikings', 'New England Patriots', 'New Orleans Saints', 'New York Giants',
    'New York Jets', 'Philadelphia Eagles', 'Pittsburgh Steelers', 'San Francisco 49ers',
    'Seattle Seahawks', 'Tampa Bay Buccaneers', 'Tennessee Titans', 'Washington Commanders',
)


def _money(value, cell):
    if value in (None, ''):
        return None
    try:
        amount = Decimal(str(value).replace('$', '').replace(',', '').strip())
        if not amount.is_finite() or amount < 0 or amount.quantize(Decimal('.01')) != amount:
            raise InvalidOperation
        return str(amount.quantize(Decimal('.01')))
    except (InvalidOperation, ValueError):
        raise ImportValidationError(f'{cell}: invalid amount owed.')


def parse_workbook(upload, completed_week):
    if not upload.name.lower().endswith('.xlsx'):
        raise ImportValidationError('Upload an .xlsx export. CSV does not preserve outcome colors.')
    if upload.size > 5 * 1024 * 1024:
        raise ImportValidationError('The workbook must be smaller than 5 MB.')
    content = upload.read(5 * 1024 * 1024 + 1)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if len(archive.infolist()) > 1000 or sum(
                entry.file_size for entry in archive.infolist()
            ) > 25 * 1024 * 1024:
                raise ImportValidationError('The expanded workbook is too large.')
        workbook = load_workbook(io.BytesIO(content), data_only=True, keep_links=False)
    except ImportValidationError:
        raise
    except Exception as exc:
        raise ImportValidationError('This file is not a readable Excel workbook.') from exc
    try:
        if 'Survivor Pool' not in workbook.sheetnames:
            raise ImportValidationError('The workbook needs a sheet named “Survivor Pool”.')
        sheet = workbook['Survivor Pool']
        if sheet.max_row > 2000 or sheet.max_column > 128:
            raise ImportValidationError('The league sheet exceeds 2,000 rows or 128 columns.')
        if normalized(sheet.cell(1, 1).value) != 'week':
            raise ImportValidationError('Cell A1 must contain Week, with player names across row 1.')

        players, columns = [], []
        names = set()
        for column in range(2, sheet.max_column + 1):
            name = str(sheet.cell(1, column).value or '').strip()
            if not name:
                continue
            if len(name) > 150 or normalized(name) in names:
                raise ImportValidationError('Player headers must be unique and no longer than 150 characters.')
            names.add(normalized(name))
            columns.append(column)
            players.append({'name': name, 'expected_losses': None, 'expected_total': None})
        if not players:
            raise ImportValidationError('No player names were found in row 1.')

        teams = {}
        for team in Team.objects.exclude(team_name='No Pick'):
            key = normalized(team.team_name)
            if key in teams:
                raise ImportValidationError(f'Ambiguous team records for {team.team_name}; fix them before importing.')
            teams[key] = team
        for fullname in FULL_TEAM_NAMES:
            short = normalized(fullname.split()[-1])
            if short in teams:
                teams.setdefault(normalized(fullname), teams[short])

        picks, warnings, seen_weeks = [], [], set()
        used_teams = [set() for _ in players]
        expected_pot = None
        for row in range(2, sheet.max_row + 1):
            label = sheet.cell(row, 1).value
            try:
                number = Decimal(str(label))
                week = int(number)
                if not number.is_finite() or number != week or not 1 <= week <= 18:
                    week = None
            except (InvalidOperation, ValueError, TypeError, OverflowError):
                week = None
            if week is None:
                kind = normalized(label)
                if kind in {'losses', 'owed'}:
                    for index, column in enumerate(columns):
                        cell = sheet.cell(row, column)
                        amount = _money(cell.value, cell.coordinate)
                        if kind == 'losses':
                            if amount is not None and Decimal(amount) != int(Decimal(amount)):
                                raise ImportValidationError(f'{cell.coordinate}: losses must be a whole number.')
                            players[index]['expected_losses'] = int(Decimal(amount)) if amount is not None else None
                        else:
                            players[index]['expected_total'] = amount
                elif kind == 'totalpot':
                    expected_pot = _money(sheet.cell(row, 2).value, f'B{row}')
                continue
            if week in seen_weeks:
                raise ImportValidationError(f'Week {week} appears more than once.')
            seen_weeks.add(week)
            for index, column in enumerate(columns):
                cell = sheet.cell(row, column)
                value = str(cell.value or '').strip()
                no_pick = not value or normalized(value) in NO_PICK_NAMES
                color = cell.fill.fgColor
                rgb = color.rgb[-6:].upper() if color.type == 'rgb' and isinstance(color.rgb, str) else ''
                is_win = True if rgb in WIN_COLORS else False if rgb in LOSS_COLORS else None
                if no_pick and week > completed_week:
                    continue
                if week <= completed_week:
                    if no_pick:
                        if is_win is True:
                            raise ImportValidationError(f'{cell.coordinate}: an empty/no-pick cell cannot be a win.')
                        is_win = False
                    elif is_win is None:
                        raise ImportValidationError(f'{cell.coordinate}: completed picks need a recognized red or green fill.')
                elif is_win is not None:
                    raise ImportValidationError(f'{cell.coordinate}: colored results are beyond the completed-week cutoff.')
                team = None if no_pick else teams.get(normalized(value))
                if not no_pick and not team:
                    raise ImportValidationError(f'{cell.coordinate}: unknown team “{value}”.')
                if team and team.pk in used_teams[index]:
                    warnings.append(f'{players[index]["name"]}: {team.team_name} is repeated in Week {week}.')
                if team:
                    used_teams[index].add(team.pk)
                picks.append({
                    'player_index': index, 'week': week,
                    'team_id': team.pk if team else None,
                    'team': team.team_name if team else 'No Pick',
                    'is_win': is_win, 'missed_deadline': no_pick,
                    'source_cell': cell.coordinate,
                })
        missing_weeks = set(range(1, completed_week + 1)) - seen_weeks
        if missing_weeks:
            raise ImportValidationError(f'Missing completed week rows: {", ".join(map(str, sorted(missing_weeks)))}.')
        if not picks:
            raise ImportValidationError('The workbook contains no picks.')
        for player in players:
            if player['expected_total'] is None:
                warnings.append(f'{player["name"]}: no amount-owed summary to reconcile.')
        return {'players': players, 'picks': picks, 'warnings': warnings, 'expected_pot': expected_pot}
    finally:
        workbook.close()
