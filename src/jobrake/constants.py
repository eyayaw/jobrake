class JobrakeConstants:
    sites: tuple = ("linkedin", "indeed")
    hours_old: int | None = 24
    results_wanted: int = 25
    radius: int | None = 50
    radius_unit: str = "KILOMETERS"
    fetch_description: bool = False
