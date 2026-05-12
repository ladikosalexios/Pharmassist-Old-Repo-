from datetime import datetime


def age_from_date(birthdate: datetime) -> int:
    """Returns the age of a person born on the given date, rounded down."""
    today = birthdate.today()
    # Subtract birth year from current year
    # Subtract 1 if the birthday hasn't happened yet this year
    return (
        today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
    )
