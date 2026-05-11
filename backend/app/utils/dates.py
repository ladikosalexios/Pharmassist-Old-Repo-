from datetime import datetime

def age_from_date(date: datetime) -> int:
    """Returns the age of a person born on the given date, rounded down."""
    today = date.today()
    # Subtract birth year from current year
    # Subtract 1 if the birthday hasn't happened yet this year
    return today.year - date.year - ((today.month, today.day) < (date.month, date.day))
