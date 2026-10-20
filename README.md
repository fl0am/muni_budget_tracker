# TMR Municipal Budget Tracker

Shows which cities, counties, townships, park districts and school districts to call each month, based on
**when each one builds its budget**. Covers all 50 states and DC (about 17,900 governments).

By default it includes places with 10,000+ people, **plus** any smaller town or park district that spends $500k+/yr on parks & rec. Park districts are separate governments that run parks in Illinois, North Dakota, California, Ohio, Washington, Colorado, Oregon and other states.

## How it works
Every local government reports its fiscal year end date to the U.S. Census Bureau. Counting from the
start of the fiscal year, each government's year is split into phases:

| Months after FY start | Status | What to do |
|---|---|---|
| 0–2 | 🔵 New fiscal year | Money just released. Follow up only where they budgeted for us. |
| 3–6 | 🟢 Call now | Departments are drafting next year's requests. Get the robot in. |
| 7–8 | 🟢 Last call | Budget under review. Still possible to get added. |
| 9 | 🔴 Budget locked | Council is adopting the budget. Don't cold call. |
| 10–11 | 🟡 Year-end spend | Use-it-or-lose-it money. Pitch Pay As You Spray or small purchases. |

Example: Atlanta's fiscal year starts July 1, so call now is Oct–Jan, last call is Feb–Mar, the budget is locked in April, and May–June is year-end spend.
You can change these ranges in the app sidebar under **Adjust call windows**.

## Features
- **Call list:** governments to call in any month, filtered by state, government type, population, enrollment and parks & rec spending. You can download it as a CSV.
- **Map:** governments colored by status.
- **Year view:** how many governments open their call window each month.
- **Look up one:** a single government's 12-month calendar.
- **HubSpot overlay:** upload a HubSpot companies export (CSV) to flag who's already in HubSpot.

## Data
All data comes from free public Census Bureau files, so no API keys are needed.
- **Fiscal year end, population, enrollment and parks & rec spending:** the 2022 Census of Governments, which covers every unit, plus the 2024 Annual Survey of State & Local Government Finances where it has newer values.
- **Map locations:** the 2024 Census Gazetteer files.

`data/governments.csv` is already built. To refresh it when Census posts a new year, update the URLs in `build_data.py` and run:
```
python build_data.py
```

## Run locally
```
pip install -r requirements.txt
streamlit run app.py
```

## Deploy
Push this folder to its own GitHub repo. Then deploy it on [Streamlit Community Cloud](https://share.streamlit.io) with `app.py` as the main file.

## Files
- `app.py`: the Streamlit app
- `cycle.py`: budget-cycle and call-window logic (run `python cycle.py` for sanity checks)
- `build_data.py`: downloads the Census files and builds `data/governments.csv`
- `test_app.py`: headless smoke test (run `python test_app.py`)
